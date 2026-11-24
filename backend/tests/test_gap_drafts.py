"""A first draft for a search gap (services/gap_drafts.py): built from the
existing pages only, with the model call faked."""
import importlib

import git
import pytest
from fastapi.testclient import TestClient

from app.services import (
    changelog,
    content_sync,
    content_versions,
    db,
    doc_chat,
    gap_drafts,
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


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    write(content, "docs/_project.yml", "name: Docs\n")
    write(content, "docs/guide/_category.yml", "name: Guide\n")
    write(content, "docs/guide/backups.md",
          "---\norder: 1\npublished: true\ntitle: Backups\n---\n\nThe backup command writes a tarball nightly.\n")
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
    git_content_repo._read_cache.clear()
    monkeypatch.setattr(changelog, "_cache", None)
    monkeypatch.setattr(search_suggest, "_cached", None)
    monkeypatch.setattr(content_versions, "_cache", {})
    search_suggest._correct_word.cache_clear()
    db.init_schema()
    content_sync.full_sync()
    users_store.create_first_admin("chef", "chef-passwort-123")
    users_store.create_user("leser", "leser-passwort-123", users_store.VIEWER)

    calls = []

    def fake_post(messages, max_tokens=600):
        calls.append(messages)
        return "```markdown\n# Restoring backups\n\nIntro.\n\n**TODO:** steps\n```"

    monkeypatch.setattr(doc_chat, "_post_chat", fake_post)
    monkeypatch.setattr(doc_chat, "is_enabled", lambda: True)
    return calls


class TestClean:
    def test_fence_and_title_are_removed(self):
        assert gap_drafts.clean("```md\n# T\n\nBody\n```") == "Body\n"

    def test_plain_text_is_kept(self):
        assert gap_drafts.clean("Intro.\n\n## A\n") == "Intro.\n\n## A\n"


class TestDraft:
    def test_built_from_related_pages(self, world):
        result = gap_drafts.draft("restoring backups offsite", "")
        assert result["title"] == "Restoring backups offsite"
        assert result["markdown"] == "Intro.\n\n**TODO:** steps\n"
        assert [s["page_slug"] for s in result["sources"]] == ["backups"]
        prompt = world[0][1]["content"]
        assert "URL: /p/docs/pages/backups" in prompt and "tarball" in prompt

    def test_nothing_related_is_said_so(self, world):
        gap_drafts.draft("quantum entanglement", "")
        assert "(none" in world[0][1]["content"]

    def test_not_configured(self, world, monkeypatch):
        monkeypatch.setattr(doc_chat, "is_enabled", lambda: False)
        with pytest.raises(doc_chat.ChatError, match="not_configured"):
            gap_drafts.draft("x", "")


class TestApi:
    def login(self, user):
        c = TestClient(importlib.import_module("app.main").app)
        c.post("/api/auth/login", json={"username": user[0], "password": user[1]}, headers=ORIGIN)
        return c

    def test_editor_gets_a_draft(self, world):
        c = self.login(("chef", "chef-passwort-123"))
        r = c.post("/api/admin/search-gaps/draft", json={"query": "restoring backups"}, headers=ORIGIN)
        assert r.status_code == 200 and r.json()["markdown"].startswith("Intro.")
        assert c.get("/api/admin/search-gaps").json()["can_draft"] is True

    def test_a_viewer_cannot(self, world):
        c = self.login(("leser", "leser-passwort-123"))
        assert c.post("/api/admin/search-gaps/draft", json={"query": "x"}, headers=ORIGIN).status_code == 403

    def test_without_a_model(self, world, monkeypatch):
        monkeypatch.setattr(doc_chat, "is_enabled", lambda: False)
        c = self.login(("chef", "chef-passwort-123"))
        r = c.post("/api/admin/search-gaps/draft", json={"query": "x"}, headers=ORIGIN)
        assert r.status_code == 409 and r.json()["detail"] == "not_configured"
