"""Semantic search: off by default, incremental, merged with full-text, and
never the reason a search fails. The embeddings endpoint is faked with a
tiny "model" that maps words to concepts, so a page about systemd is close
to a question about starting on boot without sharing a word with it."""
import importlib
import math

import git
import pytest
import requests
from fastapi.testclient import TestClient

from app.services import content_sync, db, git_content_repo, semantic_search, session_secret, users_store
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}

CONCEPTS = [
    {"boot", "startup", "systemd", "service", "autostart", "start"},
    {"backup", "restore", "archive", "copy"},
    {"theme", "colour", "color", "logo", "branding"},
    {"search", "find", "index"},
]


def fake_vector(text: str) -> list[float]:
    words = {w.strip(".,:;!?()#*`").lower() for w in text.split()}
    vector = [float(len(words & concept)) for concept in CONCEPTS]
    # A small constant so no text is the zero vector.
    return [*vector, 0.05]


class FakeEndpoint:
    def __init__(self):
        self.calls: list[list[str]] = []
        self.fail = False

    def __call__(self, url, headers=None, json=None, timeout=None):
        assert url.endswith("/embeddings")
        if self.fail:
            raise requests.ConnectionError("refused")
        self.calls.append(list(json["input"]))
        data = [{"index": i, "embedding": fake_vector(t)} for i, t in enumerate(json["input"])]
        return _Response({"data": data})


class _Response:
    status_code = 200

    def __init__(self, body):
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def page(title, body):
    return f"---\norder: 1\npublished: true\ntitle: {title}\n---\n\n{body}\n"


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    write(content, "docs/_project.yml", "name: Docs\n")
    write(content, "docs/guide/_category.yml", "name: Guide\n")
    write(content, "docs/guide/systemd.md", page(
        "Running in the background",
        "Install the unit file.\n\n## Enabling it\n\nRun systemctl enable so the systemd service comes up with the machine.",
    ))
    write(content, "docs/guide/backups.md", page("Backups", "Make an archive of the data folder and copy it away."))
    write(content, "docs/guide/branding.md", page("Branding", "Set your logo and colour."))
    write(content, "secret/_project.yml", "name: Secret\nvisibility: private\n")
    write(content, "secret/notes/_category.yml", "name: Notes\n")
    write(content, "secret/notes/boot.md", page("Internal autostart", "Our startup service details."))
    repository = git.Repo.init(repo_dir)
    repository.index.add([str(p.relative_to(repo_dir)) for p in content.rglob("*") if p.is_file()])
    actor = git.Actor("Test", "t@example.com")
    repository.index.commit("Inhalt", author=actor, committer=actor)

    monkeypatch.setattr(settings, "content_repo_path", str(repo_dir))
    monkeypatch.setattr(settings, "content_repo_url", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "index.db"))
    monkeypatch.setattr(settings, "embeddings_api_base", "")
    monkeypatch.setattr(settings, "embeddings_model", "")
    monkeypatch.setattr(settings, "embeddings_api_key", "")
    monkeypatch.setattr(session_secret, "_SECRET_PATH", tmp_path / ".session_secret")
    monkeypatch.setattr(git_content_repo, "_read_repo", lambda: repository)
    monkeypatch.setattr(git_content_repo, "_repo", repository)
    monkeypatch.setattr(git_content_repo, "_mode", git_content_repo.LOCAL)
    git_content_repo._read_cache.clear()
    # Fresh module state per test, and no background thread: the tests call
    # index_now() themselves, deterministically.
    monkeypatch.setattr(semantic_search, "_vectors", {})
    monkeypatch.setattr(semantic_search, "_loaded", False)
    monkeypatch.setattr(semantic_search, "_query_cache", semantic_search.OrderedDict())
    monkeypatch.setattr(semantic_search, "_chunk_cache", {})
    monkeypatch.setattr(semantic_search, "_status", {"chunks": 0, "embedded": 0, "last_error": "", "last_error_at": "", "indexed_at": ""})
    monkeypatch.setattr(semantic_search, "schedule", lambda: None)
    endpoint = FakeEndpoint()
    monkeypatch.setattr(semantic_search.requests, "post", endpoint)

    db.init_schema()
    content_sync.full_sync()
    users_store.create_first_admin("chef", "chef-passwort-123")
    app = importlib.import_module("app.main").app
    return {"app": app, "content": content, "endpoint": endpoint, "monkeypatch": monkeypatch}


