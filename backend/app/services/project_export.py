"""One project to take away: as an EPUB for an e-reader, or as a zip of
Markdown files for another tool.

WHAT IS IN IT is what the print view shows (routers/public_content.py,
/book): every published page of one version of the project, in the
reader's language (a page without that language gets its best other one),
in the sidebar's order, with snippets and variables filled in. A private
project is only exported for someone who may read it -- the route checks
that, as for every other public endpoint.

LAYOUT, in both, mirrors the content repository -- `<category>/<page>` next
to `assets/` -- so the relative image paths the Markdown already uses
(`../assets/x.png`) keep working without being rewritten. Links between
pages written as site addresses (/p/<project>/pages/<slug>) or as file
paths (other-page.md) point at the exported files; links to anything else
on the site become absolute when PUBLIC_BASE_URL is set.

THE EPUB is EPUB 3: XHTML pages rendered like the static export
(services/static_export.py) -- callouts included, raw HTML escaped --, a
table of contents per category, and the project's images and audio.
Diagrams and formulas stay as their source text, as in the static export.

THE MARKDOWN ZIP holds each page with a `title:` front matter and an
`index.md` listing them; it is the documentation as plain files, not a
backup -- the full export under Diagnostics is that.
"""
import html
import io
import posixpath
import re
import uuid
import zipfile
from datetime import datetime, timezone

from app.services import (
    categories_store,
    content_versions,
    pages_store,
    site_branding,
    site_languages,
    snippets,
    static_export,
)
from app.settings import settings

MAX_PAGES = 1000

_SITE_LINK = re.compile(r'(href="|\]\()/p/([^/"#?)\s]+)(?:/(pages|c)/([^/"#?)\s]+))?/?(#[^")\s]*)?(?=[")])')
_FILE_LINK = re.compile(r'(href="|\]\()(?![a-z][a-z0-9+.-]*:|/|#)([^"#?)\s]+)\.md(#[^")\s]*)?(?=[")])', re.IGNORECASE)
_ROOT_LINK = re.compile(r'(href="|src="|\]\()/(?!/)')
_VOID = re.compile(r"<(br|hr|img|input|col|wbr|source)(\s[^<>]*?)?\s*/?>", re.IGNORECASE)
_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
}


def chapters(project: dict, language: str, version: str) -> list[tuple[dict, list[dict]]]:
    """[(category, [page with resolved markdown_content])] in reading order."""
    listed = pages_store.list_project_pages(project["id"], published_only=True, language=language, version=version)
    by_category: dict[int, list[dict]] = {}
    for entry in listed[:MAX_PAGES]:
        by_category.setdefault(entry["category_id"], []).append(entry)
    result = []
    for category in categories_store.list_categories(project["id"], language, version):
        pages = []
        for entry in by_category.get(category["id"], []):
            page = pages_store.get_page(entry["id"])
            if page is None or not page["published"]:
                continue
            page = dict(page)
            page["markdown_content"] = snippets.resolve(
                page["markdown_content"], project["slug"], page["version"], page["language"]
            )
            pages.append(page)
        if pages:
            result.append((category, pages))
    return result


def file_name(project: dict, version: str, extension: str) -> str:
    suffix = f"-{version}" if version and version != content_versions.default_version(project["slug"]) else ""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{project['slug']}{suffix}")
    return f"{safe}{extension}"


def _site_name(language: str) -> str:
    branding = site_branding.read_branding()
    return site_languages.pick(branding["name"], branding.get("name_i18n") or {}, language)


