"""Translation drafts (services/translation_drafts.py), the model call faked:
code never reaches the model, a long page goes in sections, nothing is
saved."""
import importlib

import pytest
from fastapi.testclient import TestClient

from app.services import doc_chat, translation_drafts

from tests.test_gap_drafts import ORIGIN, world  # noqa: F401 -- the fixture

PAGE = """Run the backup:

```bash
docuwaves backup --to /srv
```

Then check `docuwaves status`. See [Restore](/p/docs/pages/restore).
"""


@pytest.fixture
def model(monkeypatch):
    calls = []

    def fake_post(messages, max_tokens=600):
        text = messages[1]["content"]
        calls.append(messages)
        # A "translation" that keeps the placeholders, as told.
        return "```markdown\n" + text.replace("Run the backup", "Starte das Backup").replace("Then check", "Dann prüfe") + "\n```"

    monkeypatch.setattr(doc_chat, "_post_chat", fake_post)
    monkeypatch.setattr(doc_chat, "is_enabled", lambda: True)
    return calls


def test_code_is_kept_away_from_the_model(model):
    result = translation_drafts.draft("Backups", PAGE, "en", "de")
    assert "Starte das Backup:" in result["markdown"]
    assert "```bash\ndocuwaves backup --to /srv\n```" in result["markdown"]
    assert "Dann prüfe `docuwaves status`." in result["markdown"]
    assert result["missing_code"] == 0
    sent = model[0][1]["content"]
    assert "docuwaves backup" not in sent and "docuwaves status" not in sent
    assert "English to German" in model[0][0]["content"]
    assert result["title"] == "Backups"


def test_a_dropped_placeholder_brings_the_code_back(monkeypatch):
    monkeypatch.setattr(doc_chat, "is_enabled", lambda: True)
    monkeypatch.setattr(doc_chat, "_post_chat", lambda messages, max_tokens=600: "Übersetzt ohne Code.")
    result = translation_drafts.draft("", PAGE, "en", "de")
    assert result["missing_code"] == 2
    assert "docuwaves backup --to /srv" in result["markdown"] and "`docuwaves status`" in result["markdown"]


def test_long_pages_go_in_sections(model):
    section = "## Part\n\n" + ("Words. " * 600) + "\n\n"
    translation_drafts.draft("", section * 4, "en", "de")
    assert len(model) >= 2
    assert all(len(m[1]["content"]) <= 6000 + len(section) for m in model)


def test_unknown_language_is_named_by_code():
    assert "'pl'" in translation_drafts.language_name("pl")


@pytest.mark.parametrize(
    ("title", "text", "source", "target", "code"),
    [("", "  ", "en", "de", "empty_question"), ("T", "x", "de", "de", "same_language"),
     ("T", "x" * 60001, "en", "de", "too_long")],
)
def test_refused(model, title, text, source, target, code):
    with pytest.raises(doc_chat.ChatError, match=code):
        translation_drafts.draft(title, text, source, target)
    assert model == []


class TestApi:
    def login(self, user):
        c = TestClient(importlib.import_module("app.main").app)
        c.post("/api/auth/login", json={"username": user[0], "password": user[1]}, headers=ORIGIN)
        return c

    def test_editor_gets_a_draft(self, world, model):
        c = self.login(("chef", "chef-passwort-123"))
        r = c.post("/api/admin/translation-draft", headers=ORIGIN, json={
            "title": "Backups", "markdown": PAGE, "source_language": "en", "target_language": "de",
        })
        assert r.status_code == 200 and "Starte das Backup" in r.json()["markdown"]

    def test_a_viewer_cannot(self, world, model):
        c = self.login(("leser", "leser-passwort-123"))
        r = c.post("/api/admin/translation-draft", headers=ORIGIN, json={
            "title": "x", "markdown": "x", "source_language": "en", "target_language": "de",
        })
        assert r.status_code == 403 and model == []

    def test_without_a_model(self, world, monkeypatch):
        monkeypatch.setattr(doc_chat, "is_enabled", lambda: False)
        c = self.login(("chef", "chef-passwort-123"))
        r = c.post("/api/admin/translation-draft", headers=ORIGIN, json={
            "title": "x", "markdown": "x", "source_language": "en", "target_language": "de",
        })
        assert r.status_code == 409
