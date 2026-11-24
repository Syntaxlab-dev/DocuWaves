"""A project as an EPUB or a Markdown zip (services/project_export.py)."""
import io
import xml.dom.minidom
import zipfile

from app.settings import settings

from tests.test_static_export import world  # noqa: F401 -- the fixture


def unzip(data: bytes) -> dict[str, bytes]:
    archive = zipfile.ZipFile(io.BytesIO(data))
    return {name: archive.read(name) for name in archive.namelist()}


def test_epub_structure(world):
    r = world.get("/api/public/projects/docs/export/epub")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/epub+zip"
    assert 'filename="docs.epub"' in r.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(r.content))
    first = archive.infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    files = unzip(r.content)
    assert files["mimetype"] == b"application/epub+zip"
    assert {"META-INF/container.xml", "OEBPS/content.opf", "OEBPS/nav.xhtml", "OEBPS/guide/intro.xhtml",
            "OEBPS/api/tokens.xhtml", "OEBPS/assets/logo.png"} <= set(files)
    assert "OEBPS/guide/setup.xhtml" not in files  # a draft
    # Every XML file in it is well-formed.
    for name, data in files.items():
        if name.endswith((".xhtml", ".opf", ".xml")):
            xml.dom.minidom.parseString(data)
    opf = files["OEBPS/content.opf"].decode()
    assert "<dc:title>Docs</dc:title>" in opf and 'properties="nav"' in opf
    assert 'href="assets/logo.png" media-type="image/png"' in opf
    assert opf.index('idref="p1"') < opf.index('idref="p2"')


def test_epub_page_links_and_markup(world):
    page = unzip(world.get("/api/public/projects/docs/export/epub").content)["OEBPS/guide/intro.xhtml"].decode()
    assert 'href="../api/tokens.xhtml#scopes"' in page
    assert 'href="../nav.xhtml"' in page  # a category link: the table of contents
    assert 'src="../assets/logo.png"' in page and "/>" in page
    assert 'class="callout callout-warning"' in page
    assert "<script>" not in page
    nav = unzip(world.get("/api/public/projects/docs/export/epub").content)["OEBPS/nav.xhtml"].decode()
    assert '<nav epub:type="toc"' in nav and 'href="guide/intro.xhtml"' in nav


def test_markdown_zip(world, monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://docs.example.com")
    r = world.get("/api/public/projects/docs/export/markdown")
    assert r.status_code == 200 and 'filename="docs-markdown.zip"' in r.headers["content-disposition"]
    files = unzip(r.content)
    assert {"docs/index.md", "docs/guide/intro.md", "docs/api/tokens.md", "docs/assets/logo.png"} <= set(files)
    intro = files["docs/guide/intro.md"].decode()
    assert intro.startswith('---\ntitle: "Intro"\n---\n')
    assert "[tokens](../api/tokens.md#scopes)" in intro
    assert "[the API](../index.md)" in intro
    assert "![Logo](../assets/logo.png)" in intro
    index = files["docs/index.md"].decode()
    assert "- [Intro](guide/intro.md)" in index and "## API" in index


def test_private_projects_and_unknown_formats(world):
    assert world.get("/api/public/projects/secret/export/epub").status_code == 404
    assert world.get("/api/public/projects/docs/export/pdf").status_code == 404
    assert world.get("/api/public/projects/nope/export/epub").status_code == 404
