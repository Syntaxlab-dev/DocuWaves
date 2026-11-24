"""Demo mode (services/demo.py): what a visitor could misuse is refused,
everything an author does still works, and demo-seed fills an empty
instance."""
import importlib

import pytest
from fastapi.testclient import TestClient

from app import cli
from app.services import demo, projects_store, users_store
from app.settings import settings

from tests.test_gap_drafts import ORIGIN, world  # noqa: F401 -- the fixture


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "demo_username", "demo")
    monkeypatch.setattr(settings, "demo_password", "demo-passwort-123")


@pytest.mark.parametrize(
    ("method", "path", "refused"),
    [
        ("POST", "/api/auth/password", True),
        ("PUT", "/api/auth/notifications", True),
        ("POST", "/api/auth/notifications/test", True),
        ("POST", "/api/auth/mfa/totp/setup", True),
        ("POST", "/api/admin/users", True),
        ("DELETE", "/api/admin/users/someone", True),
        ("POST", "/api/admin/tokens", True),
        ("POST", "/api/admin/import/git/preview", True),
        ("POST", "/api/sync/docs", True),
        ("GET", "/api/admin/users", False),
        ("POST", "/api/auth/login", False),
        ("POST", "/api/admin/pages", False),
        ("POST", "/api/admin/import", False),
    ],
)
def test_what_is_refused(demo_on, method, path, refused):
    assert demo.blocked(method, path) is refused


def test_off_by_default(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    assert not demo.blocked("POST", "/api/auth/password")
    assert demo.public_status() == {"enabled": False}


def test_the_api_refuses_and_the_site_shows_the_login(world, demo_on):
    c = TestClient(importlib.import_module("app.main").app)
    c.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-123"}, headers=ORIGIN)
    r = c.post("/api/admin/tokens", json={"name": "x"}, headers=ORIGIN)
    assert r.status_code == 403 and "demo" in r.json()["detail"]
    site = c.get("/api/public/site").json()
    assert site["demo"] == {"enabled": True, "username": "demo", "password": "demo-passwort-123"}
    assert site["sign_in"] is True


def test_seed_fills_an_empty_instance_once(world, demo_on, tmp_path, monkeypatch):
    # The world fixture already has accounts and a project: seeding leaves it alone.
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "start.md").write_text("# Start\n\nHallo.\n")
    assert cli.main(["demo-seed", str(docs)]) == 0
    assert users_store.get_user("demo") is None
    assert projects_store.get_project_by_slug("docs")["name"] == "Docs"  # the fixture's own project


def test_seed_needs_demo_mode(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(settings, "demo_mode", False)
    assert cli.main(["demo-seed", str(tmp_path)]) == 1
    assert "DEMO_MODE" in capsys.readouterr().err


def test_seed_an_empty_instance(tmp_path, monkeypatch, demo_on):
    from app.services import changelog, content_versions, git_content_repo, session_secret

    monkeypatch.setattr(settings, "content_repo_path", str(tmp_path / "repo"))
    monkeypatch.setattr(settings, "content_repo_url", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "index.db"))
    monkeypatch.setattr(settings, "webhook_urls", ())
    monkeypatch.setattr(session_secret, "_SECRET_PATH", tmp_path / ".session_secret")
    monkeypatch.setattr(content_versions, "_cache", {})
    monkeypatch.setattr(changelog, "_cache", None)
    monkeypatch.setattr(git_content_repo, "_repo", None)
    monkeypatch.setattr(git_content_repo, "_mode", git_content_repo._mode)
    git_content_repo._read_cache.clear()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "start.md").write_text("# Start\n\nHallo.\n")

    assert cli.main(["demo-seed", str(docs), "--name", "Demo-Doku"]) == 0
    assert users_store.get_user("demo")["role"] == "admin"
    project = projects_store.get_project_by_slug("docs")
    assert project["name"] == "Demo-Doku"
    # Run again on every start: nothing doubles.
    assert cli.main(["demo-seed", str(docs)]) == 0
    assert len(projects_store.list_projects()) == 1
    git_content_repo._read_cache.clear()