def enable(world):
    world["monkeypatch"].setattr(settings, "embeddings_api_base", "http://ollama.test:11434/v1")
    world["monkeypatch"].setattr(settings, "embeddings_model", "fake-embed")


def search(world, q, record=True, client=None):
    c = client or TestClient(world["app"])
    return c.get("/api/public/search", params={"q": q, "record": str(record).lower()}).json()["results"]


def test_chunks_follow_headings_and_keep_the_title():
    parts = semantic_search.chunks("Install", "Intro text.\n\n## Linux\n\nUse apt.\n\n## macOS\n\nUse brew.")
    assert len(parts) == 3 and all(p.startswith("Install\n") for p in parts)
    assert "apt" in parts[1] and "brew" in parts[2]
    long = semantic_search.chunks("T", "Sentence one. " * 300)
    assert len(long) > 1 and all(len(p) <= semantic_search._CHUNK_CHARS + 3 for p in long)


def test_off_by_default_no_request_and_search_unchanged(world):
    assert semantic_search.is_enabled() is False
    assert semantic_search.index_now() == 0
    assert search(world, "start on boot") == []
    assert world["endpoint"].calls == []


def test_finds_a_page_by_meaning(world):
    enable(world)
    assert semantic_search.index_now() > 0
    hits = search(world, "start on boot")
    assert hits and hits[0]["page_slug"] == "systemd"
    assert hits[0]["match"] == "meaning"
    # The section that matched is the snippet, not the page's first line.
    assert "systemctl enable" in hits[0]["snippet"]
    # Unrelated pages stay out.
    assert "branding" not in [h["page_slug"] for h in hits]


def test_text_and_meaning_together_rank_a_page_both_find_first(world):
    enable(world)
    semantic_search.index_now()
    hits = search(world, "archive")
    assert hits[0]["page_slug"] == "backups"
    assert "match" not in hits[0]


def test_search_as_you_type_does_not_embed(world):
    enable(world)
    semantic_search.index_now()
    before = len(world["endpoint"].calls)
    assert search(world, "start on boot", record=False) == []
    assert len(world["endpoint"].calls) == before


def test_indexing_is_incremental(world):
    enable(world)
    first = semantic_search.index_now()
    assert first > 0
    assert semantic_search.index_now() == 0
    write(world["content"], "docs/guide/backups.md", page("Backups", "Make an archive and copy it to another disk."))
    content_sync.full_sync()
    assert semantic_search.index_now() == 1
    status = semantic_search.status()
    assert status["enabled"] and status["embedded"] == status["chunks"]


def test_a_reindex_costs_no_request(world):
    enable(world)
    semantic_search.index_now()
    calls = len(world["endpoint"].calls)
    content_sync.full_sync()
    # A new process: nothing in memory, everything in the table.
    world["monkeypatch"].setattr(semantic_search, "_vectors", {})
    world["monkeypatch"].setattr(semantic_search, "_loaded", False)
    assert semantic_search.index_now() == 0
    assert len(world["endpoint"].calls) == calls


def test_a_failing_endpoint_never_fails_the_search(world):
    enable(world)
    semantic_search.index_now()
    world["endpoint"].fail = True
    hits = search(world, "archive copy")
    assert [h["page_slug"] for h in hits] == ["backups"]
    assert "refused" in semantic_search.status()["last_error"]


def test_a_private_page_is_not_found_by_meaning_anonymously(world):
    enable(world)
    semantic_search.index_now()
    assert "boot" not in [h["page_slug"] for h in search(world, "startup")]
    chef = TestClient(world["app"])
    chef.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-123"}, headers=ORIGIN)
    assert "boot" in [h["page_slug"] for h in search(world, "startup", client=chef)]


def test_vectors_are_unit_length(world):
    enable(world)
    vector = semantic_search.embed(["backup restore"])[0]
    assert math.isclose(sum(v * v for v in vector), 1.0, rel_tol=1e-5)
