"""Export the public documentation as a static website: one zip of plain
HTML files that open from a disk, a USB stick or any web server, with no
DocuWaves running.

WHAT IS IN IT is what an anonymous reader can see right now: published
pages of projects that are not private, in each project's default version
and in the site's default language (a page with no text in that language
gets its best other one, as on the site). Drafts, private projects, frozen
versions and other languages are not.

LAYOUT mirrors the content repository, so the relative image paths the
Markdown already uses (`../assets/x.png`) keep working without rewriting:

    index.html                       the projects
    style.css
    <project>/index.html             its categories and pages
    <project>/<category>/<page>.html
    <project>/assets/...             the project's images

Links between pages written as site addresses (/p/<project>/pages/<slug>)
or as file paths (other-page.md) are rewritten to the exported files.

RENDERING is markdown-it on the server: CommonMark with tables,
strikethrough and task lists, callouts in GitHub's `> [!NOTE]` syntax.
Raw HTML in a page is escaped, as it is on the site, and HTML comments
(the tab markers) are dropped. Diagrams and formulas are exported as their
source text: drawing them needs the JavaScript the static site leaves out.
"""
import html
import io
import posixpath
import re
import zipfile
from datetime import datetime, timezone

from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

from app.services import (
    categories_store,
    content_versions,
    pages_store,
    projects_store,
    site_branding,
    site_languages,
    snippets,
)

_CALLOUT = re.compile(r"^<p>\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(?:<br>\s*)?", re.IGNORECASE)
_CALLOUT_LABELS = {
    "de": {"note": "Hinweis", "tip": "Tipp", "important": "Wichtig", "warning": "Warnung", "caution": "Vorsicht"},
    "en": {"note": "Note", "tip": "Tip", "important": "Important", "warning": "Warning", "caution": "Caution"},
}
_SITE_LINK = re.compile(r'href="/p/([^/"#?]+)(?:/(pages|c)/([^/"#?]+))?/?(#[^"]*)?"')
_FILE_LINK = re.compile(r'href="(?![a-z][a-z0-9+.-]*:|/|#)([^"#?]+)\.md(#[^"]*)?"', re.IGNORECASE)


def _renderer() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True, "linkify": False, "typographer": False})
    md.enable(["table", "strikethrough"])
    md.use(tasklists_plugin)

    # html=True only so that comments are recognised as such and can be
    # dropped. Every other piece of raw HTML is shown as text, exactly as the
    # site's renderer does (it never turns raw HTML on).
    def html_block(_renderer, tokens, idx, _options, _env):
        content = tokens[idx].content
        return "" if content.lstrip().startswith("<!--") else f"<p>{html.escape(content)}</p>\n"

    def html_inline(_renderer, tokens, idx, _options, _env):
        content = tokens[idx].content
        if content.startswith('<input class="task-list-item-checkbox"'):
            return content  # the task list plugin's own checkbox, not page text
        return "" if content.startswith("<!--") else html.escape(content)

    md.add_render_rule("html_block", html_block)
    md.add_render_rule("html_inline", html_inline)
    return md


_BADGE = re.compile(r"<code>badge:(?:(info|success|warning|danger|neutral):)?([^<]+)</code>", re.IGNORECASE)


def _badges(rendered: str) -> str:
    """`badge:Beta` written as inline code is a small label on the site
    (frontend lib/blocks.ts); here too, rather than code nobody wrote."""
    return _BADGE.sub(
        lambda m: f'<span class="badge badge-{(m.group(1) or "info").lower()}">{m.group(2).strip()}</span>',
        rendered,
    )


def _callouts(rendered: str, language: str) -> str:
    labels = _CALLOUT_LABELS["de" if language.startswith("de") else "en"]

    def replace(match: re.Match) -> str:
        body = match.group(1)
        inner = _CALLOUT.match(body.lstrip())
        if not inner:
            return match.group(0)
        kind = inner.group(1).lower()
        rest = "<p>" + body.lstrip()[inner.end():]
        if rest.startswith("<p></p>"):
            rest = rest[len("<p></p>"):]
        return f'<aside class="callout callout-{kind}"><strong>{labels[kind]}</strong>\n{rest}</aside>'

    return re.sub(r"<blockquote>\n(.*?)</blockquote>", replace, rendered, flags=re.DOTALL)


