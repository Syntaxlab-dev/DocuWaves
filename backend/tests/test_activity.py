"""The admin activity feed (services/activity.py): commits to the content
repo with their author, message and the pages they touched."""
import importlib

import git
import pytest
from fastapi.testclient import TestClient

from app.services import (
    activity,
    changelog,
    content_sync,
    content_versions,
    db,
    git_content_repo,
    search_suggest,
    session_secret,
    users_store,
)
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def page(title):
    return f"---\norder: 1\npublished: true\ntitle: {title}\n---\n\nText.\n"


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    repository = git.Repo.init(repo_dir)

    def commit(message, author, files):
        for path, text in files.items():
            write(content, path, text)
        repository.index.add([f"content/{p}" for p in files])
        actor = git.Actor(author, f"{author}@example.com")
        repository.index.commit(message, author=actor, committer=actor)

    commit("Add project", "Alex", {
        "docs/_project.yml": "name: Docs\n",
        "docs/guide/_category.yml": "name: Guide\n",
        "docs/guide/start.md": page("Start"),
    })
    commit("Update page: Start", "Kim", {"docs/guide/start.md": page("Start here")})
    commit("Propose changes: Start", "Sam", {"docs/guide/_pending/start.md": page("Start (new)")})

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


class TestFeed:
    def test_newest_first_with_author_and_message(self, world):
        entries = activity.recent()
        assert [(e["author"], e["message"]) for e in entries] == [
            ("Sam", "Propose changes: Start"),
            ("Kim", "Update page: Start"),
            ("Alex", "Add project"),
        ]

    def test_pages_are_named_with_their_current_title(self, world):
        update = activity.recent()[1]
        assert update["pages"] == [{
            "project_slug": "docs", "project_name": "Docs", "version": "", "slug": "start", "language": "",
            "pending": False, "title": "Start here", "status": "M",
        }]

    def test_a_proposal_is_marked(self, world):
        assert activity.recent()[0]["pages"][0]["pending"] is True

    def test_project_files_are_counted_not_listed(self, world):
        first = activity.recent()[2]
        assert [p["slug"] for p in first["pages"]] == ["start"] and first["other_files"] == 2

    def test_limit(self, world):
        assert len(activity.recent(1)) == 1


class TestApi:
    def test_signed_in(self, world):
        app = importlib.import_module("app.main").app
        c = TestClient(app)
        assert c.get("/api/admin/activity").status_code == 401
        c.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-123"}, headers=ORIGIN)
        r = c.get("/api/admin/activity?limit=2")
        assert r.status_code == 200 and len(r.json()["entries"]) == 2
