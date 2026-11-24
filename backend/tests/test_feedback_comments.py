"""The optional note after "Was this helpful?" (services/page_feedback_store.py):
only for the vote just cast, only once, within an hour, read by editors only."""
import importlib
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.services import db, page_feedback_store
from app.settings import settings

from tests.test_gap_drafts import ORIGIN, world  # noqa: F401 -- the fixture

VOTE = {"project": "docs", "page": "backups", "helpful": False}


def client() -> TestClient:
    return TestClient(importlib.import_module("app.main").app)


def vote(c, **extra):
    r = c.post("/api/public/feedback", json={**VOTE, **extra})
    assert r.status_code == 200
    return r.json()


def test_a_note_goes_with_the_vote(world):
    c = client()
    answer = vote(c)
    assert answer["recorded"] and answer["id"] and answer["key"]
    r = c.post("/api/public/feedback/comment", json={"id": answer["id"], "key": answer["key"],
                                                    "comment": "  Schritt 3   klappt\n\n nicht unter Windows "})
    assert r.status_code == 200
    notes = page_feedback_store.comments("docs")
    assert notes[0]["comment"] == "Schritt 3 klappt\nnicht unter Windows" and notes[0]["helpful"] is False
    assert page_feedback_store.summary("docs")[0]["comments"] == 1


def test_only_once_and_only_with_the_key(world):
    c = client()
    answer = vote(c)
    wrong = c.post("/api/public/feedback/comment", json={"id": answer["id"], "key": "0" * 32, "comment": "x"})
    assert wrong.status_code == 409
    other = vote(c)
    stolen = c.post("/api/public/feedback/comment", json={"id": other["id"], "key": answer["key"], "comment": "x"})
    assert stolen.status_code == 409
    ok = c.post("/api/public/feedback/comment", json={**answer, "comment": "eins"})
    again = c.post("/api/public/feedback/comment", json={**answer, "comment": "zwei"})
    assert ok.status_code == 200 and again.status_code == 409
    empty = c.post("/api/public/feedback/comment", json={**other, "comment": "   "})
    assert empty.status_code == 409


def test_not_after_an_hour(world):
    c = client()
    answer = vote(c)
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with db.get_connection() as conn:
        conn.execute("UPDATE page_feedback SET created_at = ?", (old,))
    r = c.post("/api/public/feedback/comment", json={**answer, "comment": "spät"})
    assert r.status_code == 409


def test_long_notes_are_cut(world):
    c = client()
    answer = vote(c)
    c.post("/api/public/feedback/comment", json={**answer, "comment": "a" * 3000})
    assert len(page_feedback_store.comments()[0]["comment"]) == page_feedback_store.COMMENT_MAX


def test_switched_off(world, monkeypatch):
    monkeypatch.setattr(settings, "feedback_comments", False)
    c = client()
    answer = vote(c)
    assert answer == {"recorded": True}
    key = page_feedback_store.comment_key(1)
    assert c.post("/api/public/feedback/comment", json={"id": 1, "key": key, "comment": "x"}).status_code == 404


def test_editors_read_them_readers_do_not(world):
    c = client()
    answer = vote(c)
    c.post("/api/public/feedback/comment", json={**answer, "comment": "Fehlt ein Beispiel."})
    assert c.get("/api/admin/feedback/comments").status_code == 401
    c.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-123"}, headers=ORIGIN)
    notes = c.get("/api/admin/feedback/comments?project=docs&page=backups").json()["comments"]
    assert [n["comment"] for n in notes] == ["Fehlt ein Beispiel."]
    # Clearing a page's votes forgets its notes too.
    c.delete("/api/admin/feedback/docs/backups", headers=ORIGIN)
    assert c.get("/api/admin/feedback/comments").json()["comments"] == []
