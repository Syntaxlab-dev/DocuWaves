"""The glossary (services/glossary.py): site and project terms, per language,
written through the admin API and read by the public one."""
import importlib

import pytest
from fastapi.testclient import TestClient

from app.services import git_content_repo, glossary
from app.settings import settings

from tests.test_gap_drafts import ORIGIN, world  # noqa: F401 -- the fixture


@pytest.fixture
def signed_in(world, monkeypatch):
    monkeypatch.setattr(git_content_repo, "_mode", git_content_repo.LOCAL)
    monkeypatch.setattr(git_content_repo, "_repo", git_content_repo._read_repo())
    c = TestClient(importlib.import_module("app.main").app)
    c.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-123"}, headers=ORIGIN)
    return c


def test_written_and_read(signed_in):
    c = signed_in
    r = c.put("/api/admin/glossary", json={"project": "docs", "text": "SLA: Zugesagte Verfügbarkeit.\n"}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    c.put("/api/admin/glossary", json={"text": "Tarball: Ein gepacktes Archiv.\nSLA: Site-weit.\n"}, headers=ORIGIN)
    assert c.get("/api/admin/glossary?project=docs").json()["text"] == "SLA: Zugesagte Verfügbarkeit.\n"
    terms = c.get("/api/public/projects/docs/glossary").json()["terms"]
    # The project's SLA wins over the site's; sorted by term.
    assert terms == [
        {"term": "SLA", "definition": "Zugesagte Verfügbarkeit."},
        {"term": "Tarball", "definition": "Ein gepacktes Archiv."},
    ]
    repo = git_content_repo._read_repo()
    assert "Update glossary" in repo.head.commit.message


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("SLA: [unclosed", "valid YAML"),
        ("- a\n- b\n", "one term per line"),
        ("SLA:\n", "a definition is text"),
        ("SLA: yes\n", "a definition is text"),
        (f"SLA: {'x' * 700}\n", "at most"),
    ],
)
def test_refused_with_a_reason(signed_in, text, reason):
    r = signed_in.put("/api/admin/glossary", json={"project": "docs", "text": text}, headers=ORIGIN)
    assert r.status_code == 400 and reason in r.json()["detail"]


def test_per_language_definitions(world, monkeypatch):
    monkeypatch.setattr("app.services.site_languages.default_language", lambda: "de")
    monkeypatch.setattr(glossary, "read_text", lambda slug, version: (
        "API:\n  de: Programmierschnittstelle\n  en: Programming interface\n" if slug else ""
    ))
    assert glossary.terms("docs", "", "en") == [{"term": "API", "definition": "Programming interface"}]
    assert glossary.terms("docs", "", "fr") == [{"term": "API", "definition": "Programmierschnittstelle"}]


def test_a_broken_file_means_no_terms_not_an_error(world, monkeypatch):
    monkeypatch.setattr(glossary, "read_text", lambda slug, version: "SLA: [broken")
    assert glossary.terms("docs", "", "") == []


def test_unknown_project_is_404(world):
    c = TestClient(importlib.import_module("app.main").app)
    assert c.get("/api/public/projects/nope/glossary").status_code == 404


def test_empty_text_removes_the_file(signed_in):
    c = signed_in
    c.put("/api/admin/glossary", json={"project": "docs", "text": "SLA: x\n"}, headers=ORIGIN)
    c.put("/api/admin/glossary", json={"project": "docs", "text": ""}, headers=ORIGIN)
    assert c.get("/api/admin/glossary?project=docs").json()["text"] == ""
    assert not (glossary._path("docs", "")).exists()
    assert settings.content_repo_path
