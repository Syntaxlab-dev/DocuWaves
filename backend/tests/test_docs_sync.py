"""Docs-as-code: a CI job pushes a ZIP of docs/ with a sync token, and the
project becomes exactly that -- stable addresses, published unless marked
draft, one commit per change and none without (services/docs_sync.py)."""
from fastapi.testclient import TestClient

from app.services import api_tokens_store, docs_sync, pages_store, projects_store, webhooks

from tests.test_importer import ORIGIN, make_zip, png, world  # noqa: F401 -- the fixture

DOCS = {
    "docs/index.md": "# Pagenest\n\nWillkommen. [Installation](setup/install.md)\n",
    "docs/setup/install.md": "# Installation\n\n![Plan](../img/plan.png)\n",
    "docs/setup/02-config.md": "---\ndraft: true\n---\n# Konfiguration\n\nNoch nicht fertig.\n",
    "docs/img/plan.png": png(),
}


def token(project="alt", scope=api_tokens_store.SYNC_SCOPE) -> str:
    _record, value = api_tokens_store.create("ci", scope, "", project if scope == api_tokens_store.SYNC_SCOPE else "")
    return value


def push(world, files, value, project="alt", ref="abc1234"):
    client = TestClient(world["app"])
    return client.post(
        f"/api/sync/{project}?ref={ref}", content=make_zip(files), headers={"Authorization": f"Bearer {value}"}
    )


def pages():
    project = projects_store.get_project_by_slug("alt")
    slugs = {p["slug"] for p in pages_store.list_project_pages(project["id"])}
    return {s: pages_store.get_page_by_slug(project["id"], s) for s in slugs}


def commits(world) -> int:
    return len(list(world["repo"].iter_commits()))


class TestSync:
    def test_the_archive_becomes_the_project(self, world):
        r = push(world, DOCS, token())
        assert r.status_code == 200, r.text
        body = r.json()
        # The project had a hand-written `install` page: same address, so
        # it is CHANGED (now the synced text), not removed and re-added.
        assert body["committed"] is True and body["added"] == ["config", "start"]
        assert body["changed"] == ["install"] and body["removed"] == []
        current = pages()
        # The old hand-written page of the project is gone, the synced ones are there.
        assert set(current) == {"start", "install", "config"}
        assert current["start"]["published"] and current["install"]["published"]
        assert current["config"]["published"] is False  # draft: true
        assert "[Installation](/p/alt/pages/install)" in current["start"]["markdown_content"]
        assert "../assets/sync/img/plan.png" in current["install"]["markdown_content"]
        assert (world["content"] / "alt/assets/sync/img/plan.png").exists()

    def test_the_same_push_twice_changes_nothing(self, world):
        value = token()
        push(world, DOCS, value)
        before = commits(world)
        r = push(world, DOCS, value, ref="abc1234")
        assert r.json()["committed"] is False and r.json()["added"] == [] and r.json()["changed"] == []
        assert commits(world) == before

    def test_a_reworded_title_keeps_the_address_and_a_deleted_file_deletes_the_page(self, world):
        value = token()
        push(world, DOCS, value)
        changed = {**DOCS, "docs/setup/install.md": "# Einrichtung\n\nNeu.\n"}
        del changed["docs/setup/02-config.md"]
        r = push(world, changed, value, ref="def5678").json()
        assert r["changed"] == ["install"] and r["removed"] == ["config"]
        assert pages()["install"]["title"] == "Einrichtung"
        message = world["repo"].head.commit.message
        assert message.startswith("Sync from def5678") and "1 changed, 1 removed" in message

    def test_slug_in_front_matter_pins_the_address(self, world):
        push(world, {"docs/a.md": "---\nslug: fester-name\n---\n# A\n"}, token())
        assert set(pages()) == {"fester-name"}

    def test_webhooks_only_after_the_first_sync(self, world, monkeypatch):
        sent = []
        monkeypatch.setattr(webhooks, "notify", lambda event, page, *a, **k: sent.append((event, page["slug"])))
        value = token()
        # The project already has a page, so even the first sync is a change.
        push(world, DOCS, value)
        assert ("published", "start") in sent and ("unpublished", "install") not in sent
        sent.clear()
        push(world, {**DOCS, "docs/index.md": "# Pagenest\n\nAnders.\n"}, value, ref="x")
        assert sent == [("updated", "start")]

    def test_runs_are_recorded(self, world):
        value = token()
        push(world, DOCS, value, ref="aaa")
        push(world, DOCS, value, ref="bbb")
        runs = docs_sync.runs("alt")
        assert [r["ref"] for r in runs] == ["bbb", "aaa"] and runs[0]["committed"] is False