class _Links:
    """Rewrites links in rendered HTML or in Markdown to the exported files."""

    def __init__(self, project_slug: str, extension: str, contents: str):
        self.project = project_slug
        self.extension = extension
        self.contents = contents  # the table of contents, relative to the root
        self.pages: dict[str, str] = {}
        self.categories: set[str] = set()

    def add(self, category_slug: str, page_slug: str) -> None:
        self.pages[page_slug] = f"{category_slug}/{page_slug}{self.extension}"
        self.categories.add(category_slug)

    def rewrite(self, text: str, here: str) -> str:
        directory = posixpath.dirname(here)

        def site_link(match: re.Match) -> str:
            lead, project, kind, slug, fragment = (match.group(i) for i in range(1, 6))
            fragment = fragment or ""
            target = None
            if project == self.project:
                if kind == "pages":
                    target = self.pages.get(slug)
                elif kind is None or (kind == "c" and slug in self.categories):
                    target = self.contents
            if target is None:
                return match.group(0)
            return lead + posixpath.relpath(target, directory or ".") + fragment

        def file_link(match: re.Match) -> str:
            lead, path, fragment = match.group(1), match.group(2), match.group(3) or ""
            target = self.pages.get(posixpath.basename(path))
            if target is None:
                return match.group(0)
            return lead + posixpath.relpath(target, directory or ".") + fragment

        text = _FILE_LINK.sub(file_link, _SITE_LINK.sub(site_link, text))
        if settings.public_base_url:
            # What is left pointing at the site cannot be in the file: send
            # it to the site itself rather than to a path that resolves
            # nowhere on an e-reader or a disk.
            text = _ROOT_LINK.sub(lambda m: m.group(1) + settings.public_base_url + "/", text)
        return text


def _assets(project_slug: str, version: str):
    directory = content_versions.content_dir(project_slug, version) / "assets"
    if not directory.is_dir():
        return
    for file in sorted(directory.rglob("*")):
        if file.is_file() and not file.name.startswith("."):
            yield file, file.relative_to(directory).as_posix()


# ---- Markdown ----


def markdown_zip(project: dict, language: str, version: str) -> tuple[bytes, int]:
    """(the zip, how many pages are in it)."""
    found = chapters(project, language, version)
    links = _Links(project["slug"], ".md", "index.md")
    for category, pages in found:
        for page in pages:
            links.add(category["slug"], page["slug"])

    buffer = io.BytesIO()
    count = 0
    root = project["slug"]
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        index = [f"# {project['name']}", ""]
        if project.get("description"):
            index += [project["description"], ""]
        for category, pages in found:
            index += [f"## {category['name']}", ""]
            for page in pages:
                here = links.pages[page["slug"]]
                index.append(f"- [{page['title']}]({here})")
                front = "---\ntitle: " + _yaml(page["title"]) + "\n---\n\n"
                body = links.rewrite(page["markdown_content"], here).strip() + "\n"
                archive.writestr(f"{root}/{here}", front + body)
                count += 1
            index.append("")
        archive.writestr(f"{root}/index.md", "\n".join(index).rstrip() + "\n")
        for file, relative in _assets(project["slug"], version):
            archive.write(file, f"{root}/assets/{relative}")
    return buffer.getvalue(), count


def _yaml(text: str) -> str:
    import json

    return json.dumps(text, ensure_ascii=False)  # a JSON string is a valid YAML scalar


# ---- EPUB ----

_EPUB_STYLE = """body{font-family:serif;line-height:1.5}h1,h2,h3{font-family:sans-serif;line-height:1.25}
pre{white-space:pre-wrap;font-size:.85em;background:#f4f4f4;padding:.5em}code{font-size:.9em}
table{border-collapse:collapse}th,td{border:1px solid #999;padding:.2em .4em}img{max-width:100%}
blockquote{margin-left:1em;padding-left:.8em;border-left:3px solid #ccc}
.callout{border:1px solid #bbb;border-left:4px solid #2563eb;padding:.3em .8em;margin:1em 0}
.callout-warning,.callout-caution{border-left-color:#d97706}.callout strong{display:block}
nav ol{list-style:none;padding-left:1em}
"""


def _xhtml(fragment: str) -> str:
    """markdown-it writes HTML; an EPUB needs XML. Void elements are the one
    difference its output has (text is escaped already)."""
    def close(match: re.Match) -> str:
        attributes = (match.group(2) or "").rstrip().rstrip("/").rstrip()
        return f"<{match.group(1).lower()}{attributes} />"

    return _VOID.sub(close, fragment)


def _page_document(title: str, language: str, stylesheet: str, body: str) -> str:
    lang = html.escape(language or "en")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" '
        f'xml:lang="{lang}">\n<head>\n<meta charset="utf-8" />\n<title>{html.escape(title)}</title>\n'
        f'<link rel="stylesheet" type="text/css" href="{stylesheet}" />\n</head>\n<body>\n{body}\n</body>\n</html>\n'
    )


