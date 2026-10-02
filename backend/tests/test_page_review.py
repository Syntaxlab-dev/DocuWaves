"""Approval before publishing, end to end: the real app, a real SQLite index
and a real content repo with one project that needs approval and one that
does not. Pinned down: a live page keeps its text until somebody ELSE
approves the change, a draft goes live only through an approval, a
read-only account may decide but not write, and an assistant writing
through MCP lands in the same queue as everybody else.
"""
import importlib

import frontmatter
import git
import pytest
from fastapi.testclient import TestClient

from app.services import (
    changelog, content_files, content_sync, db, git_content_repo, mcp_tools, page_review, pages_store,
    projects_store, search_suggest, session_secret, users_store, webhooks,
)
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}
ANNA = ("anna", "anna-passwort-123")  # editor
BEN = ("ben", "ben-passwort-1234")  # editor
CLARA = ("clara", "clara-passwort-123")  # viewer
CHEF = ("chef", "chef-passwort-123")  # admin


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def page(title, body, published=True):
    return f"---\norder: 1\npublished: {str(published).lower()}\ntitle: {title}\n---\n\n{body}\n"


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    write(content, "handbuch/_project.yml", "name: Handbuch\nreview: required\n")
    write(content, "handbuch/guide/_category.yml", "name: Guide\n")
    write(content, "handbuch/guide/start.md", page("Start", "Der freigegebene Text."))
    write(content, "handbuch/guide/entwurf.md", page("Entwurf", "Noch nicht live.", published=False))
    write(content, "frei/_project.yml", "name: Frei\n")
    write(content, "frei/guide/_category.yml", "name: Guide\n")
    write(content, "frei/guide/info.md", page("Info", "Direkt live."))
    repository = git.Repo.init(repo_dir)
    repository.index.add([str(p.relative_to(repo_dir)) for p in content.rglob("*") if p.is_file()])
    actor = git.Actor("Test", "t@example.com")
    repository.index.commit("Inhalt", author=actor, committer=actor)

    monkeypatch.setattr(settings, "content_repo_path", str(repo_dir))
    monkeypatch.setattr(settings, "content_repo_url", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "index.db"))
    monkeypatch.setattr(settings, "public_base_url", "")
    monkeypatch.setattr(session_secret, "_SECRET_PATH", tmp_path / ".session_secret")
    monkeypatch.setattr(git_content_repo, "_read_repo", lambda: repository)
    monkeypatch.setattr(git_content_repo, "_repo", repository)
    monkeypatch.setattr(git_content_repo, "_mode", git_content_repo.LOCAL)
    git_content_repo._read_cache.clear()
    monkeypatch.setattr(changelog, "_cache", None)
    monkeypatch.setattr(search_suggest, "_cached", None)
    events = []
    monkeypatch.setattr(webhooks, "notify", lambda event, page, *a, **k: events.append((event, page["slug"])))

    db.init_schema()
    content_sync.full_sync()
    users_store.create_first_admin(*CHEF)
    users_store.create_user(*ANNA, users_store.EDITOR)
    users_store.create_user(*BEN, users_store.EDITOR)
    users_store.create_user(*CLARA, users_store.VIEWER)

    app = importlib.import_module("app.main").app
    return {"app": app, "content": content, "repo": repository, "events": events}


def client(world, user=None):
    c = TestClient(world["app"])
    if user:
        r = c.post("/api/auth/login", json={"username": user[0], "password": user[1]}, headers=ORIGIN)
        assert r.status_code == 200, r.text
    return c


def page_id(project_slug, slug):
    project = projects_store.get_project_by_slug(project_slug)
    return pages_store.get_page_by_slug(project["id"], slug)["id"]


def public_text(world, project_slug, slug):
    r = client(world).get(f"/api/public/projects/{project_slug}/pages/{slug}")
    return r.json()["page"]["markdown_content"] if r.status_code == 200 else None


