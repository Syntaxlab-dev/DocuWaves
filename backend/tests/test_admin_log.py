"""The admin log (services/admin_log.py): every change to the instance is
written down, readably where the endpoint knows how, generically where it
does not -- and never with a password or a token value in it."""
import importlib

import pytest
from fastapi.testclient import TestClient

from app import auth_guard
from app.services import admin_log, db, session_secret, users_store
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}
SECRET_PASSWORD = "geheim-passwort-987"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "index.db"))
    monkeypatch.setattr(session_secret, "_SECRET_PATH", tmp_path / ".session_secret")
    db.init_schema()
    users_store.create_first_admin("chef", "chef-passwort-123")
    users_store.create_user("anna", "anna-passwort-123", users_store.EDITOR)
    return importlib.import_module("app.main").app


def signed_in(app, name="chef", password="chef-passwort-123"):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": name, "password": password}, headers=ORIGIN).status_code == 200
    return c


def log(c):
    return c.get("/api/admin/log").json()["entries"]


def test_account_changes_are_written_down(app):
    c = signed_in(app)
    assert c.post("/api/admin/users", json={"username": "bert", "password": SECRET_PASSWORD, "role": "viewer"}, headers=ORIGIN).status_code == 201
    assert c.put("/api/admin/users/bert/role", json={"role": "editor"}, headers=ORIGIN).status_code == 200
    assert c.put("/api/admin/users/bert/password", json={"password": SECRET_PASSWORD + "x"}, headers=ORIGIN).status_code == 200
    assert c.delete("/api/admin/users/bert", headers=ORIGIN).status_code == 200
    entries = log(c)
    assert [(e["action"], e["target"]) for e in entries] == [
        ("account.delete", "bert"),
        ("account.password_reset", "bert"),
        ("account.role", "bert"),
        ("account.create", "bert"),
    ]
    assert entries[2]["detail"] == "viewer -> editor"
    assert all(e["actor"] == "chef" for e in entries)
    assert SECRET_PASSWORD not in str(entries)


def test_a_token_is_logged_by_name_never_by_value(app):
    c = signed_in(app)
    made = c.post("/api/admin/tokens", json={"name": "CI", "scope": "read"}, headers=ORIGIN).json()
    assert c.delete(f"/api/admin/tokens/{made['id']}", headers=ORIGIN).status_code == 200
    entries = log(c)
    assert [(e["action"], e["target"]) for e in entries] == [("token.revoke", "CI"), ("token.create", "CI")]
    assert made["token"] not in str(entries)


def test_a_refused_change_is_not_logged(app):
    c = signed_in(app)
    assert c.delete("/api/admin/users/chef", headers=ORIGIN).status_code == 400
    assert log(c) == []


def test_only_admins_read_it(app):
    assert signed_in(app, "anna", "anna-passwort-123").get("/api/admin/log").status_code == 403
    assert "/api/admin/log".startswith(auth_guard._ADMIN_ONLY_PREFIXES)


def test_the_middleware_catches_what_an_endpoint_forgot(app, monkeypatch):
    """A route that records nothing still leaves a generic entry."""
    from app.routers import users

    class Forgetful:
        @staticmethod
        def record(*a, **k):
            pass

    # The router's reference only: the middleware keeps the real module.
    monkeypatch.setattr(users, "admin_log", Forgetful)
    c = signed_in(app)
    assert c.post("/api/admin/users/anna/mfa/reset", headers=ORIGIN).status_code == 200
    entries = log(c)
    assert [(e["action"], e["actor"]) for e in entries] == [("POST /api/admin/users/anna/mfa/reset", "chef")]


def test_reading_is_not_logged(app):
    c = signed_in(app)
    c.get("/api/admin/users")
    c.get("/api/admin/tokens")
    assert log(c) == []


def test_it_keeps_the_newest_entries_only(app, monkeypatch):
    monkeypatch.setattr(admin_log, "MAX_ENTRIES", 3)
    for i in range(5):
        admin_log.record(None, "test", str(i))
    assert [e["target"] for e in admin_log.entries()] == ["4", "3", "2"]


def test_paging(app):
    for i in range(5):
        admin_log.record(None, "test", str(i))
    first = admin_log.entries(limit=2)
    assert [e["target"] for e in first] == ["4", "3"]
    assert [e["target"] for e in admin_log.entries(limit=2, before=first[-1]["id"])] == ["2", "1"]
