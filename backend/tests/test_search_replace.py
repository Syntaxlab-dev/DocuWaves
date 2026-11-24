"""Search and replace across a project (services/search_replace.py), end to
end: a real content repo, a real index, the real endpoints."""
import importlib

import git
import pytest
from fastapi.testclient import TestClient

from app.services import (
    content_sync,
    content_versions,
    db,
    git_content_repo,
    pages_store,
    projects_store,
    search_replace,
    session_secret,
    users_store,
)
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def page(title, body, published=True):
    return f"---\norder: 1\npublished: {'true' if published else 'false'}\ntitle: {title}\n---\n\n{body}\n"


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    write(content, "docs/_project.yml", "name: Docs\n")
    write(content, "docs/guide/_category.yml", "name: Guide\n")
    write(content, "docs/guide/intro.md", page("Intro", "Install WaveDocs. WaveDocs is fast. wavedocs-cli too."))
    write(content, "docs/guide/setup.md", page("Setup", "Run WaveDocs once.", published=False))
    write(content, "docs/guide/other.md", page("Other", "Nothing to see."))
    write(content, "strict/_project.yml", "name: Strict\nreview: required\n")
    write(content, "strict/guide/_category.yml", "name: Guide\n")
    write(content, "strict/guide/live.md", page("Live", "WaveDocs is live."))
    repository = git.Repo.init(repo_dir)
    repository.index.add([str(p.relative_to(repo_dir)) for p in content.rglob("*") if p.is_file()])
    actor = git.Actor("Test", "t@example.com")
    repository.index.commit("Inhalt", author=actor, committer=actor)

    monkeypatch.setattr(settings, "content_repo_path", str(repo_dir))
    monkeypatch.setattr(settings, "content_repo_url", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "index.db"))
    monkeypatch.setattr(settings, "webhook_urls", ())
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(session_secret, "_SECRET_PATH", tmp_path / ".session_secret")
    monkeypatch.setattr(git_content_repo, "_read_repo", lambda: repository)
    monkeypatch.setattr(git_content_repo, "_repo", repository)
    monkeypatch.setattr(git_content_repo, "_mode", git_content_repo.LOCAL)
    monkeypatch.setattr(content_versions, "_cache", {})
    git_content_repo._read_cache.clear()

    db.init_schema()
    content_sync.full_sync()
    users_store.create_first_admin("chef", "chef-passwort-123")
    app = importlib.import_module("app.main").app
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-123"}, headers=ORIGIN).status_code == 200
    return c


def project_id(slug="docs"):
    return next(p for p in projects_store.list_projects() if p["slug"] == slug)["id"]


