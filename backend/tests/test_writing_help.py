"""Writing help in the editor (services/writing_help.py), the model call
faked: the selection goes in, the suggestion comes back, nothing is saved."""
import importlib

import pytest
from fastapi.testclient import TestClient

from app.services import doc_chat, writing_help

from tests.test_gap_drafts import ORIGIN, world  # noqa: F401 -- the fixture


@pytest.fixture
def model(monkeypatch):
    calls = []

    def fake_post(messages, max_tokens=600):
        calls.append(messages)
        return "```markdown\nKürzer gesagt: [Backups](/p/docs/pages/backups) laufen nachts.\n```"

    monkeypatch.setattr(doc_chat, "_post_chat", fake_post)
    monkeypatch.setattr(doc_chat, "is_enabled", lambda: True)
    return calls


class TestRewrite:
    def test_fence_removed_and_the_selection_shape_kept(self, model):
        result = writing_help.rewrite("Die Backups laufen jede Nacht.", "shorten", "de")
        assert result == "Kürzer gesagt: [Backups](/p/docs/pages/backups) laufen nachts."
        system, user = model[0]
        assert "shorter" in system["content"] and "German" in system["content"]
        assert "ONLY what the text says" in system["content"]
        assert user["content"] == "Die Backups laufen jede Nacht."

    def test_a_selection_ending_in_a_newline_keeps_it(self, model):
        assert writing_help.rewrite("Absatz.\n", "fix", "de").endswith("\n")

    @pytest.mark.parametrize(
        ("text", "action", "code"),
        [("x", "poem", "unknown_action"), ("  ", "fix", "empty_question"), ("x" * 8001, "fix", "too_long")],
    )
    def test_refused(self, model, text, action, code):
        with pytest.raises(doc_chat.ChatError, match=code):
            writing_help.rewrite(text, action, "de")
        assert model == []

    def test_not_configured(self, monkeypatch):
        monkeypatch.setattr(doc_chat, "is_enabled", lambda: False)
        with pytest.raises(doc_chat.ChatError, match="not_configured"):
            writing_help.rewrite("Text", "rephrase", "de")


class TestApi:
    def login(self, user):
        c = TestClient(importlib.import_module("app.main").app)
        c.post("/api/auth/login", json={"username": user[0], "password": user[1]}, headers=ORIGIN)
        return c

    def test_editor_gets_a_suggestion(self, world, model):
        c = self.login(("chef", "chef-passwort-123"))
        r = c.post("/api/admin/writing-help", json={"text": "Lang.", "action": "shorten"}, headers=ORIGIN)
        assert r.status_code == 200 and r.json()["text"].startswith("Kürzer gesagt")

    def test_a_viewer_cannot(self, world, model):
        c = self.login(("leser", "leser-passwort-123"))
        r = c.post("/api/admin/writing-help", json={"text": "x", "action": "fix"}, headers=ORIGIN)
        assert r.status_code == 403 and model == []

    def test_errors(self, world, model, monkeypatch):
        c = self.login(("chef", "chef-passwort-123"))
        assert c.post("/api/admin/writing-help", json={"text": "x", "action": "poem"}, headers=ORIGIN).status_code == 400
        monkeypatch.setattr(doc_chat, "is_enabled", lambda: False)
        r = c.post("/api/admin/writing-help", json={"text": "x", "action": "fix"}, headers=ORIGIN)
        assert r.status_code == 409 and r.json()["detail"] == "not_configured"