def epub(project: dict, language: str, version: str, now: datetime | None = None) -> tuple[bytes, int]:
    """(the EPUB, how many pages are in it)."""
    found = chapters(project, language, version)
    language = language or site_languages.default_language() or "en"
    links = _Links(project["slug"], ".xhtml", "nav.xhtml")
    for category, pages in found:
        for page in pages:
            links.add(category["slug"], page["slug"])

    md = static_export._renderer()
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    identity = uuid.uuid5(uuid.NAMESPACE_URL, f"{settings.public_base_url or 'docuwaves'}/p/{project['slug']}/{version}")
    title = project["name"] + (f" ({version})" if version and version != content_versions.default_version(project["slug"]) else "")

    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="style" href="style.css" media-type="text/css"/>',
    ]
    spine = ['<itemref idref="nav"/>']
    toc = []
    buffer = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buffer, "w") as archive:
        # The mimetype file first and uncompressed: that is how a reader
        # recognises the zip as an EPUB at all.
        archive.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)

        def put(name: str, data) -> None:
            archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

        put(
            "META-INF/container.xml",
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            "</rootfiles>\n</container>\n",
        )
        put("OEBPS/style.css", _EPUB_STYLE)
        for category, pages in found:
            entries = []
            for page in pages:
                here = links.pages[page["slug"]]
                page_language = page["language"] or language
                rendered = static_export._callouts(md.render(page["markdown_content"]), page_language)
                body = f"<h1>{html.escape(page['title'])}</h1>\n{_xhtml(links.rewrite(rendered, here))}"
                put(f"OEBPS/{here}", _page_document(page["title"], page_language, "../style.css", body))
                count += 1
                manifest.append(f'<item id="p{count}" href="{html.escape(here)}" media-type="application/xhtml+xml"/>')
                spine.append(f'<itemref idref="p{count}"/>')
                entries.append(f'<li><a href="{html.escape(here)}">{html.escape(page["title"])}</a></li>')
            toc.append(f"<li><span>{html.escape(category['name'])}</span><ol>{''.join(entries)}</ol></li>")
        assets = 0
        for file, relative in _assets(project["slug"], version):
            media_type = _MEDIA_TYPES.get(posixpath.splitext(relative)[1].lower())
            if media_type is None:
                continue  # video and documents: not something an e-reader shows
            assets += 1
            archive.write(file, f"OEBPS/assets/{relative}", compress_type=zipfile.ZIP_DEFLATED)
            manifest.append(f'<item id="a{assets}" href="assets/{html.escape(relative)}" media-type="{media_type}"/>')

        contents_label = "Inhalt" if language.startswith("de") else "Contents"
        put(
            "OEBPS/nav.xhtml",
            _page_document(
                title, language, "style.css",
                f"<h1>{html.escape(title)}</h1>\n"
                + (f"<p>{html.escape(project['description'])}</p>\n" if project.get("description") else "")
                + f'<nav epub:type="toc" id="toc"><h2>{contents_label}</h2><ol>{"".join(toc)}</ol></nav>',
            ),
        )
        publisher = _site_name(language)
        put(
            "OEBPS/content.opf",
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">\n'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            f'<dc:identifier id="id">urn:uuid:{identity}</dc:identifier>\n'
            f"<dc:title>{html.escape(title)}</dc:title>\n"
            f"<dc:language>{html.escape(language)}</dc:language>\n"
            + (f"<dc:publisher>{html.escape(publisher)}</dc:publisher>\n" if publisher else "")
            + (f"<dc:description>{html.escape(project['description'])}</dc:description>\n" if project.get("description") else "")
            + f'<meta property="dcterms:modified">{stamp}</meta>\n'
            "</metadata>\n"
            f"<manifest>\n{chr(10).join(manifest)}\n</manifest>\n"
            f"<spine>\n{chr(10).join(spine)}\n</spine>\n"
            "</package>\n",
        )
    return buffer.getvalue(), count
