"""Nested categories: `parent:` in `_category.yml`, directories stay flat.
What a reader sees (tiles, breadcrumb, sidebar order, the book) and what an
editor can and cannot do (no loops, no orphans, siblings stay siblings)."""
import importlib

import git
import pytest
import yaml
from fastapi.testclient import TestClient

from app.services import (
    categories_store,
    content_sync,
    content_versions,
    db,
    git_content_repo,
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


def page(title, order=1):
    return f"---\norder: {order}\npublished: true\ntitle: {title}\n---\n\nText of {title}.\n"


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    write(content, "docs/_project.yml", "name: Docs\n")
    # guide > install > linux, plus a top-level reference; `server` holds
    # nothing itself, only `linux` under `install` holds pages there.
    write(content, "docs/guide/_category.yml", "name: Guide\norder: 0\n")
    write(content, "docs/guide/intro.md", page("Intro"))
    write(content, "docs/install/_category.yml", "name: Install\nparent: guide\norder: 1\n")
    write(content, "docs/install/basics.md", page("Basics"))
    write(content, "docs/linux/_category.yml", "name: Linux\nparent: install\norder: 0\n")
    write(content, "docs/linux/apt.md", page("Apt"))
    write(content, "docs/server/_category.yml", "name: Server\norder: 2\n")
    write(content, "docs/hosting/_category.yml", "name: Hosting\nparent: server\n")
    write(content, "docs/hosting/vps.md", page("VPS"))
    write(content, "docs/reference/_category.yml", "name: Reference\norder: 3\n")
    write(content, "docs/reference/cli.md", page("CLI"))
    # Broken on purpose: a loop and a parent that does not exist.
    write(content, "docs/loop-a/_category.yml", "name: Loop A\nparent: loop-b\norder: 4\n")
    write(content, "docs/loop-a/a.md", page("A"))
    write(content, "docs/loop-b/_category.yml", "name: Loop B\nparent: loop-a\norder: 5\n")
    write(content, "docs/loop-b/b.md", page("B"))
    write(content, "docs/orphan/_category.yml", "name: Orphan\nparent: nowhere\norder: 6\n")
    write(content, "docs/orphan/o.md", page("O"))
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
    return importlib.import_module("app.main").app, content


def admin(app):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-123"}, headers=ORIGIN).status_code == 200
    return c


def by_slug(project="docs"):
    pid = projects_store.get_project_by_slug(project)["id"]
    return {c["slug"]: c for c in categories_store.list_categories(pid)}


def test_parents_are_indexed_and_broken_ones_fall_back_to_the_top(world):
    cats = by_slug()
    assert cats["install"]["parent"] == "guide"
    assert cats["linux"]["parent"] == "install"
    assert cats["orphan"]["parent"] == ""
    # One link of the loop is cut, the other kept -- nothing disappears.
    assert sorted([cats["loop-a"]["parent"], cats["loop-b"]["parent"]]) == ["", "loop-a"]


def test_nav_is_in_reading_order_with_depths(world):
    app, _ = world
    nav = TestClient(app).get("/api/public/projects/docs/nav").json()
    order = [(c["slug"], c["depth"]) for c in nav["categories"]]
    assert order[:6] == [
        ("guide", 0), ("install", 1), ("linux", 2), ("server", 0), ("hosting", 1), ("reference", 0),
    ]
    assert len(order) == 9


def test_project_tiles_are_top_level_and_count_what_is_under_them(world):
    app, _ = world
    tiles = {c["slug"]: c["page_count"] for c in TestClient(app).get("/api/public/projects/docs").json()["categories"]}
    assert "install" not in tiles and "linux" not in tiles and "hosting" not in tiles
    assert tiles["guide"] == 3
    # Nothing of its own, but a subsection with a page: still a tile.
    assert tiles["server"] == 1


def test_category_has_breadcrumb_and_subcategory_tiles(world):
    app, _ = world
    body = TestClient(app).get("/api/public/projects/docs/categories/install").json()
    assert [p["slug"] for p in body["parents"]] == ["guide"]
    assert [(c["slug"], c["page_count"]) for c in body["subcategories"]] == [("linux", 1)]
    assert [p["slug"] for p in body["pages"]] == ["basics"]


def test_printing_a_section_prints_its_subsections(world):
    app, _ = world
    book = TestClient(app).get("/api/public/projects/docs/book", params={"category": "install"}).json()
    assert [(c["slug"], c["depth"]) for c in book["categories"]] == [("install", 0), ("linux", 1)]


def test_editor_nests_and_unnests(world):
    app, content = world
    c = admin(app)
    cats = by_slug()
    r = c.put(f"/api/admin/categories/{cats['reference']['id']}", json={"name": "Reference", "parent": "guide"}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert yaml.safe_load((content / "docs/reference/_category.yml").read_text())["parent"] == "guide"
    assert by_slug()["reference"]["parent"] == "guide"
    # Leaving `parent` out keeps it -- a plain rename must not un-nest.
    c.put(f"/api/admin/categories/{by_slug()['reference']['id']}", json={"name": "Reference", "icon": "📘"}, headers=ORIGIN)
    assert by_slug()["reference"]["parent"] == "guide"
    c.put(f"/api/admin/categories/{by_slug()['reference']['id']}", json={"name": "Reference", "parent": ""}, headers=ORIGIN)
    assert by_slug()["reference"]["parent"] == ""
    assert "parent" not in yaml.safe_load((content / "docs/reference/_category.yml").read_text())


def test_editor_cannot_make_a_loop_or_nest_too_deep(world):
    app, _ = world
    c = admin(app)
    cats = by_slug()
    loop = c.put(f"/api/admin/categories/{cats['guide']['id']}", json={"name": "Guide", "parent": "linux"}, headers=ORIGIN)
    assert loop.status_code == 400
    missing = c.post(f"/api/admin/projects/{cats['guide']['project_id']}/categories", json={"name": "X", "parent": "nope"}, headers=ORIGIN)
    assert missing.status_code == 400
    # guide > install > linux > deep is 4 levels: fine. A fifth is not.
    deep = c.post(f"/api/admin/projects/{cats['guide']['project_id']}/categories", json={"name": "Deep", "parent": "linux"}, headers=ORIGIN)
    assert deep.status_code == 200
    deeper = c.post(f"/api/admin/projects/{cats['guide']['project_id']}/categories", json={"name": "Deeper", "parent": "deep"}, headers=ORIGIN)
    assert deeper.status_code == 400
    # Moving a branch under another must count the branch's own depth too.
    server = c.put(f"/api/admin/categories/{cats['guide']['id']}", json={"name": "Guide", "parent": "server"}, headers=ORIGIN)
    assert server.status_code == 400


def test_renaming_a_parent_takes_its_children_along(world):
    app, content = world
    c = admin(app)
    r = c.put(f"/api/admin/categories/{by_slug()['install']['id']}", json={"name": "Setup"}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    cats = by_slug()
    assert cats["setup"]["parent"] == "guide"
    assert cats["linux"]["parent"] == "setup"
    assert yaml.safe_load((content / "docs/linux/_category.yml").read_text())["parent"] == "setup"


def test_deleting_a_parent_moves_its_children_up(world):
    app, _ = world
    c = admin(app)
    assert c.delete(f"/api/admin/categories/{by_slug()['install']['id']}", headers=ORIGIN).status_code == 200
    cats = by_slug()
    assert "install" not in cats
    assert cats["linux"]["parent"] == "guide"


def test_moving_stays_among_siblings(world):
    app, _ = world
    c = admin(app)
    # `linux` is the only child of `install`: moving it up changes nothing,
    # rather than swapping it with whatever sits above it in the flat list.
    before = {s: x["sort_order"] for s, x in by_slug().items()}
    c.post(f"/api/admin/categories/{by_slug()['linux']['id']}/move", params={"direction": -1}, headers=ORIGIN)
    assert {s: x["sort_order"] for s, x in by_slug().items()} == before
    # Two top-level ones swap as before.
    c.post(f"/api/admin/categories/{by_slug()['reference']['id']}/move", params={"direction": -1}, headers=ORIGIN)
    after = by_slug()
    assert after["reference"]["sort_order"] == before["server"]
    assert after["server"]["sort_order"] == before["reference"]
    assert after["linux"]["parent"] == "install"
