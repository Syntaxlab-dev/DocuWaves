"""Bulk actions on pages: several pages, one commit, one reindex, and every
page checked exactly as it would be on its own."""
import importlib

import git
import pytest
from fastapi.testclient import TestClient

from app.services import (
    content_sync,
    content_versions,
    db,
    git_content_repo,
    pages_store,
    project_access,
    projects_store,
    session_secret,
    users_store,
)
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def page(title, published, order=1):
    return f"---\norder: {order}\npublished: {'true' if published else 'false'}\ntitle: {title}\n---\n\nText of {title}.\n"


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    write(content, "docs/_project.yml", "name: Docs\n")
    write(content, "docs/guide/_category.yml", "name: Guide\n")
    write(content, "docs/archive/_category.yml", "name: Archive\n")
    for i, slug in enumerate(("one", "two", "three")):
        write(content, f"docs/guide/{slug}.md", page(slug.title(), False, i))
    write(content, "other/_project.yml", "name: Other\n")
    write(content, "other/misc/_category.yml", "name: Misc\n")
    write(content, "other/misc/four.md", page("Four", False))
    write(content, "strict/_project.yml", "name: Strict\nreview: required\n")
    write(content, "strict/guide/_category.yml", "name: Guide\n")
    write(content, "strict/guide/five.md", page("Five", False))
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
    git_content_repo._read_cache.clear()

    db.init_schema()
    content_sync.full_sync()
    users_store.create_first_admin("chef", "chef-passwort-123")
    users_store.create_user("vera", "vera-passwort-123", users_store.VIEWER)
    project_access.set_grants("vera", {"docs": users_store.EDITOR})
    return importlib.import_module("app.main").app, repository


def client(app, name="chef", password="chef-passwort-123"):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": name, "password": password}, headers=ORIGIN).status_code == 200
    return c


def ids(project, *slugs):
    p = projects_store.get_project_by_slug(project)
    return [pages_store.get_page_by_slug(p["id"], s, "", "")["id"] for s in slugs]


def category_id(project, slug):
    from app.services import categories_store

    p = projects_store.get_project_by_slug(project)
    return next(c["id"] for c in categories_store.list_categories(p["id"], "", "") if c["slug"] == slug)


def bulk(c, **body):
    return c.post("/api/admin/pages/bulk", json=body, headers=ORIGIN)


def test_publishing_several_pages_is_one_commit(world):
    app, repo = world
    before = repo.head.commit
    r = bulk(client(app), action="publish", page_ids=ids("docs", "one", "two"))
    assert r.status_code == 200, r.text
    assert len(r.json()["done"]) == 2
    assert repo.head.commit.parents[0] == before
    assert repo.head.commit.message == "Publish 2 pages"
    assert all(pages_store.get_page(i)["published"] for i in ids("docs", "one", "two"))
    assert not pages_store.get_page(ids("docs", "three")[0])["published"]


def test_unchanged_pages_are_skipped_not_failed(world):
    app, _ = world
    r = bulk(client(app), action="unpublish", page_ids=ids("docs", "one"))
    assert r.json() == {"done": [], "skipped": [{"id": ids("docs", "one")[0], "reason": "unchanged"}]}


def test_moving_to_another_category(world):
    app, repo = world
    target = category_id("docs", "archive")
    r = bulk(client(app), action="move", page_ids=ids("docs", "one", "two"), category_id=target)
    assert r.status_code == 200, r.text
    assert sorted(p["slug"] for p in pages_store.list_pages(target)) == ["one", "two"]
    assert repo.head.commit.message == "Move 2 pages to Archive"


def test_a_page_from_another_project_is_not_moved(world):
    app, _ = world
    r = bulk(client(app), action="move", page_ids=ids("other", "four"), category_id=category_id("docs", "archive"))
    assert r.json()["skipped"][0]["reason"] == "other_project"


def test_deleting(world):
    app, _ = world
    r = bulk(client(app), action="delete", page_ids=ids("docs", "one", "three"))
    assert r.status_code == 200, r.text
    p = projects_store.get_project_by_slug("docs")
    assert [pg["slug"] for pg in pages_store.list_pages(category_id("docs", "guide"))] == ["two"]
    assert p is not None


def test_approval_still_applies(world):
    app, _ = world
    r = bulk(client(app), action="publish", page_ids=ids("strict", "five"))
    assert r.json()["skipped"][0]["reason"] == "review_required"


def test_a_selection_reaching_into_a_read_only_project_is_refused_whole(world):
    app, _ = world
    c = client(app, "vera", "vera-passwort-123")
    r = bulk(c, action="publish", page_ids=ids("docs", "one") + ids("other", "four"))
    assert r.status_code == 403
    assert not pages_store.get_page(ids("docs", "one")[0])["published"]
    assert bulk(c, action="publish", page_ids=ids("docs", "one")).status_code == 200


@pytest.mark.parametrize("body", [{"action": "explode", "page_ids": [1]}, {"action": "publish", "page_ids": []}])
def test_refused(world, body):
    app, _ = world
    assert bulk(client(app), **body).status_code in (400, 422)


def test_a_batch_inside_a_batch_commits_once(world):
    _, repo = world
    before = repo.head.commit
    with git_content_repo.batch("outer", "chef"):
        with git_content_repo.batch("inner", "chef"):
            pages_store.set_published(ids("docs", "one")[0], True, "chef")
    assert repo.head.commit.parents[0] == before and repo.head.commit.message == "outer"
