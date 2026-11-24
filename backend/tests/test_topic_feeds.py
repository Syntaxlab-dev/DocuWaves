"""Feeds of one category and one page (routers/feeds.py), end to end: a
real content repo, a real index, the real routes."""
import importlib
import re

import git
import pytest
from fastapi.testclient import TestClient

from app.routers import feeds

from app.services import (
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


def page(title, body, published=True):
    return f"---\norder: 1\npublished: {'true' if published else 'false'}\ntitle: {title}\n---\n\n{body}\n"


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    write(content, "docs/_project.yml", "name: Docs\n")
    write(content, "docs/guide/_category.yml", "name: Guide\n")
    write(content, "docs/guide/intro.md", page("Intro", "The intro text."))
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


def items(xml: str) -> list[str]:
    return re.findall(r"<item>\s*<title>([^<]*)</title>", xml)


def test_a_category_feed_has_only_that_category(world):
    r = world.get("/p/docs/c/guide/feed.xml")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/rss+xml")
    assert items(r.text) == ["New: Intro"]
    assert "<link>http://testserver/p/docs/c/guide</link>" in r.text
    assert items(world.get("/p/docs/c/api/feed.xml").text) == ["New: Tokens"]


def test_a_page_feed_has_only_that_page(world):
    r = world.get("/p/docs/pages/tokens/feed.xml")
    assert r.status_code == 200
    assert items(r.text) == ["New: Tokens"]
    assert "<title>Tokens – Docs</title>" in r.text


@pytest.mark.parametrize(
    "url",
    [
        "/p/docs/pages/setup/feed.xml",  # a draft
        "/p/docs/pages/nope/feed.xml",
        "/p/docs/c/drafts/feed.xml",  # nothing published in it
        "/p/docs/c/nope/feed.xml",
        "/p/nope/c/guide/feed.xml",
    ],
)
def test_nothing_a_reader_cannot_see(world, url):
    assert world.get(url).status_code == 404


def test_a_private_project_has_no_category_or_page_feed(world, monkeypatch):
    real = feeds.projects_store.get_project_by_slug
    monkeypatch.setattr(feeds.projects_store, "get_project_by_slug", lambda slug, lang="": {**real(slug, lang), "private": True})
    assert world.get("/p/docs/c/guide/feed.xml").status_code == 404
    assert world.get("/p/docs/pages/tokens/feed.xml").status_code == 404


def test_pages_and_categories_announce_their_own_feed(world):
    html = world.get("/p/docs/pages/tokens").text
    assert 'href="http://testserver/p/docs/pages/tokens/feed.xml"' in html
    assert 'href="http://testserver/feed.xml"' in html
    assert 'href="http://testserver/p/docs/c/api/feed.xml"' in world.get("/p/docs/c/api").text
