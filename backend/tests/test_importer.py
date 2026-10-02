"""Importing a ZIP of Markdown: structure, order, titles, links, images and
callouts from the common tools -- and an archive that is not allowed to do
anything it likes (services/importer.py)."""
import importlib
import io
import struct
import zipfile
import zlib

import git
import pytest
from fastapi.testclient import TestClient

from app.services import (
    content_sync, db, git_content_repo, importer, pages_store, projects_store, session_secret, users_store,
)
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}
CHEF = ("chef", "chef-passwort-123")
CLARA = ("clara", "clara-passwort-123")


def png() -> bytes:
    """A real 1x1 PNG: the asset check reads the bytes, not the name."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00")) + chunk(b"IEND", b"")


def make_zip(files: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    (content / "alt/guide").mkdir(parents=True)
    (content / "alt/_project.yml").write_text("name: Alt\n")
    (content / "alt/guide/_category.yml").write_text("name: Guide\n")
    (content / "alt/guide/install.md").write_text("---\norder: 1\npublished: true\ntitle: Install\n---\n\nAlt.\n")
    repository = git.Repo.init(repo_dir)
    repository.index.add([str(p.relative_to(repo_dir)) for p in content.rglob("*") if p.is_file()])
    actor = git.Actor("Test", "t@example.com")
    repository.index.commit("Inhalt", author=actor, committer=actor)

    monkeypatch.setattr(settings, "content_repo_path", str(repo_dir))
    monkeypatch.setattr(settings, "content_repo_url", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "index.db"))
    monkeypatch.setattr(session_secret, "_SECRET_PATH", tmp_path / ".session_secret")
    monkeypatch.setattr(git_content_repo, "_read_repo", lambda: repository)
    monkeypatch.setattr(git_content_repo, "_repo", repository)
    monkeypatch.setattr(git_content_repo, "_mode", git_content_repo.LOCAL)
    git_content_repo._read_cache.clear()
    db.init_schema()
    content_sync.full_sync()
    users_store.create_first_admin(*CHEF)
    users_store.create_user(*CLARA, users_store.VIEWER)
    return {"app": importlib.import_module("app.main").app, "content": content, "repo": repository}


def pages_of(project_slug: str) -> dict[str, dict]:
    project = projects_store.get_project_by_slug(project_slug)
    slugs = {p["slug"] for p in pages_store.list_project_pages(project["id"])}
    return {slug: pages_store.get_page_by_slug(project["id"], slug) for slug in slugs}


def full_page(project_slug: str, slug: str) -> dict:
    project = projects_store.get_project_by_slug(project_slug)
    return pages_store.get_page_by_slug(project["id"], slug)


PLAIN = {
    "handbuch/README.md": "# Willkommen\n\nStart hier. Siehe [Installation](01-installation/docker.md#vorbereitung).\n",
    "handbuch/01-installation/docker.md": "---\ntitle: Mit Docker\n---\n\n## Vorbereitung\n\n![Diagramm](../bilder/plan.png)\n",
    "handbuch/01-installation/02-update.md": "# Aktualisieren\n\nText.\n",
    "handbuch/01-installation/01-anforderungen.md": "# Anforderungen\n\nText.\n",
    "handbuch/02-betrieb/backup.md": "# Backup\n\n[kaputt](gibts-nicht.md)\n",
    "handbuch/bilder/plan.png": png(),
    "handbuch/notizen.txt": "irgendwas",
    "__MACOSX/handbuch/._README.md": "x",
}


class TestPlainMarkdown:
    def test_preview_writes_nothing_and_says_what_would_happen(self, world):
        commits = len(list(world["repo"].iter_commits()))
        result = importer.plan(make_zip(PLAIN), new_project_name="Handbuch").summary()
        assert len(list(world["repo"].iter_commits())) == commits
        assert result["tool"] == "markdown"
        assert [c["name"] for c in result["categories"]] == ["Allgemein", "Installation", "Betrieb"]
        installation = result["categories"][1]["pages"]
        # Numbered prefixes order the pages; the title comes from the file.
        assert [p["title"] for p in installation] == ["Anforderungen", "Aktualisieren", "Mit Docker"]
        assert result["assets"] == 1
        assert {s["path"] for s in result["skipped"]} == {"notizen.txt"}
        assert any("gibts-nicht.md" in w["message"] for w in result["warnings"])

    def test_import_creates_drafts_links_and_images_in_one_commit(self, world):
        commits = len(list(world["repo"].iter_commits()))
        importer.apply(make_zip(PLAIN), "chef", new_project_name="Handbuch", archive_name="handbuch.zip")
        assert len(list(world["repo"].iter_commits())) == commits + 1
        pages = pages_of("handbuch")
        assert set(pages) == {"willkommen", "mit-docker", "aktualisieren", "anforderungen", "backup"}
        assert not any(p["published"] for p in pages.values())
        start = full_page("handbuch", "willkommen")
        # The heading became the title and is not repeated in the body.
        assert not start["markdown_content"].lstrip().startswith("# Willkommen")
        assert "(/p/handbuch/pages/mit-docker#vorbereitung)" in start["markdown_content"]
        docker = full_page("handbuch", "mit-docker")
        assert "![Diagramm](../assets/imported/bilder/plan.png)" in docker["markdown_content"]
        assert (world["content"] / "handbuch/assets/imported/bilder/plan.png").read_bytes() == png()

    def test_an_existing_project_keeps_everything_it_had(self, world):
        # Two folders, so neither is taken for a wrapper around the archive.
        archive = make_zip({"guide/install.md": "# Install\n\nNeu.\n", "faq/fragen.md": "# Fragen\n"})
        importer.apply(archive, "chef", project_slug="alt")
        pages = pages_of("alt")
        assert full_page("alt", "install")["markdown_content"].strip() == "Alt."
        assert "install-2" in pages and pages["install-2"]["published"] is False
        categories = {c["slug"] for c in __import__("app.services.categories_store", fromlist=["x"]).list_categories(
            projects_store.get_project_by_slug("alt")["id"])}
        assert categories == {"guide", "guide-2", "faq"}


class TestTools:
    def test_mkdocs_nav_order_titles_and_admonitions(self, world):
        archive = make_zip({
            "mkdocs.yml": "site_name: X\nmarkdown_extensions:\n  - pymdownx.superfences:\n      custom_fences:\n"
                          "        - format: !!python/name:pymdownx.superfences.fence_code_format\n"
                          "nav:\n  - Start: index.md\n  - Anleitung:\n    - Zweitens: guide/b.md\n    - Erstens: guide/a.md\n",
            "docs/index.md": "Hallo\n\n!!! warning \"Achtung\"\n    Erst sichern.\n\n    Wirklich.\n\nDanach.\n",
            "docs/guide/a.md": "A\n",
            "docs/guide/b.md": "B\n",
            "README.md": "Nicht Teil der Doku.\n",
        })
        result = importer.plan(archive, new_project_name="Mk").summary()
        assert result["tool"] == "mkdocs"
        assert [p["title"] for p in result["categories"][1]["pages"]] == ["Zweitens", "Erstens"]
        importer.apply(archive, "chef", new_project_name="Mk")
        body = full_page("mk", "start")["markdown_content"]
        assert "> [!WARNING]\n> **Achtung**\n>\n> Erst sichern.\n>\n> Wirklich." in body
        assert "Danach." in body

    def test_gitbook_summary_and_hints(self, world):
        archive = make_zip({
            "SUMMARY.md": "# Summary\n\n* [Einführung](README.md)\n* [Zweite Seite](kapitel/zwei.md)\n* [Erste Seite](kapitel/eins.md)\n",
            "README.md": "{% hint style=\"danger\" %}\nVorsicht!\n{% endhint %}\n\n{% embed url=\"https://example.com/v\" %}\n",
            "kapitel/eins.md": "Eins\n",
            "kapitel/zwei.md": "Zwei\n",
        })
        result = importer.plan(archive, new_project_name="Gb").summary()
        assert result["tool"] == "gitbook"
        assert [p["title"] for p in result["categories"][1]["pages"]] == ["Zweite Seite", "Erste Seite"]
        importer.apply(archive, "chef", new_project_name="Gb")
        body = full_page("gb", "einfuhrung")["markdown_content"]
        assert "> [!CAUTION]\n> Vorsicht!" in body and "<https://example.com/v>" in body

    def test_docusaurus_positions_categories_containers_and_mdx(self, world):
        archive = make_zip({
            "docusaurus.config.js": "module.exports = {}",
            "docs/intro.md": "---\nsidebar_position: 1\n---\n\n# Intro\n\n:::tip[Gut zu wissen]\nKlappt.\n:::\n\n![Logo](/img/logo.png)\n",
            "docs/tutorial/_category_.json": "{\"label\": \"Tutorial\", \"position\": 2}",
            "docs/tutorial/b.mdx": "---\nsidebar_position: 2\n---\nimport Tabs from '@theme/Tabs';\n\n# B\n",
            "docs/tutorial/a.md": "---\nsidebar_position: 1\n---\n# A\n",
            "static/img/logo.png": png(),
        })
        result = importer.plan(archive, new_project_name="Ds").summary()
        assert result["tool"] == "docusaurus"
        assert [c["name"] for c in result["categories"]] == ["Allgemein", "Tutorial"]
        assert [p["title"] for p in result["categories"][1]["pages"]] == ["A", "B"]
        assert any("MDX" in w["message"] for w in result["warnings"])
        importer.apply(archive, "chef", new_project_name="Ds")
        body = full_page("ds", "intro")["markdown_content"]
        assert "> [!TIP]\n> **Gut zu wissen**\n>\n> Klappt." in body
        assert "](../assets/imported/static/img/logo.png)" in body
        assert "import Tabs" not in full_page("ds", "b")["markdown_content"]

    def test_obsidian_wiki_links_embeds_and_callouts(self, world):
        archive = make_zip({
            ".obsidian/app.json": "{}",
            "Notizen/Server.md": "Siehe [[Backup Plan|den Plan]] und [[Backup Plan#Ablauf]].\n\n![[schema.png]]\n\n> [!info] Hinweis\n> Text.\n",
            "Notizen/Backup Plan.md": "## Ablauf\n",
            "Anhänge/schema.png": png(),
        })
        assert importer.plan(archive, new_project_name="Ob").tool == "obsidian"
        importer.apply(archive, "chef", new_project_name="Ob")
        body = full_page("ob", "server")["markdown_content"]
        assert "[den Plan](/p/ob/pages/backup-plan)" in body
        assert "(/p/ob/pages/backup-plan#ablauf)" in body
        assert "../assets/imported/anhange/schema.png" in body
        assert "> [!NOTE]\n> **Hinweis**\n> Text." in body

    def test_code_blocks_are_left_alone(self, world):
        archive = make_zip({"a.md": "# A\n\n```md\n!!! note\n    nicht umwandeln\n[x](b.md)\n```\n", "b.md": "B\n"})
        importer.apply(archive, "chef", new_project_name="Code")
        body = full_page("code", "a")["markdown_content"]
        assert "!!! note\n    nicht umwandeln\n[x](b.md)" in body


class TestUntrustedArchives:
    def test_not_a_zip(self, world):
        with pytest.raises(importer.ImportError_, match="not a ZIP"):
            importer.plan(b"hello", new_project_name="X")

    def test_paths_that_climb_out_are_refused(self, world):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../../etc/evil.md", "x")
        with pytest.raises(importer.ImportError_, match="unsafe path"):
            importer.plan(buffer.getvalue(), new_project_name="X")

    def test_a_zip_bomb_is_refused(self, world):
        archive = make_zip({"a.md": "# A\n", "big.png": b"\x00" * (5 * 1024 * 1024)})
        with pytest.raises(importer.ImportError_, match="unpacks to far more"):
            importer.plan(archive, new_project_name="X")

    def test_a_fake_image_is_not_copied(self, world):
        archive = make_zip({"a.md": "![x](evil.png)\n", "evil.png": b"<script>alert(1)</script>"})
        result = importer.plan(archive, new_project_name="X").summary()
        assert result["assets"] == 0
        assert any(s["path"] == "evil.png" for s in result["skipped"])

    def test_no_markdown_no_import(self, world):
        with pytest.raises(importer.ImportError_, match="no Markdown"):
            importer.plan(make_zip({"a.png": png()}), new_project_name="X")


class TestEndpoints:
    def client(self, world, user):
        c = TestClient(world["app"])
        assert c.post("/api/auth/login", json={"username": user[0], "password": user[1]}, headers=ORIGIN).status_code == 200
        return c

    def test_preview_then_import(self, world):
        chef = self.client(world, CHEF)
        archive = make_zip(PLAIN)
        preview = chef.post("/api/admin/import/preview?name=Handbuch", content=archive, headers=ORIGIN)
        assert preview.status_code == 200 and preview.json()["pages"] == 5
        done = chef.post("/api/admin/import?name=Handbuch&filename=handbuch.zip", content=archive, headers=ORIGIN)
        assert done.status_code == 200, done.text
        assert len(pages_of("handbuch")) == 5

    def test_a_bad_archive_is_a_400_with_a_reason(self, world):
        r = self.client(world, CHEF).post("/api/admin/import/preview?name=X", content=b"nope", headers=ORIGIN)
        assert r.status_code == 400 and "ZIP" in r.json()["detail"]

    def test_exactly_one_target(self, world):
        r = self.client(world, CHEF).post("/api/admin/import/preview?name=X&project=alt", content=b"", headers=ORIGIN)
        assert r.status_code == 400

    def test_a_read_only_account_cannot_import(self, world):
        r = self.client(world, CLARA).post("/api/admin/import/preview?name=X", content=make_zip(PLAIN), headers=ORIGIN)
        assert r.status_code == 403


def test_a_github_callout_keeps_its_kind(world):
    importer.apply(make_zip({"a.md": "# A\n\n> [!CAUTION]\n> Rot.\n\n> [!danger] Obsidian\n> Auch rot.\n"}), "chef", new_project_name="Gh")
    text = full_page("gh", "a")["markdown_content"]
    assert "> [!CAUTION]\n> Rot." in text
    assert "> [!CAUTION]\n> **Obsidian**" in text


def test_inline_code_is_never_converted(world):
    body = "Write `{% hint style=\"info\" %}`, `[[wiki links]]` or `![x](../assets/x.png)` -- as examples.\n"
    importer.apply(make_zip({"a.md": "# A\n\n" + body}), "chef", new_project_name="Ic")
    assert full_page("ic", "a")["markdown_content"].strip() == body.strip()