def save(c, pid, title, body):
    current = c.get(f"/api/admin/pages/{pid}").json()
    r = c.put(
        f"/api/admin/pages/{pid}",
        json={"title": title, "markdown_content": body, "category_id": current["category_id"],
              "base_revision": current["revision"]},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    return r.json()


def post(c, path, body=None):
    return c.post(path, json=body or {}, headers=ORIGIN)


class TestTheSetting:
    def test_it_comes_from_the_project_file_and_round_trips(self, world):
        assert projects_store.get_project_by_slug("handbuch")["review_required"] is True
        assert projects_store.get_project_by_slug("frei")["review_required"] is False

    def test_the_admin_switches_it_on_and_it_lands_in_the_file(self, world):
        chef = client(world, CHEF)
        project = projects_store.get_project_by_slug("frei")
        r = chef.put(f"/api/admin/projects/{project['id']}", json={"name": "Frei", "review_required": True},
                     headers=ORIGIN)
        assert r.status_code == 200, r.text
        assert "review: required" in (world["content"] / "frei/_project.yml").read_text()
        assert projects_store.get_project_by_slug("frei")["review_required"] is True
        # And off again: the key leaves the file.
        chef.put(f"/api/admin/projects/{project['id']}", json={"name": "Frei"}, headers=ORIGIN)
        assert "review" not in (world["content"] / "frei/_project.yml").read_text()

    def test_only_the_exact_words_count(self, world):
        write(world["content"], "frei/_project.yml", "name: Frei\nreview: yes please\n")
        assert content_files.read_project("frei")["review_required"] is False


class TestALivePage:
    def test_an_edit_waits_and_readers_keep_the_live_text(self, world):
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        answer = save(anna, pid, "Start", "Der neue Text.")
        assert answer["review"]["pending"] is True and answer["review"]["status"] == ""
        assert public_text(world, "handbuch", "start").strip() == "Der freigegebene Text."
        # The editor opens on the proposal, not on the live text.
        opened = anna.get(f"/api/admin/pages/{pid}").json()
        assert opened["markdown_content"].strip() == "Der neue Text."
        assert opened["review"]["changed_by"] == "anna"
        # And it is a file in the repo, next to the page.
        assert (world["content"] / "handbuch/guide/_pending/start.md").is_file()

    def test_submit_approve_publishes_in_one_commit(self, world):
        anna, ben = client(world, ANNA), client(world, BEN)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Der neue Text.")
        assert post(anna, f"/api/admin/pages/{pid}/review/submit", {"note": "Bitte Absatz 1"}).status_code == 200
        queue = ben.get("/api/admin/reviews").json()
        assert queue["count"] == 1 and queue["reviews"][0]["note"] == "Bitte Absatz 1"
        diff = ben.get(f"/api/admin/pages/{pid}/review/diff").json()["diff"]
        assert "-Der freigegebene Text." in diff and "+Der neue Text." in diff

        commits_before = len(list(world["repo"].iter_commits()))
        r = post(ben, f"/api/admin/pages/{pid}/review/approve")
        assert r.status_code == 200, r.text
        assert len(list(world["repo"].iter_commits())) == commits_before + 1
        assert public_text(world, "handbuch", "start").strip() == "Der neue Text."
        assert not (world["content"] / "handbuch/guide/_pending").exists()
        live = frontmatter.loads((world["content"] / "handbuch/guide/start.md").read_text())
        assert live["reviewed_by"] == "ben"
        assert not any(k.startswith("review_") for k in live.metadata)
        assert ben.get("/api/admin/reviews").json()["count"] == 0
        assert ("updated", "start") in world["events"]
        assert ("review_requested", "start") in world["events"]
        assert ("review_decided", "start") in world["events"]

    def test_four_eyes_the_author_cannot_approve(self, world):
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Selbst freigegeben?")
        post(anna, f"/api/admin/pages/{pid}/review/submit")
        r = post(anna, f"/api/admin/pages/{pid}/review/approve")
        assert r.status_code == 409 and r.json()["detail"] == "own_change"
        # Nor the admin, if the admin was the one who submitted ANNA's text:
        # what counts is who wrote it.
        chef = client(world, CHEF)
        assert post(chef, f"/api/admin/pages/{pid}/review/approve").status_code == 200

    def test_whoever_edits_last_is_the_one_who_cannot_approve(self, world):
        anna, ben = client(world, ANNA), client(world, BEN)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Anna schreibt.")
        save(ben, pid, "Start", "Ben bessert nach.")
        post(anna, f"/api/admin/pages/{pid}/review/submit")
        assert post(ben, f"/api/admin/pages/{pid}/review/approve").json()["detail"] == "own_change"
        assert post(anna, f"/api/admin/pages/{pid}/review/approve").status_code == 200

    def test_an_edit_after_submitting_takes_the_submission_back(self, world):
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Version 1.")
        post(anna, f"/api/admin/pages/{pid}/review/submit")
        answer = save(anna, pid, "Start", "Version 2.")
        assert answer["review"]["status"] == ""
        assert client(world, BEN).get("/api/admin/reviews").json()["count"] == 0

    def test_request_changes_then_resubmit(self, world):
        anna, ben = client(world, ANNA), client(world, BEN)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Erster Wurf.")
        post(anna, f"/api/admin/pages/{pid}/review/submit")
        r = post(ben, f"/api/admin/pages/{pid}/review/request-changes", {"comment": "Bitte genauer."})
        assert r.json()["review"]["status"] == "changes_requested"
        assert r.json()["review"]["comment"] == "Bitte genauer."
        answer = save(anna, pid, "Start", "Zweiter Wurf.")
        assert answer["review"]["status"] == "changes_requested"  # still what anna works on
        assert post(anna, f"/api/admin/pages/{pid}/review/submit").json()["review"]["comment"] == ""
        assert post(ben, f"/api/admin/pages/{pid}/review/approve").status_code == 200
        assert public_text(world, "handbuch", "start").strip() == "Zweiter Wurf."

    def test_discard_throws_the_proposal_away(self, world):
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Lieber doch nicht.")
        assert post(anna, f"/api/admin/pages/{pid}/review/discard").status_code == 200
        assert anna.get(f"/api/admin/pages/{pid}").json()["markdown_content"].strip() == "Der freigegebene Text."
        assert post(anna, f"/api/admin/pages/{pid}/review/submit").json()["detail"] == "nothing_to_review"

    def test_editing_back_to_the_live_text_leaves_nothing_to_review(self, world):
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Kurz anders.")
        answer = save(anna, pid, "Start", "Der freigegebene Text.\n")
        assert answer["review"]["pending"] is False

    def test_a_stale_save_on_the_proposal_is_still_refused(self, world):
        anna, ben = client(world, ANNA), client(world, BEN)
        pid = page_id("handbuch", "start")
        stale = anna.get(f"/api/admin/pages/{pid}").json()
        save(ben, pid, "Start", "Ben war schneller.")
        r = anna.put(
            f"/api/admin/pages/{pid}",
            json={"title": "Start", "markdown_content": "Anna", "category_id": stale["category_id"],
                  "base_revision": stale["revision"]},
            headers=ORIGIN,
        )
        assert r.status_code == 409 and r.json()["detail"] == "page_changed"

    def test_a_rename_moves_the_proposal_along(self, world):
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        answer = save(anna, pid, "Erste Schritte", "Neuer Text.")
        assert (world["content"] / "handbuch/guide/_pending/erste-schritte.md").is_file()
        assert public_text(world, "handbuch", "erste-schritte").strip() == "Der freigegebene Text."
        opened = anna.get(f"/api/admin/pages/{answer['id']}").json()
        assert opened["title"] == "Erste Schritte" and opened["live_title"] == "Start"

    def test_taking_the_page_offline_folds_the_proposal_into_the_draft(self, world):
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Vorschlag.")
        assert anna.post(f"/api/admin/pages/{pid}/publish?published=false", headers=ORIGIN).status_code == 200
        assert not (world["content"] / "handbuch/guide/_pending").exists()
        assert anna.get(f"/api/admin/pages/{pid}").json()["markdown_content"].strip() == "Vorschlag."


class TestADraft:
    def test_publishing_directly_is_refused(self, world):
        anna = client(world, ANNA)
        pid = page_id("handbuch", "entwurf")
        r = anna.post(f"/api/admin/pages/{pid}/publish?published=true", headers=ORIGIN)
        assert r.status_code == 409 and r.json()["detail"] == "review_required"
        assert public_text(world, "handbuch", "entwurf") is None

    def test_an_approval_publishes_it(self, world):
        anna, ben = client(world, ANNA), client(world, BEN)
        pid = page_id("handbuch", "entwurf")
        save(anna, pid, "Entwurf", "Fertig geschrieben.")
        post(anna, f"/api/admin/pages/{pid}/review/submit")
        assert ben.get(f"/api/admin/pages/{pid}/review/diff").json()["live"] is None
        assert post(ben, f"/api/admin/pages/{pid}/review/approve").status_code == 200
        assert public_text(world, "handbuch", "entwurf").strip() == "Fertig geschrieben."
        assert ("published", "entwurf") in world["events"]

    def test_a_new_page_records_its_author(self, world):
        anna = client(world, ANNA)
        category_id = anna.get(f"/api/admin/pages/{page_id('handbuch', 'start')}").json()["category_id"]
        r = anna.post("/api/admin/pages", json={"title": "Neu", "markdown_content": "x", "category_id": category_id},
                      headers=ORIGIN)
        post(anna, f"/api/admin/pages/{r.json()['id']}/review/submit")
        assert post(anna, f"/api/admin/pages/{r.json()['id']}/review/approve").json()["detail"] == "own_change"


class TestAViewer:
    def test_may_approve_and_request_changes_but_not_write(self, world):
        anna, clara = client(world, ANNA), client(world, CLARA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Für Clara.")
        post(anna, f"/api/admin/pages/{pid}/review/submit")
        assert post(clara, f"/api/admin/pages/{pid}/review/submit").status_code == 403
        assert post(clara, f"/api/admin/pages/{pid}/review/withdraw").status_code == 403
        assert post(clara, f"/api/admin/pages/{pid}/review/discard").status_code == 403
        r = post(clara, f"/api/admin/pages/{pid}/review/request-changes", {"comment": "Tippfehler"})
        assert r.status_code == 200
        post(anna, f"/api/admin/pages/{pid}/review/submit")
        assert post(clara, f"/api/admin/pages/{pid}/review/approve").status_code == 200
        assert public_text(world, "handbuch", "start").strip() == "Für Clara."

    def test_the_exception_is_exactly_those_two_paths(self, world):
        clara = client(world, CLARA)
        pid = page_id("handbuch", "start")
        assert post(clara, f"/api/admin/pages/{pid}/review/approve/../../publish").status_code in (403, 404, 405)
        r = clara.put(f"/api/admin/pages/{pid}", json={}, headers=ORIGIN)
        assert r.status_code == 403


class TestWithoutTheSetting:
    def test_nothing_changes(self, world):
        anna = client(world, ANNA)
        pid = page_id("frei", "info")
        answer = save(anna, pid, "Info", "Sofort live.")
        assert answer["review"]["pending"] is False
        assert public_text(world, "frei", "info").strip() == "Sofort live."

    def test_a_review_can_still_be_asked_for_and_leaves_a_note(self, world):
        anna, ben = client(world, ANNA), client(world, BEN)
        pid = page_id("frei", "info")
        save(anna, pid, "Info", "Bitte drüberschauen.")
        post(anna, f"/api/admin/pages/{pid}/review/submit")
        assert post(ben, f"/api/admin/pages/{pid}/review/approve").status_code == 200
        assert pages_store.get_page(page_id("frei", "info"))["reviewed_by"] == "ben"


class TestTheIndex:
    def test_a_reindex_rebuilds_the_queue_from_the_files(self, world):
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Wartet.")
        post(anna, f"/api/admin/pages/{pid}/review/submit")
        with db.get_connection() as conn:
            conn.execute("UPDATE pages SET review_status = '', has_pending = 0")
        content_sync.full_sync()
        assert [e["slug"] for e in page_review.queue()] == ["start"]

    def test_proposals_are_not_pages(self, world):
        anna = client(world, ANNA)
        save(anna, page_id("handbuch", "start"), "Start", "Wartet.")
        slugs = [p["slug"] for p in client(world).get("/api/public/projects/handbuch/nav").json().get("pages", [])]
        assert "_pending" not in str(slugs)
        assert len(page_review.queue()) == 0  # saved, not submitted


class TestMcp:
    TOKEN = {"name": "assistent", "scope": "write"}

    def test_an_assistant_edit_of_a_live_page_is_submitted(self, world):
        result = mcp_tools.update_page(
            {"project": "handbuch", "page": "start", "markdown": "Vom Assistenten."}, self.TOKEN
        )
        assert result["review"] == "pending"
        assert public_text(world, "handbuch", "start").strip() == "Der freigegebene Text."
        # A person approves it -- any person: the assistant wrote it.
        pid = page_id("handbuch", "start")
        assert post(client(world, ANNA), f"/api/admin/pages/{pid}/review/approve").status_code == 200

    def test_an_assistant_cannot_publish_a_new_page_directly(self, world):
        result = mcp_tools.create_page(
            {"project": "handbuch", "category": "guide", "title": "KI-Seite", "markdown": "x", "published": True},
            self.TOKEN,
        )
        assert result["page"]["published"] is False and result["review"] == "pending"