class TestTokens:
    def test_a_sync_token_only_syncs_its_own_project(self, world):
        value = token("alt")
        assert push(world, DOCS, value, project="andere").status_code == 403
        client = TestClient(world["app"])
        mcp = client.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                          headers={"Authorization": f"Bearer {value}"})
        assert mcp.status_code == 403

    def test_a_write_token_cannot_sync(self, world):
        assert push(world, DOCS, token(scope=api_tokens_store.WRITE_SCOPE)).status_code == 403

    def test_no_token_no_sync(self, world):
        r = TestClient(world["app"]).post("/api/sync/alt", content=make_zip(DOCS))
        assert r.status_code == 401

    def test_a_session_cannot_sync_either(self, world):
        client = TestClient(world["app"])
        client.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-123"}, headers=ORIGIN)
        assert client.post("/api/sync/alt", content=make_zip(DOCS), headers=ORIGIN).status_code == 401

    def test_creating_one_needs_a_project(self, world):
        assert api_tokens_store.rejection_reason("ci", "sync", "", "") is not None
        assert api_tokens_store.rejection_reason("ci", "read", "", "alt") is not None
        assert api_tokens_store.rejection_reason("ci", "sync", "", "alt") is None


class TestReadOnly:
    def admin(self, world):
        client = TestClient(world["app"])
        client.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-123"}, headers=ORIGIN)
        return client

    def test_the_first_sync_marks_the_project_and_its_pages_are_read_only(self, world):
        push(world, DOCS, token())
        assert "source:" in (world["content"] / "alt/_project.yml").read_text()
        project = projects_store.get_project_by_slug("alt")
        assert project["source"] == {"repo": "", "branch": "main", "path": "docs"}
        chef = self.admin(world)
        page = pages()["install"]
        r = chef.put(f"/api/admin/pages/{page['id']}", headers=ORIGIN,
                     json={"title": "X", "markdown_content": "y", "category_id": page["category_id"]})
        assert r.status_code == 403 and "code repository" in r.json()["detail"]
        assert chef.post(f"/api/admin/pages/{page['id']}/publish?published=false", headers=ORIGIN).status_code == 403
        assert chef.post("/api/admin/pages", headers=ORIGIN,
                         json={"title": "Neu", "markdown_content": "", "category_id": page["category_id"]}).status_code == 403

    def test_an_assistant_cannot_write_there_either(self, world):
        push(world, DOCS, token())
        from app.services import mcp_tools
        import pytest as _pytest
        with _pytest.raises(Exception, match="code repository"):
            mcp_tools.update_page({"project": "alt", "page": "install", "markdown": "x"}, {"name": "bot", "scope": "write"})

    def test_the_editor_gets_a_link_to_the_file(self, world):
        push(world, DOCS, token())
        chef = self.admin(world)
        project = projects_store.get_project_by_slug("alt")
        r = chef.put(f"/api/admin/projects/{project['id']}", headers=ORIGIN, json={
            "name": "Alt", "source": {"repo": "https://github.com/acme/pagenest", "branch": "main", "path": "docs"},
        })
        assert r.status_code == 200, r.text
        page = pages()["install"]
        data = chef.get(f"/api/admin/pages/{page['id']}").json()
        assert data["synced"] is True
        assert data["source_edit_url"] == "https://github.com/acme/pagenest/edit/main/docs/setup/install.md"
        runs = chef.get("/api/admin/projects/alt/sync").json()
        assert runs["source"]["repo"] == "https://github.com/acme/pagenest" and len(runs["runs"]) == 1

    def test_switching_the_source_off_makes_it_editable_again(self, world):
        push(world, DOCS, token())
        chef = self.admin(world)
        project = projects_store.get_project_by_slug("alt")
        chef.put(f"/api/admin/projects/{project['id']}", headers=ORIGIN, json={"name": "Alt", "source": None})
        page = pages()["install"]
        r = chef.put(f"/api/admin/pages/{page['id']}", headers=ORIGIN,
                     json={"title": "Install", "markdown_content": "Hier geändert.", "category_id": page["category_id"]})
        assert r.status_code == 200

    def test_a_javascript_repo_address_is_not_kept(self, world):
        from app.services import content_files
        assert content_files.normalize_source({"repo": "javascript:alert(1)"})["repo"] == ""


def test_edit_links_per_host():
    file = "setup/install.md"
    source = {"branch": "main", "path": "docs"}
    assert docs_sync.edit_url({**source, "repo": "https://gitlab.com/a/b"}, file) == "https://gitlab.com/a/b/-/edit/main/docs/setup/install.md"
    assert docs_sync.edit_url({**source, "repo": "https://codeberg.org/a/b.git"}, file) == "https://codeberg.org/a/b/_edit/main/docs/setup/install.md"
    assert docs_sync.edit_url({**source, "repo": ""}, file) == ""