def _relative(from_dir: str, target: str) -> str:
    return posixpath.relpath(target, from_dir or ".")


class _Site:
    """Every exported page's file, for rewriting links between them."""

    def __init__(self):
        self.pages: dict[tuple[str, str], str] = {}  # (project, page slug) -> path
        self.categories: dict[tuple[str, str], str] = {}  # (project, category slug) -> path of its first page
        self.projects: set[str] = set()

    def rewrite(self, rendered: str, project_slug: str, here: str) -> str:
        directory = posixpath.dirname(here)

        def site_link(match: re.Match) -> str:
            project, kind, slug, fragment = match.group(1), match.group(2), match.group(3), match.group(4) or ""
            if kind == "pages":
                target = self.pages.get((project, slug))
            elif kind == "c":
                target = f"{project}/index.html" if (project, slug) in self.categories else None
                fragment = f"#{slug}" if target else fragment
            else:
                target = f"{project}/index.html" if project in self.projects else None
            if target is None:
                return match.group(0)
            return f'href="{_relative(directory, target)}{fragment}"'

        def file_link(match: re.Match) -> str:
            path, fragment = match.group(1), match.group(2) or ""
            slug = posixpath.basename(path)
            target = self.pages.get((project_slug, slug))
            if target is None:
                return match.group(0)
            return f'href="{_relative(directory, target)}{fragment}"'

        return _FILE_LINK.sub(file_link, _SITE_LINK.sub(site_link, rendered))


_STYLE = """:root{--bg:#fff;--fg:#1c1f24;--muted:#5d6570;--border:#e3e6ea;--accent:#2563eb;--surface:#f6f7f9}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--fg:#e7e9ec;--muted:#9aa3ad;--border:#2a2f36;--accent:#7aa7ff;--surface:#1a1d22}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--accent)}header{border-bottom:1px solid var(--border);padding:12px 16px}header a{color:var(--fg);text-decoration:none;font-weight:600}
.layout{display:grid;grid-template-columns:240px minmax(0,1fr);gap:32px;max-width:1100px;margin:0 auto;padding:24px 16px}
nav ul{list-style:none;margin:0 0 16px;padding:0}nav li{margin:2px 0}nav h2{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:16px 0 4px}
nav a{color:var(--fg);text-decoration:none;font-size:14px}nav a[aria-current]{color:var(--accent);font-weight:600}
main{min-width:0}main.wide{max-width:800px;margin:0 auto;padding:24px 16px}
pre{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px;overflow:auto}code{font-size:.9em}
table{border-collapse:collapse;display:block;overflow:auto}th,td{border:1px solid var(--border);padding:6px 10px;text-align:left}
img{max-width:100%}blockquote{margin:0;padding:0 16px;border-left:3px solid var(--border);color:var(--muted)}
.callout{border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:8px;padding:8px 14px;margin:16px 0;background:var(--surface)}
.callout-warning,.callout-caution{border-left-color:#d97706}.callout strong{display:block}
.tiles{list-style:none;padding:0;display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(220px,1fr))}
.tiles li{border:1px solid var(--border);border-radius:10px;padding:14px}
.badge{display:inline-block;padding:0 .5em;border-radius:999px;font-size:.75em;font-weight:600;border:1px solid currentColor;color:#3b82f6}
.badge-success{color:#16a34a}.badge-warning{color:#d97706}.badge-danger{color:#dc2626}.badge-neutral{color:var(--muted)}footer{color:var(--muted);font-size:13px;text-align:center;padding:24px 16px}
@media (max-width:760px){.layout{grid-template-columns:1fr}nav{border-bottom:1px solid var(--border)}}
"""


def _document(title: str, site_name: str, language: str, root: str, body: str) -> str:
    return (
        f'<!doctype html>\n<html lang="{html.escape(language or "en")}">\n<head>\n<meta charset="utf-8">\n'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        f'<link rel="stylesheet" href="{root}style.css">\n</head>\n<body>\n'
        f'<header><a href="{root}index.html">{html.escape(site_name)}</a></header>\n{body}\n'
        f"<footer>{html.escape(site_name)}</footer>\n</body>\n</html>\n"
    )