def preview(c, find, slug="docs", **kw):
    r = c.post(f"/api/admin/projects/{project_id(slug)}/replace/preview", json={"find": find, **kw}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()


def apply(c, find, replace, pages, slug="docs", **kw):
    return c.post(
        f"/api/admin/projects/{project_id(slug)}/replace",
        json={"find": find, "replace": replace, "pages": pages, **kw},
        headers=ORIGIN,
    )


def body(slug, project="docs"):
    return pages_store.get_page_by_slug(project_id(project), slug, "", "")["markdown_content"]


class TestPreview:
    def test_lists_pages_with_matches_and_context(self, world):
        got = preview(world, "WaveDocs")
        by_slug = {p["slug"]: p for p in got["pages"]}
        assert set(by_slug) == {"intro", "setup"}
        assert by_slug["intro"]["count"] == 3  # case-insensitive by default, wavedocs-cli included
        assert got["total"] == 4
        assert by_slug["intro"]["snippets"][0] == {"before": "Install ", "match": "WaveDocs", "after": ". WaveDocs is fast. wavedocs-cli too."}

    def test_case_and_whole_word(self, world):
        assert preview(world, "WaveDocs", case_sensitive=True)["total"] == 3
        assert preview(world, "Wave", whole_word=True)["total"] == 0
        assert preview(world, "C++", whole_word=True)["total"] == 0

    def test_it_is_plain_text_not_a_regular_expression(self, world):
        assert preview(world, "Wave.ocs")["total"] == 0

    @pytest.mark.parametrize("find", ["", "   ", "x" * 201])
    def test_refuses_empty_or_huge(self, world, find):
        r = world.post(f"/api/admin/projects/{project_id()}/replace/preview", json={"find": find}, headers=ORIGIN)
        assert r.status_code == 400


class TestApply:
    def test_replaces_in_the_chosen_pages_as_one_commit(self, world):
        found = preview(world, "WaveDocs", case_sensitive=True)
        intro = next(p for p in found["pages"] if p["slug"] == "intro")
        before = git_content_repo._repo.head.commit
        r = apply(world, "WaveDocs", "DocuWaves", {intro["id"]: intro["revision"]}, case_sensitive=True)
        assert r.status_code == 200, r.text
        assert r.json()["replacements"] == 2
        assert body("intro") == "Install DocuWaves. DocuWaves is fast. wavedocs-cli too."
        assert body("setup") == "Run WaveDocs once."  # not ticked
        head = git_content_repo._repo.head.commit
        assert head.parents == (before,) and head.message.startswith('Replace "WaveDocs" with "DocuWaves" in 1 page')
        assert head.author.name == "chef"

    def test_several_pages_one_commit(self, world):
        found = preview(world, "WaveDocs")
        before = git_content_repo._repo.head.commit
        r = apply(world, "WaveDocs", "DocuWaves", {p["id"]: p["revision"] for p in found["pages"]})
        assert len(r.json()["done"]) == 2
        assert git_content_repo._repo.head.commit.parents == (before,)
        assert "in 2 pages" in git_content_repo._repo.head.commit.message

    def test_the_replacement_is_literal(self, world):
        found = preview(world, "once")
        p = found["pages"][0]
        apply(world, "once", r"\1 twice", {p["id"]: p["revision"]})
        assert body("setup") == r"Run WaveDocs \1 twice."

    def test_a_page_saved_since_the_preview_is_skipped(self, world):
        found = preview(world, "WaveDocs")
        intro = next(p for p in found["pages"] if p["slug"] == "intro")
        current = pages_store.get_page(intro["id"])
        pages_store.update_page(intro["id"], "Intro", "intro", "WaveDocs, rewritten.", current["category_id"], "someone")
        r = apply(world, "WaveDocs", "DocuWaves", {intro["id"]: intro["revision"]}).json()
        assert r["done"] == [] and r["skipped"] == [{"id": intro["id"], "reason": "changed"}]
        assert body("intro") == "WaveDocs, rewritten."

    def test_a_page_of_another_project_is_not_touched(self, world):
        other = preview(world, "WaveDocs", slug="strict")["pages"][0]
        r = apply(world, "WaveDocs", "X", {other["id"]: other["revision"]}).json()
        assert r["skipped"] == [{"id": other["id"], "reason": "not_found"}]

    def test_a_live_page_in_an_approval_project_gets_a_proposal(self, world):
        found = preview(world, "WaveDocs", slug="strict")
        live = found["pages"][0]
        assert live["becomes_proposal"]
        r = apply(world, "WaveDocs", "DocuWaves", {live["id"]: live["revision"]}, slug="strict").json()
        assert r["done"] == [{"id": live["id"], "count": 1, "proposal": True}]
        assert body("live", "strict") == "WaveDocs is live."  # readers keep the live text
        again = preview(world, "DocuWaves", slug="strict")["pages"][0]
        assert again["proposal"] and again["count"] == 1

    def test_a_viewer_may_not(self, world):
        users_store.create_user("leser", "leser-passwort-123", "viewer")
        c = TestClient(importlib.import_module("app.main").app)
        c.post("/api/auth/login", json={"username": "leser", "password": "leser-passwort-123"}, headers=ORIGIN)
        r = c.post(f"/api/admin/projects/{project_id()}/replace/preview", json={"find": "x"}, headers=ORIGIN)
        assert r.status_code == 403


def test_whole_word_next_to_punctuation():
    pattern = search_replace.compile_pattern("C++", True, True)
    assert pattern.findall("C++ and C++11 and xC++") == ["C++", "C++"]
