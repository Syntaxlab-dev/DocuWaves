"""Permissions per project, end to end: the real app, a real SQLite index and
a real content repo with two projects, and two accounts whose role is
different in one of them (services/project_access.py).

    vera   viewer, but `editor` in alpha   -> writes alpha only
    eddi   editor, but `viewer` in beta    -> writes everywhere but beta
"""
import importlib

import git
import pytest
from fastapi.testclient import TestClient

from app import auth_guard
from app.services import content_sync, content_versions, db, git_content_repo, project_access, session_secret, users_store
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}
ADMIN = ("chef", "chef-passwort-123")
VERA = ("vera", "vera-passwort-123")
EDDI = ("eddi", "eddi-passwort-123")


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def page(title):
    return f"---\norder: 1\npublished: true\ntitle: {title}\n---\n\nText.\n"


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    for slug in ("alpha", "beta"):
        write(content, f"{slug}/_project.yml", f"name: {slug.title()}\n")
        write(content, f"{slug}/guide/_category.yml", "name: Guide\n")
        write(content, f"{slug}/guide/start.md", page(f"Start {slug}"))
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
    monkeypatch.setattr(git_content_repo, "_repo", repository)
    monkeypatch.setattr(git_content_repo, "_mode", git_content_repo.LOCAL)
    monkeypatch.setattr(content_versions, "_cache", {})
    git_content_repo._read_cache.clear()

    db.init_schema()
    content_sync.full_sync()
    users_store.create_first_admin(*ADMIN)
    users_store.create_user(*VERA, users_store.VIEWER)
    users_store.create_user(*EDDI, users_store.EDITOR)
    project_access.set_grants("vera", {"alpha": users_store.EDITOR})
    project_access.set_grants("eddi", {"beta": users_store.VIEWER})
    return importlib.import_module("app.main").app


def client(app, user):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": user[0], "password": user[1]}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    return c


def ids(c, slug):
    """(project id, category id, page id) of one project, read as the admin
    area reads them."""
    project = next(p for p in c.get("/api/admin/projects").json()["projects"] if p["slug"] == slug)
    category = c.get(f"/api/admin/projects/{project['id']}/categories").json()["categories"][0]
    pages = c.get(f"/api/admin/categories/{category['id']}/pages").json()["pages"]
    return project["id"], category["id"], pages[0]["id"]


def unpublish(c, page_id):
    return c.post(f"/api/admin/pages/{page_id}/publish?published=false", headers=ORIGIN)


class TestWritesFollowTheProject:
    def test_a_viewer_writes_where_it_is_an_editor_and_nowhere_else(self, world):
        c = client(world, VERA)
        _, _, alpha_page = ids(c, "alpha")
        _, _, beta_page = ids(c, "beta")
        assert unpublish(c, alpha_page).status_code == 200
        refused = unpublish(c, beta_page)
        assert refused.status_code == 403
        assert "not change" in refused.json()["detail"]

    def test_an_editor_is_read_only_where_it_is_a_viewer(self, world):
        c = client(world, EDDI)
        _, _, alpha_page = ids(c, "alpha")
        _, _, beta_page = ids(c, "beta")
        assert unpublish(c, alpha_page).status_code == 200
        assert unpublish(c, beta_page).status_code == 403

    def test_creating_a_page_is_checked_against_the_category_s_project(self, world):
        c = client(world, VERA)
        _, alpha_cat, _ = ids(c, "alpha")
        _, beta_cat, _ = ids(c, "beta")
        made = c.post("/api/admin/pages", json={"title": "Neu", "category_id": alpha_cat}, headers=ORIGIN)
        assert made.status_code == 200, made.text
        refused = c.post("/api/admin/pages", json={"title": "Neu", "category_id": beta_cat}, headers=ORIGIN)
        assert refused.status_code == 403

    def test_a_page_cannot_be_moved_into_a_project_it_may_not_write(self, world):
        c = client(world, VERA)
        _, _, alpha_page = ids(c, "alpha")
        _, beta_cat, _ = ids(c, "beta")
        refused = c.put(
            f"/api/admin/pages/{alpha_page}",
            json={"title": "Start alpha", "category_id": beta_cat, "markdown_content": "x"},
            headers=ORIGIN,
        )
        assert refused.status_code == 403

    def test_categories_of_a_writable_project_can_be_made(self, world):
        c = client(world, VERA)
        alpha, _, _ = ids(c, "alpha")
        beta, _, _ = ids(c, "beta")
        assert c.post(f"/api/admin/projects/{alpha}/categories", json={"name": "Mehr"}, headers=ORIGIN).status_code == 200
        assert c.post(f"/api/admin/projects/{beta}/categories", json={"name": "Mehr"}, headers=ORIGIN).status_code == 403

    def test_snippets_follow_the_project_named_in_the_body(self, world):
        c = client(world, VERA)
        body = {"content": "Hallo", "version": "", "language": ""}
        assert c.put("/api/admin/snippets/gruss", json={**body, "project": "alpha"}, headers=ORIGIN).status_code == 200
        assert c.put("/api/admin/snippets/gruss", json={**body, "project": "beta"}, headers=ORIGIN).status_code == 403
        # The whole site's snippets are about no one project: the account's
        # own role counts, and vera's is viewer.
        assert c.put("/api/admin/snippets/gruss", json={**body, "project": ""}, headers=ORIGIN).status_code == 403

    def test_instance_wide_writes_need_the_account_s_own_role(self, world):
        c = client(world, VERA)
        refused = c.post("/api/admin/projects", json={"name": "Gamma"}, headers=ORIGIN)
        assert refused.status_code == 403
        assert "whole instance" in refused.json()["detail"]

    def test_an_exception_never_opens_the_admin_only_areas(self, world):
        c = client(world, VERA)
        assert c.get("/api/admin/users").status_code == 403

    def test_the_status_tells_the_ui_where_it_may_write(self, world):
        c = client(world, VERA)
        status = c.get("/api/auth/status").json()
        assert status["role"] == "viewer"
        assert status["project_roles"] == {"alpha": "editor"}


