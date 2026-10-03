"""The in-container maintenance commands behind `docuwaves reset-password`
and `docuwaves backup` (app/cli.py)."""
import io
import sqlite3

import pytest

from app import cli
from app.services import db, session_registry_store, users_store
from app.settings import settings


@pytest.fixture
def instance(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "docuwaves.db"))
    db.init_schema()
    users_store.create_first_admin("test-claude", "first-password")
    return tmp_path


def test_reset_password_from_stdin(instance, monkeypatch, capsys):
    session_registry_store.create("s1", "test-claude", "10.0.0.1", "test")
    monkeypatch.setattr("sys.stdin", io.StringIO("a-new-password\n"))
    assert cli.main(["reset-password", "test-claude"]) == 0
    assert users_store.verify_credentials("test-claude", "a-new-password")
    assert not users_store.verify_credentials("test-claude", "first-password")
    assert not session_registry_store.exists("s1")
    out = capsys.readouterr().out
    assert "a-new-password" not in out
    assert "1 session(s) signed out" in out


def test_reset_password_refuses_a_short_one(instance, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    assert cli.main(["reset-password", "test-claude"]) == 1
    assert users_store.verify_credentials("test-claude", "first-password")


def test_reset_password_names_the_accounts_there_are(instance, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("a-new-password\n"))
    assert cli.main(["reset-password", "nobody"]) == 1
    assert "test-claude" in capsys.readouterr().err


def test_users(instance, capsys):
    assert cli.main(["users"]) == 0
    assert capsys.readouterr().out == "test-claude\tadmin\n"


def test_snapshot_is_a_working_database(instance):
    target = instance / "backup" / "snapshot.db"
    assert cli.main(["snapshot-db", str(target)]) == 0
    copy = sqlite3.connect(target)
    try:
        assert copy.execute("SELECT username FROM auth").fetchall() == [("test-claude",)]
    finally:
        copy.close()


def test_snapshot_refuses_postgres(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "database_url", "postgresql://example/docuwaves")
    assert cli.main(["snapshot-db", str(tmp_path / "x.db")]) == 2
