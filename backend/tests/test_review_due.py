"""`review_every: <days>` in a project's _project.yml and the list of pages
due for a review (services/review_due.py)."""
import importlib
from datetime import date

import git
import pytest
from fastapi.testclient import TestClient

from app.services import (
    changelog,
    content_files,
    content_sync,
    content_versions,
    db,
    git_content_repo,
    projects_store,
    review_due,
    search_suggest,
    session_secret,
    users_store,
)
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}
TODAY = date(2026, 11, 24)


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def page(title, reviewed_at="", published=True):
    note = f"reviewed_by: Alex\nreviewed_at: '{reviewed_at}'\n" if reviewed_at else ""
    return f"---\norder: 1\npublished: {str(published).lower()}\ntitle: {title}\n{note}---\n\nText.\n"


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    write(content, "docs/_project.yml", "name: Docs\nreview_every: 90\n")
    write(content, "docs/guide/_category.yml", "name: Guide\n")
    write(content, "docs/guide/fresh.md", page("Fresh", "2026-11-01"))
    write(content, "docs/guide/old.md", page("Old", "2026-06-01"))
    write(content, "docs/guide/never.md", page("Never"))
    write(content, "docs/guide/draft.md", page("Draft", published=False))
    write(content, "other/_project.yml", "name: Other\n")
    write(content, "other/guide/_category.yml", "name: Guide\n")
    write(content, "other/guide/never.md", page("Other never"))
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
    monkeypatch.setattr(content_versions, "_cache", {})
    search_suggest._correct_word.cache_clear()

    db.init_schema()
    content_sync.full_sync()
    users_store.create_first_admin("chef", "chef-passwort-123")
    return tmp_path


class TestDue:
    def test_never_reviewed_first_then_overdue(self, world):
        due = review_due.due_pages(TODAY)
        assert [p["title"] for p in due] == ["Never", "Old"]
        assert due[0]["days_overdue"] is None
        assert due[1]["days_overdue"] == (TODAY - date(2026, 6, 1)).days - 90
        # Enough for the admin's overview to open the page in the editor.
        assert all(p["category_id"] > 0 for p in due)

    def test_a_recent_note_is_not_due_until_it_is(self, world):
        assert "Fresh" not in [p["title"] for p in review_due.due_pages(TODAY)]
        assert "Fresh" in [p["title"] for p in review_due.due_pages(date(2027, 1, 30))]

    def test_projects_without_the_setting_are_left_alone(self, world):
        assert all(p["project_slug"] == "docs" for p in review_due.due_pages(TODAY))


class TestSetting:
    def test_read_from_the_project_file(self, world):
        assert projects_store.get_project_by_slug("docs")["review_every_days"] == 90
        assert projects_store.get_project_by_slug("other")["review_every_days"] == 0

    def test_a_rewrite_that_does_not_mention_it_keeps_it(self, world):
        project = projects_store.get_project_by_slug("docs")
        projects_store.reorder_project(project["id"], 1, "Test")
        assert content_files.review_every_days("docs") == 90

    def test_nonsense_is_off(self, world):
        write(world / "repo" / "content", "other/_project.yml", "name: Other\nreview_every: soon\n")
        assert content_files.review_every_days("other") == 0


class TestApi:
    def client(self):
        app = importlib.import_module("app.main").app
        c = TestClient(app)
        c.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-123"}, headers=ORIGIN)
        return c

    def test_the_list(self, world):
        r = self.client().get("/api/admin/review-due")
        assert r.status_code == 200 and r.json()["count"] == 2

    def test_the_form_sets_and_clears_it(self, world):
        c = self.client()
        other = projects_store.get_project_by_slug("other")
        body = {"name": "Other", "icon": "", "color": "", "description": "", "review_every_days": 30}
        assert c.put(f"/api/admin/projects/{other['id']}", json=body, headers=ORIGIN).status_code == 200
        assert "review_every: 30" in (world / "repo/content/other/_project.yml").read_text()
        body["review_every_days"] = 0
        c.put(f"/api/admin/projects/{other['id']}", json=body, headers=ORIGIN)
        assert "review_every" not in (world / "repo/content/other/_project.yml").read_text()

    def test_needs_a_session(self, world):
        app = importlib.import_module("app.main").app
        assert TestClient(app).get("/api/admin/review-due").status_code == 401