class TestManagingThem:
    def test_an_admin_sets_and_reads_them_back(self, world):
        c = client(world, ADMIN)
        r = c.put("/api/admin/users/vera/projects", json={"projects": {"beta": "editor", "alpha": "viewer"}}, headers=ORIGIN)
        assert r.status_code == 200, r.text
        # alpha = viewer is vera's own role: not an exception, not stored.
        assert r.json()["projects"] == {"beta": "editor"}
        listed = {u["username"]: u for u in c.get("/api/admin/users").json()["users"]}
        assert listed["vera"]["projects"] == {"beta": "editor"}
        assert listed["chef"]["projects"] == {}

    @pytest.mark.parametrize("role", ["admin", "reader", "owner"])
    def test_only_viewer_and_editor_can_be_granted(self, world, role):
        c = client(world, ADMIN)
        r = c.put("/api/admin/users/vera/projects", json={"projects": {"alpha": role}}, headers=ORIGIN)
        assert r.status_code == 400

    def test_an_unknown_project_is_refused(self, world):
        c = client(world, ADMIN)
        r = c.put("/api/admin/users/vera/projects", json={"projects": {"nope": "editor"}}, headers=ORIGIN)
        assert r.status_code == 404

    def test_not_for_admins(self, world):
        c = client(world, ADMIN)
        r = c.put("/api/admin/users/chef/projects", json={"projects": {"alpha": "viewer"}}, headers=ORIGIN)
        assert r.status_code == 400

    def test_an_editor_cannot_grant_itself_anything(self, world):
        c = client(world, EDDI)
        r = c.put("/api/admin/users/eddi/projects", json={"projects": {}}, headers=ORIGIN)
        assert r.status_code == 403

    def test_they_follow_a_renamed_project(self, world):
        c = client(world, ADMIN)
        alpha, _, _ = ids(c, "alpha")
        r = c.put(f"/api/admin/projects/{alpha}", json={"name": "Alphabet"}, headers=ORIGIN)
        assert r.status_code == 200, r.text
        assert project_access.grants("vera") == {r.json()["slug"]: "editor"}

    def test_they_go_with_a_deleted_project_and_a_deleted_account(self, world):
        c = client(world, ADMIN)
        beta, _, _ = ids(c, "beta")
        assert c.delete(f"/api/admin/projects/{beta}", headers=ORIGIN).status_code == 200
        assert project_access.grants("eddi") == {}
        assert c.delete("/api/admin/users/vera", headers=ORIGIN).status_code == 200
        assert project_access.all_grants() == {}


class TestEffectiveRole:
    def test_admins_and_readers_ignore_exceptions(self, world):
        project_access.set_grants("chef", {"alpha": users_store.VIEWER})
        assert project_access.effective_role({"username": "chef", "role": "admin"}, "alpha") == "admin"
        project_access.set_grants("leser", {"alpha": users_store.EDITOR})
        assert project_access.effective_role({"username": "leser", "role": "reader"}, "alpha") == "reader"

    def test_no_project_means_the_account_s_own_role(self, world):
        assert project_access.effective_role({"username": "vera", "role": "viewer"}, None) == "viewer"


def test_every_admin_write_route_says_how_its_project_is_found(world):
    """The middleware decides per project only for writes it can place. A
    write route nobody classified falls back to the account's own role --
    safe, but an editor who is read-only in one project could then still
    write there through it. So every write route has to be in
    project_access.WRITE_ROUTES (or be admin-only, where exceptions never
    apply), and adding one without deciding fails here."""
    unclassified = []
    for path, operations in world.openapi()["paths"].items():
        if not path.startswith("/api/admin") or path.startswith(auth_guard._ADMIN_ONLY_PREFIXES):
            continue
        concrete = path.replace("{", "").replace("}", "")
        # Stand-ins that fit both the numeric and the slug patterns.
        for name in ("project_id", "category_id", "page_id", "link_id", "gap_id"):
            concrete = concrete.replace(name, "7")
        for method in operations:
            method = method.upper()
            if method in ("GET", "HEAD"):
                continue
            if not any(m == method and p.match(concrete) for m, p, _ in project_access.WRITE_ROUTES):
                unclassified.append(f"{method} {path}")
    assert unclassified == []
