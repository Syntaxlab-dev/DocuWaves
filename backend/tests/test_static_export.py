"""The static website export (services/static_export.py), from a real content
repo and index."""
import importlib
import io
import zipfile

import git
import pytest
from fastapi.testclient import TestClient


from app.services import (
    static_export,
    changelog,
    content_sync,
    content_versions,
    db,
    git_content_repo,
    session_secret,
)
from app.settings import settings

def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


INTRO = """See [tokens](/p/docs/pages/tokens#scopes) and [the API](/p/docs/c/api) or [setup](setup.md).

![Logo](../assets/logo.png)

> [!WARNING]
> Back up first.

<script>alert(1)</script>

<!-- tabs -->

| a | b |
|---|---|
| 1 | 2 |

- [x] done

[bad](javascript:alert(1))
"""


def page(title, body, published=True):
    return f"---\norder: 1\npublished: {'true' if published else 'false'}\ntitle: {title}\n---\n\n{body}\n"


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    write(content, "docs/_project.yml", "name: Docs\n")
    write(content, "docs/guide/_category.yml", "name: Guide\n")
    write(content, "docs/guide/intro.md", page("Intro", INTRO))
    write(content, "docs/assets/logo.png", "PNG")
    write(content, "secret/_project.yml", "name: Secret\nvisibility: private\n")
    write(content, "secret/guide/_category.yml", "name: Guide\n")
    write(content, "secret/guide/hidden.md", page("Hidden", "Private text."))
    write(content, "docs/guide/setup.md", page("Setup", "A draft.", published=False))
    write(content, "docs/api/_category.yml", "name: API\n")
    write(content, "docs/api/tokens.md", page("Tokens", "About tokens."))
    write(content, "docs/drafts/_category.yml", "name: Drafts\n")
    write(content, "docs/drafts/later.md", page("Later", "Not yet.", published=False))
    repository = git.Repo.init(repo_dir)
    repository.index.add([str(p.relative_to(repo_dir)) for p in content.rglob("*") if p.is_file()])
    actor = git.Actor("Test", "t@example.com")
    repository.index.commit("Inhalt", author=actor, committer=actor)

    monkeypatch.setattr(settings, "content_repo_path", str(repo_dir))
    monkeypatch.setattr(settings, "content_repo_url", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "index.db"))
    monkeypatch.setattr(settings, "webhook_urls", ())
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(session_secret, "_SECRET_PATH", tmp_path / ".session_secret")
    monkeypatch.setattr(git_content_repo, "_read_repo", lambda: repository)
    monkeypatch.setattr(git_content_repo, "_repo", repository)
    monkeypatch.setattr(git_content_repo, "_mode", git_content_repo.LOCAL)
    monkeypatch.setattr(content_versions, "_cache", {})
    monkeypatch.setattr(changelog, "_cache", None)
    git_content_repo._read_cache.clear()

    db.init_schema()
    content_sync.full_sync()
    app = importlib.import_module("app.main").app
    return TestClient(app)


def files(world):
    archive = zipfile.ZipFile(io.BytesIO(static_export.build_bytes()))
    return {name: archive.read(name) for name in archive.namelist()}


def test_only_what_the_public_sees(world):
    names = set(files(world))
    assert {"index.html", "style.css", "docs/index.html", "docs/guide/intro.html", "docs/api/tokens.html",
            "docs/assets/logo.png"} <= names
    assert not any(n.startswith("secret/") for n in names)  # private project
    assert "docs/guide/setup.html" not in names  # a draft
    assert not any("drafts" in n for n in names)  # nothing published in it


def test_a_page_is_rendered_and_its_links_point_at_the_export(world):
    page = files(world)["docs/guide/intro.html"].decode()
    assert '<h1>Intro</h1>' in page
    assert 'href="../api/tokens.html#scopes"' in page
    assert 'href="../index.html#api"' in page
    assert 'src="../assets/logo.png"' in page
    assert 'class="callout callout-warning"' in page and "Back up first." in page
    assert "<table>" in page and 'type="checkbox"' in page
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "tabs" not in page.replace("tabs.", "")
    assert 'href="javascript' not in page
    assert 'href="../../style.css"' in page


def test_the_index_lists_the_projects(world):
    index = files(world)["index.html"].decode()
    assert 'href="docs/index.html"' in index and "Secret" not in index


def test_the_endpoint_is_admin_only_and_returns_a_zip(world):
    assert world.get("/api/admin/export/static").status_code in (401, 403)


def test_badges_become_labels():
    rendered = static_export._badges("<p>A <code>badge:Beta</code>, <code>badge:warning:Old &amp; slow</code>, <code>x</code></p>")
    assert '<span class="badge badge-info">Beta</span>' in rendered
    assert '<span class="badge badge-warning">Old &amp; slow</span>' in rendered
    assert "<code>x</code>" in rendered