def _nav(project: dict, chapters: list[tuple[dict, list[dict]]], current: str, here: str) -> str:
    directory = posixpath.dirname(here)
    parts = [f'<nav><a href="{_relative(directory, project["slug"] + "/index.html")}"><strong>'
             f'{html.escape(project["name"])}</strong></a>']
    for category, pages in chapters:
        parts.append(f"<h2>{html.escape(category['name'])}</h2><ul>")
        for page in pages:
            path = f"{project['slug']}/{category['slug']}/{page['slug']}.html"
            mark = ' aria-current="page"' if path == current else ""
            parts.append(f'<li><a href="{_relative(directory, path)}"{mark}>{html.escape(page["title"])}</a></li>')
        parts.append("</ul>")
    parts.append("</nav>")
    return "".join(parts)


def build(target) -> dict:
    """Writes the zip to `target` (a path or a binary file object). Returns
    how many projects and pages went in."""
    language = site_languages.default_language()
    branding = site_branding.read_branding()
    site_name = site_languages.pick(branding["name"], branding.get("name_i18n") or {}, language)
    md = _renderer()
    site = _Site()

    # Pass 1: what exists, so every link can be rewritten in pass 2.
    exported = []
    for project in projects_store.list_projects():
        if project.get("private"):
            continue
        version = content_versions.default_version(project["slug"])
        chapters = []
        for category in categories_store.list_categories(project["id"], language, version):
            pages = pages_store.list_pages(category["id"], published_only=True, language=language)
            if not pages:
                continue
            chapters.append((category, pages))
            site.categories[(project["slug"], category["slug"])] = ""
            for page in pages:
                site.pages[(project["slug"], page["slug"])] = f"{project['slug']}/{category['slug']}/{page['slug']}.html"
        if chapters:
            site.projects.add(project["slug"])
            exported.append((project, version, chapters))

    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("style.css", _STYLE)
        tiles = "".join(
            f'<li><a href="{p["slug"]}/index.html"><strong>{html.escape(p["name"])}</strong></a>'
            f"<p>{html.escape(p.get('description') or '')}</p></li>"
            for p, _v, _c in exported
        )
        archive.writestr(
            "index.html",
            _document(site_name, site_name, language, "", f'<main class="wide"><h1>{html.escape(site_name)}</h1>'
                      f'<ul class="tiles">{tiles}</ul></main>'),
        )
        for project, version, chapters in exported:
            slug = project["slug"]
            sections = "".join(
                f'<h2 id="{html.escape(c["slug"])}">{html.escape(c["name"])}</h2><ul>'
                + "".join(
                    f'<li><a href="{c["slug"]}/{p["slug"]}.html">{html.escape(p["title"])}</a></li>' for p in pages
                )
                + "</ul>"
                for c, pages in chapters
            )
            description = f"<p>{html.escape(project['description'])}</p>" if project.get("description") else ""
            archive.writestr(
                f"{slug}/index.html",
                _document(project["name"], site_name, language, "../",
                          f'<main class="wide"><h1>{html.escape(project["name"])}</h1>{description}{sections}</main>'),
            )
            for category, pages in chapters:
                for entry in pages:
                    page = pages_store.get_page(entry["id"])
                    if page is None:
                        continue
                    here = f"{slug}/{category['slug']}/{page['slug']}.html"
                    body = snippets.resolve(page["markdown_content"], slug, page["version"], page["language"])
                    rendered = site.rewrite(_badges(_callouts(md.render(body), page["language"] or language)), slug, here)
                    article = f"<article><h1>{html.escape(page['title'])}</h1>\n{rendered}</article>"
                    archive.writestr(
                        here,
                        _document(f"{page['title']} – {project['name']}", site_name, page["language"] or language,
                                  "../../", f'<div class="layout">{_nav(project, chapters, here, here)}'
                                  f"<main>{article}</main></div>"),
                    )
                    count += 1
            assets = content_versions.content_dir(slug, version) / "assets"
            if assets.is_dir():
                for file in sorted(assets.rglob("*")):
                    if file.is_file() and not file.name.startswith("."):
                        archive.write(file, f"{slug}/assets/{file.relative_to(assets).as_posix()}")
    return {"projects": len(exported), "pages": count}


def archive_name(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    return f"docuwaves-site-{stamp}.zip"


def build_bytes() -> bytes:
    """For tests: the zip in memory."""
    buffer = io.BytesIO()
    build(buffer)
    return buffer.getvalue()
