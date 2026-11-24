"""Renaming a page keeps its old address working: `_redirects.yml` in the
content repo, the public API's 301, and the server-side 301 for the reading
URL (services/page_redirects.py)."""
import importlib

import git
import pytest
from fastapi.testclient import TestClient

from app.services import (
    changelog,
    content_sync,
    content_versions,
    db,
    git_content_repo,
    page_redirects,
    pages_store,
    search_suggest,
    seo,
    session_secret,
    users_store,
)
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


# ---- The map itself ----

@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "content_repo_path", str(tmp_path / "repo"))
    monkeypatch.setattr(content_versions, "_cache", {})
    (tmp_path / "repo" / "content" / "docs").mkdir(parents=True)
    return "docs"


class TestMap:
    def test_a_rename_is_recorded(self, project):
        assert page_redirects.record_rename(project, "install", "installation") == ["content/docs/_redirects.yml"]
        assert page_redirects.read(project) == {"install": "installation"}
        assert page_redirects.resolve(project, "install") == "installation"

    def test_renaming_again_keeps_one_hop(self, project):
        page_redirects.record_rename(project, "a", "b")
        page_redirects.record_rename(project, "b", "c")
        assert page_redirects.read(project) == {"a": "c", "b": "c"}

    def test_taking_a_slug_back_removes_its_redirect(self, project):
        page_redirects.record_rename(project, "a", "b")
        page_redirects.record_rename(project, "b", "a")
        assert page_redirects.read(project) == {"b": "a"}

    def test_no_change_writes_nothing(self, project):
        assert page_redirects.record_rename(project, "a", "a") == []
        assert page_redirects.read(project) == {}

    def test_a_hand_written_loop_ends(self, project, tmp_path):
        write(tmp_path / "repo" / "content", "docs/_redirects.yml", "pages:\n  a: b\n  b: a\n")
        assert page_redirects.resolve(project, "a") in ("a", "b", None)

    def test_a_broken_file_means_no_redirects(self, project, tmp_path):
        write(tmp_path / "repo" / "content", "docs/_redirects.yml", "pages: [unclosed\n")
        assert page_redirects.read(project) == {}


# ---- A rename through the app ----

def page(title, body):
    return f"---\norder: 1\npublished: true\ntitle: {title}\n---\n\n{body}\n"


@pytest.fixture
def app(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    write(content, "docs/_project.yml", "name: Docs\n")
    write(content, "docs/guide/_category.yml", "name: Guide\n")
    write(content, "docs/guide/install.md", page("Install", "How to install."))
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
    return importlib.import_module("app.main").app


def rename(app, new_title):
    c = TestClient(app)
    c.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-123"}, headers=ORIGIN)
    project = c.get("/api/public/projects").json()["projects"][0]
    current = pages_store.resolve_page(project["id"], "install", "", published_only=True, version="")
    r = c.put(
        f"/api/admin/pages/{current['id']}",
        json={"title": new_title, "markdown_content": current["markdown_content"], "category_id": current["category_id"]},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestRename:
    def test_the_old_api_address_redirects(self, app):
        assert rename(app, "Installation")["slug"] == "installation"
        c = TestClient(app)
        r = c.get("/api/public/projects/docs/pages/install", follow_redirects=False)
        assert r.status_code == 301
        assert r.headers["location"].endswith("/api/public/projects/docs/pages/installation")
        assert c.get("/api/public/projects/docs/pages/install").json()["page"]["slug"] == "installation"

    def test_the_old_reading_url_gets_a_real_301(self, app):
        rename(app, "Installation")
        assert seo.page_redirect("p/docs/pages/install") == "/p/docs/pages/installation"
        assert seo.page_redirect("p/docs/pages/installation") is None
        assert seo.page_redirect("p/docs/pages/never-existed") is None

    def test_the_redirect_is_in_the_rename_commit(self, app, tmp_path):
        rename(app, "Installation")
        repository = git.Repo(tmp_path / "repo")
        changed = repository.head.commit.stats.files
        assert "content/docs/_redirects.yml" in changed
        assert (tmp_path / "repo/content/docs/_redirects.yml").read_text().count("install: installation") == 1

    def test_unknown_slugs_still_404(self, app):
        assert TestClient(app).get("/api/public/projects/docs/pages/nope").status_code == 404
