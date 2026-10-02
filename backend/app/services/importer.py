"""Import existing documentation from a ZIP of Markdown files.

What a ZIP from most documentation tools looks like -- a folder of `.md`
files with images next to them -- becomes a DocuWaves project:

- a folder is a CATEGORY, a Markdown file a PAGE (DocuWaves has one level
  of categories, so `guide/advanced/` becomes the category "Guide /
  Advanced": flatter, nothing lost); files at the top go into "General";
- titles come from the front matter, else the first `# heading`, else the
  file name; the order from the tool's own navigation when there is one;
- images and media are copied into the project's `assets/`, and every
  relative link is rewritten: to another page -> `/p/<project>/pages/<slug>`,
  to an image -> `../assets/...`;
- callouts in the four common dialects become DocuWaves callouts (GitHub
  syntax, see frontend/src/lib/callouts.ts).

RECOGNISED TOOLS, by what is in the archive:
- MkDocs (`mkdocs.yml`): pages under `docs_dir`, order and titles from `nav`,
  `!!! note "Title"` admonitions;
- GitBook (`SUMMARY.md`): order and titles from the summary,
  `{% hint style="..." %}` blocks;
- Docusaurus (`docusaurus.config.*`): pages under `docs/`, `sidebar_position`
  / `_category_.json`, `:::tip` containers, MDX `import` lines dropped;
- Obsidian (`.obsidian/`): `[[wiki links]]`, `![[embeds]]`, `> [!info]`
  callouts;
- Confluence (an HTML space export): converted to Markdown first, see
  services/import_confluence.py;
- anything else: plain Markdown, numbered prefixes (`01-intro.md`) order it.

TWO STEPS, the same code: `plan()` reads the archive and says what WOULD
happen (pages, categories, images, warnings) without writing anything;
`apply()` runs the same plan and writes it -- every page a DRAFT, never
published, one commit for the whole import, so one revert undoes it.
Existing pages and categories are never overwritten: a name that is taken
gets `-2`.

THE ARCHIVE IS UNTRUSTED. At most 50 MB uploaded, 200 MB unpacked, 5000
entries; an entry that unpacks to far more than it was packed as is a ZIP
bomb and refuses the whole archive; absolute paths and `..` are refused;
only Markdown, the image/media types assets accept anyway (each through the
same byte check, content_assets.rejection_reason) and the few navigation
files above are read at all.
"""
import io
import json
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from urllib.parse import unquote

import frontmatter
import yaml

from app.services import (
    categories_store,
    import_confluence,
    content_assets,
    content_files,
    content_sync,
    content_versions,
    git_content_repo,
    pages_store,
    projects_store,
    site_languages,
)

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
MAX_ENTRIES = 5000
# Real documentation compresses well, but not 200:1 across a megabyte.
_BOMB_RATIO = 200
_BOMB_MIN_BYTES = 1024 * 1024

MARKDOWN_EXTENSIONS = (".md", ".markdown", ".mdx")
_NAV_FILES = ("mkdocs.yml", "mkdocs.yaml", "summary.md", "_category_.json", ".gitbook.yaml")
_SKIP_DIRS = {"__macosx", "node_modules", ".git", ".github", "site", "build", ".docusaurus"}


class ImportError_(Exception):
    """The archive as a whole cannot be imported. `str()` says why, for the
    person who uploaded it."""


@dataclass
class PagePlan:
    source: str
    slug: str
    title: str
    order: int
    body: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class CategoryPlan:
    key: str  # source directory, "" for the top
    slug: str
    name: str
    order: int
    exists: bool = False
    pages: list[PagePlan] = field(default_factory=list)


@dataclass
class Plan:
    tool: str
    project_slug: str
    project_name: str
    new_project: bool
    version: str
    categories: list[CategoryPlan]
    # source path in the archive -> path under the project's assets/
    assets: dict[str, str]
    skipped: list[dict]
    warnings: list[dict]

    def summary(self) -> dict:
        return {
            "tool": self.tool,
            "project": {"slug": self.project_slug, "name": self.project_name, "new": self.new_project},
            "categories": [
                {
                    "slug": c.slug, "name": c.name, "exists": c.exists,
                    "pages": [{"title": p.title, "slug": p.slug, "source": p.source} for p in c.pages],
                }
                for c in self.categories
            ],
            "pages": sum(len(c.pages) for c in self.categories),
            "assets": len(self.assets),
            "skipped": self.skipped,
            "warnings": self.warnings,
        }


# ---- Reading the archive ----


def _clean_path(name: str) -> str | None:
    """The entry's path, or None for anything that has no business being
    extracted anywhere: absolute, `..`, or a drive letter."""
    path = name.replace("\\", "/")
    if path.startswith("/") or re.match(r"^[a-zA-Z]:", path):
        return None
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def _wanted(path: str) -> bool:
    lower = path.lower()
    parts = lower.split("/")
    if any(p in _SKIP_DIRS for p in parts[:-1]):
        return False
    name = parts[-1]
    if name.startswith("._") or name == ".ds_store":
        return False
    if name in _NAV_FILES or name.startswith("docusaurus.config."):
        return True
    if lower.endswith((".html", ".htm")):
        # Read for Confluence exports (services/import_confluence.py); in any
        # other archive plan() lists them as not taken over.
        return not any(p.startswith(".") for p in parts)
    if lower.endswith(MARKDOWN_EXTENSIONS):
        return not any(p.startswith(".") for p in parts)
    return posixpath.splitext(lower)[1] in content_assets.CONTENT_TYPES and not any(p.startswith(".") for p in parts)


def read_archive(data: bytes) -> tuple[dict[str, bytes], set[str], list[dict]]:
    """(files we read, every path in the archive, skipped entries). Raises
    ImportError_ for an archive that must not be read at all."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImportError_(f"The archive is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ImportError_("That is not a ZIP file.") from exc
    infos = [i for i in archive.infolist() if not i.is_dir()]
    if len(infos) > MAX_ENTRIES:
        raise ImportError_(f"The archive has more than {MAX_ENTRIES} files.")
    if sum(i.file_size for i in infos) > MAX_UNPACKED_BYTES:
        raise ImportError_(f"The archive unpacks to more than {MAX_UNPACKED_BYTES // (1024 * 1024)} MB.")
    for info in infos:
        if info.file_size > _BOMB_MIN_BYTES and info.file_size > _BOMB_RATIO * max(info.compress_size, 1):
            raise ImportError_("The archive contains a file that unpacks to far more than it was packed as.")

    files: dict[str, bytes] = {}
    names: set[str] = set()
    skipped: list[dict] = []
    for info in infos:
        path = _clean_path(info.filename)
        if path is None:
            raise ImportError_(f"The archive contains an unsafe path: {info.filename!r}")
        names.add(path)
        if not _wanted(path):
            if not path.lower().startswith("__macosx/") and "/." not in f"/{path}":
                skipped.append({"path": path, "reason": "not a Markdown, image or media file"})
            continue
        with archive.open(info) as handle:
            content = handle.read(info.file_size + 1)
        if len(content) > info.file_size:
            raise ImportError_(f"{path} is larger than the archive says it is.")
        files[path] = content

    # One folder around everything (the way "Compress" on a folder makes a
    # ZIP) is not part of the structure. macOS adds __MACOSX/ and .DS_Store
    # next to it, which do not count as a second folder.
    meaningful = {p for p in names if not p.lower().startswith("__macosx/") and not p.split("/")[-1].startswith(".")}
    tops = {p.split("/", 1)[0] for p in meaningful}
    if len(tops) == 1 and all("/" in p for p in meaningful):
        prefix = next(iter(tops)) + "/"
        files = {p[len(prefix):]: b for p, b in files.items() if p.startswith(prefix)}
        names = {p[len(prefix):] for p in names if p.startswith(prefix)}
        skipped = [{**s, "path": s["path"][len(prefix):]} for s in skipped if s["path"].startswith(prefix)]
    return files, names, skipped


# ---- Which tool, and its navigation ----


class _LenientLoader(yaml.SafeLoader):
    """mkdocs.yml may hold `!!python/name:...` and `!ENV` tags; they say
    nothing about the navigation, so they read as None instead of failing."""


_LenientLoader.add_multi_constructor("", lambda loader, suffix, node: None)


def _text(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n")


@dataclass
class _Layout:
    tool: str
    root: str  # directory the pages live under, "" = everything
    order: dict[str, int]  # page path -> position from the tool's navigation
    titles: dict[str, str]  # page path -> title from the tool's navigation
    static: str = ""  # where `/img/x.png` points (Docusaurus)


def _mkdocs_nav(nav, root: str, order: dict, titles: dict) -> None:
    for item in nav or []:
        if isinstance(item, str):
            order.setdefault(posixpath.join(root, item), len(order))
        elif isinstance(item, dict):
            for title, value in item.items():
                if isinstance(value, str):
                    if value.lower().endswith(MARKDOWN_EXTENSIONS):
                        path = posixpath.normpath(posixpath.join(root, value))
                        order.setdefault(path, len(order))
                        if title:
                            titles[path] = str(title)
                elif isinstance(value, list):
                    _mkdocs_nav(value, root, order, titles)


_SUMMARY_LINK = re.compile(r"^\s*[*+-]\s*\[([^\]]+)\]\(([^)\s]+)\)")


def detect(files: dict[str, bytes], names: set[str]) -> _Layout:
    lower = {p.lower(): p for p in files}
    order: dict[str, int] = {}
    titles: dict[str, str] = {}

    mkdocs = lower.get("mkdocs.yml") or lower.get("mkdocs.yaml")
    if mkdocs:
        try:
            config = yaml.load(_text(files[mkdocs]), Loader=_LenientLoader) or {}
        except yaml.YAMLError:
            config = {}
        root = str(config.get("docs_dir") or "docs").strip("/")
        _mkdocs_nav(config.get("nav"), root, order, titles)
        return _Layout("mkdocs", root, order, titles)

    if any(p.split("/")[-1].lower().startswith("docusaurus.config.") for p in files):
        return _Layout("docusaurus", "docs", order, titles, static="static")

    summary = next((p for p in files if p.split("/")[-1].lower() == "summary.md"), None)
    if summary:
        root = posixpath.dirname(summary)
        for line in _text(files[summary]).split("\n"):
            match = _SUMMARY_LINK.match(line)
            if match:
                path = posixpath.normpath(posixpath.join(root, unquote(match.group(2).split("#")[0])))
                order.setdefault(path, len(order))
                titles[path] = match.group(1).strip()
        return _Layout("gitbook", root, order, titles)

    if any(p.split("/", 1)[0] == ".obsidian" for p in names):
        return _Layout("obsidian", "", order, titles)
    return _Layout("markdown", "", order, titles)


# ---- Names, slugs, order ----

_NUMBER_PREFIX = re.compile(r"^(\d+)[-_. ]+(.+)$")
_INDEX_NAMES = ("index", "readme", "_index")


def _strip_number(name: str) -> tuple[int | None, str]:
    match = _NUMBER_PREFIX.match(name)
    return (int(match.group(1)), match.group(2)) if match else (None, name)


def _pretty(name: str) -> str:
    _, rest = _strip_number(name)
    text = re.sub(r"[-_]+", " ", rest).strip()
    return text[:1].upper() + text[1:] if text else name


def _general_name() -> str:
    return "General" if site_languages.default_language().startswith("en") else "Allgemein"


_FIRST_H1 = re.compile(r"^\s*#\s+(.+?)\s*#*\s*$")


def _first_heading(body: str) -> tuple[str, str]:
    """(title, body without it) when the body starts with a `# heading`:
    DocuWaves shows the page title itself, so keeping the heading would
    print it twice."""
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        match = _FIRST_H1.match(line)
        if match:
            return match.group(1).strip(), "\n".join(lines[:i] + lines[i + 1:]).lstrip("\n")
        break
    return "", body


# ---- Planning ----


def plan(data: bytes, *, project_slug: str = "", new_project_name: str = "") -> Plan:
    """What an import would do. Writes nothing. Exactly one of the two:
    an existing project's slug, or the name of the project to create."""
    files, names, skipped = read_archive(data)
    warnings: list[dict] = []
    html = [p for p in files if p.lower().endswith((".html", ".htm"))]
    if html and import_confluence.looks_like(files):
        files, order, notes = import_confluence.convert(files)
        layout = _Layout("confluence", "", order, {})
        for note in notes:
            source, _, message = note.partition(": ")
            warnings.append({"source": source, "message": message})
    else:
        for path in html:
            files.pop(path)
            skipped.append({"path": path, "reason": "HTML is only imported from a Confluence export"})
        layout = detect(files, names)

    root_prefix = f"{layout.root}/" if layout.root else ""
    markdown = sorted(
        p for p in files
        if p.lower().endswith(MARKDOWN_EXTENSIONS)
        and p.startswith(root_prefix)
        and p.split("/")[-1].lower() != "summary.md"
    )
    if not markdown:
        raise ImportError_("There is no Markdown file in the archive" + (f" under {layout.root}/." if layout.root else "."))

    # -- Target --
    if project_slug:
        project = projects_store.get_project_by_slug(project_slug)
        if project is None:
            raise ImportError_("That project does not exist.")
        version = content_versions.writable_version(project_slug)
        project_name, project_id, new = project["name"], project["id"], False
    else:
        name = (new_project_name or "").strip()
        if not name:
            raise ImportError_("A name for the new project is required.")
        project_slug = content_files.unique_slug(name, projects_store.slug_taken)
        project_name, project_id, version, new = name, None, "", True

    # -- Front matter, titles, positions --
    docs: dict[str, dict] = {}
    for path in markdown:
        raw = _text(files[path])
        try:
            post = frontmatter.loads(raw)
            meta, body = dict(post.metadata), post.content
        except Exception:  # noqa: BLE001 -- broken front matter is the file's problem, not the import's
            meta, body = {}, raw
            warnings.append({"source": path, "message": "front matter could not be read; imported as text"})
        heading, rest = _first_heading(body)
        stem = posixpath.splitext(path.split("/")[-1])[0]
        number, _ = _strip_number(stem)
        # The page's own words first: its front matter, then its heading. The
        # navigation's label is only a fallback -- MkDocs and GitBook show it
        # in the menu but the heading on the page, and taking the label while
        # keeping the heading would put two titles on every page.
        title = str(meta.get("title") or heading or layout.titles.get(path) or meta.get("sidebar_label") or "").strip()
        if not title:
            title = _pretty(path.split("/")[-2]) if stem.lower() in _INDEX_NAMES and "/" in path else _pretty(stem)
        if heading and heading == title:
            body = rest
        position = next(
            (meta.get(k) for k in ("sidebar_position", "nav_order", "weight", "order") if isinstance(meta.get(k), (int, float))),
            None,
        )
        docs[path] = {"title": title, "body": body, "position": position, "number": number, "stem": stem}

    # -- Categories: one per directory --
    def category_key(path: str) -> str:
        rel = path[len(root_prefix):]
        return posixpath.dirname(rel)

    category_meta: dict[str, dict] = {}
    for path in files:
        if path.split("/")[-1] == "_category_.json" and path.startswith(root_prefix):
            try:
                data_json = json.loads(_text(files[path]))
            except ValueError:
                continue
            category_meta[posixpath.dirname(path[len(root_prefix):])] = data_json

    keys = sorted({category_key(p) for p in markdown})
    nav_first = {}
    for path in markdown:
        key = category_key(path)
        if path in layout.order:
            nav_first[key] = min(nav_first.get(key, 1 << 30), layout.order[path])

    def category_sort(key: str):
        meta = category_meta.get(key, {})
        number, _ = _strip_number(key.split("/")[-1]) if key else (None, "")
        return (
            key != "",  # the top level first
            nav_first.get(key, 1 << 30),
            meta.get("position") if isinstance(meta.get("position"), (int, float)) else 1 << 30,
            number if number is not None else 1 << 30,
            key.lower(),
        )

    existing_categories = categories_store.list_categories(project_id, version=version) if project_id else []
    order_base = max((c["sort_order"] for c in existing_categories), default=-1) + 1
    planned_category_slugs: set[str] = set()

    def category_taken(slug: str, _exclude=None) -> bool:
        if slug in planned_category_slugs:
            return True
        return bool(project_id and categories_store.slug_taken(project_id, version, slug))

    categories: list[CategoryPlan] = []
    for index, key in enumerate(sorted(keys, key=category_sort)):
        meta = category_meta.get(key, {})
        name = str(meta.get("label") or "").strip() or (
            " / ".join(_pretty(part) for part in key.split("/")) if key else _general_name()
        )
        slug = content_files.unique_slug(name, category_taken)
        planned_category_slugs.add(slug)
        categories.append(CategoryPlan(key=key, slug=slug, name=name, order=order_base + index))
    by_key = {c.key: c for c in categories}

    # -- Pages: slugs first (links need them), bodies after --
    planned_page_slugs: set[str] = set()

    def page_taken(slug: str, _exclude=None) -> bool:
        if slug in planned_page_slugs:
            return True
        return bool(project_id and pages_store.slug_taken(project_id, version, slug))

    def page_sort(path: str):
        doc = docs[path]
        return (
            path not in layout.order,
            layout.order.get(path, 0),
            doc["stem"].lower() not in _INDEX_NAMES,
            doc["position"] if doc["position"] is not None else 1 << 30,
            doc["number"] if doc["number"] is not None else 1 << 30,
            doc["title"].lower(),
        )

    page_by_path: dict[str, PagePlan] = {}
    for key in keys:
        paths = sorted((p for p in markdown if category_key(p) == key), key=page_sort)
        for position, path in enumerate(paths):
            slug = content_files.unique_slug(docs[path]["title"], page_taken)
            planned_page_slugs.add(slug)
            page = PagePlan(source=path, slug=slug, title=docs[path]["title"], order=position)
            by_key[key].pages.append(page)
            page_by_path[path] = page

    # -- Assets --
    asset_dir = content_files.project_content_dir(project_slug, version) / "assets"
    assets: dict[str, str] = {}
    used_targets: set[str] = set()

    def asset_target(source: str) -> str:
        if source in assets:
            return assets[source]
        rel = source[len(root_prefix):] if source.startswith(root_prefix) else source
        directory, filename = posixpath.split(rel)
        stem, ext = posixpath.splitext(filename)
        safe_dir = "/".join(content_files.make_slug(part) for part in directory.split("/") if part)
        base = posixpath.join("imported", safe_dir, f"{content_files.make_slug(stem)}{ext.lower()}")
        candidate, n = base, 2
        while candidate in used_targets or (asset_dir / candidate).exists():
            if (asset_dir / candidate).exists() and (asset_dir / candidate).read_bytes() == files[source]:
                break  # the very same file is already there: reuse it
            candidate = f"{posixpath.splitext(base)[0]}-{n}{ext.lower()}"
            n += 1
        used_targets.add(candidate)
        assets[source] = candidate
        return candidate

    # -- Bodies --
    stems = {}
    for path in markdown:
        stems.setdefault(docs[path]["stem"].lower(), path)
        stems.setdefault(docs[path]["title"].lower(), path)

    rejected_assets: set[str] = set()
    for path, page in page_by_path.items():
        context = _Context(
            source=path, files=files, layout=layout, project_slug=project_slug, page_by_path=page_by_path,
            stems=stems, asset_target=asset_target, warn=page.warnings, rejected=rejected_assets,
        )
        page.body = convert(docs[path]["body"], context)
        for message in page.warnings:
            warnings.append({"source": path, "message": message})

    for source in sorted(rejected_assets):
        skipped.append({"path": source, "reason": "not accepted as an image or media file"})

    return Plan(
        tool=layout.tool, project_slug=project_slug, project_name=project_name, new_project=new,
        version=version, categories=categories, assets=assets, skipped=skipped, warnings=warnings,
    )


# ---- Converting a page body ----


@dataclass
class _Context:
    source: str
    files: dict[str, bytes]
    layout: _Layout
    project_slug: str
    page_by_path: dict[str, PagePlan]
    stems: dict[str, str]
    asset_target: object
    warn: list[str]
    rejected: set[str]


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")

_KINDS = {
    "note": "NOTE", "info": "NOTE", "abstract": "NOTE", "summary": "NOTE", "tldr": "NOTE", "todo": "NOTE",
    "seealso": "NOTE", "quote": "NOTE", "cite": "NOTE", "example": "NOTE", "question": "NOTE", "faq": "NOTE",
    "help": "NOTE",
    "tip": "TIP", "hint": "TIP", "success": "TIP", "check": "TIP", "done": "TIP",
    "important": "IMPORTANT",
    "warning": "WARNING", "caution": "WARNING", "attention": "WARNING",
    "danger": "CAUTION", "error": "CAUTION", "failure": "CAUTION", "fail": "CAUTION", "missing": "CAUTION",
    "bug": "CAUTION",
}
_GITHUB_KINDS = {"NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION"}
# Docusaurus spells it the other way round: its `caution` is a warning, its
# `danger` the red one.
_GITBOOK_KINDS = {"info": "NOTE", "success": "TIP", "warning": "WARNING", "danger": "CAUTION"}


def _callout(kind: str, title: str, lines: list[str]) -> list[str]:
    out = [f"> [!{_KINDS.get(kind.lower(), 'NOTE')}]"]
    if title:
        out.append(f"> **{title}**")
        out.append(">")
    out += [f"> {line}".rstrip() for line in lines]
    return out


_MKDOCS_ADMONITION = re.compile(r'^(!!!|\?\?\?\+?)\s+(\w+)(?:\s+"([^"]*)")?\s*$')
_DOCUSAURUS_OPEN = re.compile(r"^:::(\w+)(?:\[([^\]]*)\]|\s+(.+))?\s*$")
_GITBOOK_HINT = re.compile(r'^\{%\s*hint\s+style="(\w+)"\s*%\}\s*$')
_GITBOOK_END = re.compile(r"^\{%\s*endhint\s*%\}\s*$")
_GITBOOK_EMBED = re.compile(r'\{%\s*embed\s+url="([^"]+)"[^%]*%\}')
_GITBOOK_TAG = re.compile(r"\{%[^%]*%\}")
_OBSIDIAN_CALLOUT = re.compile(r"^>\s*\[!(\w+)\][+-]?\s*(.*)$")
_MDX_LINE = re.compile(r"^(import|export)\s.+")


def _blocks(markdown: str, context: _Context) -> list[str]:
    """The structural pass: callouts and tool syntax, never inside a fenced
    code block (a tutorial ABOUT MkDocs must keep its `!!! note` example)."""
    lines = markdown.split("\n")
    out: list[str] = []
    fence = None
    i = 0
    mdx_dropped = False
    while i < len(lines):
        line = lines[i]
        match = _FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker[0] * len(marker)
            elif line.strip().startswith(fence):
                fence = None
            out.append(line)
            i += 1
            continue
        if fence is not None:
            out.append(line)
            i += 1
            continue

        admonition = _MKDOCS_ADMONITION.match(line)
        if admonition:
            body: list[str] = []
            i += 1
            while i < len(lines) and (lines[i].startswith("    ") or lines[i].startswith("\t") or not lines[i].strip()):
                if not lines[i].strip() and (i + 1 >= len(lines) or not lines[i + 1].startswith(("    ", "\t"))):
                    break
                body.append(lines[i][4:] if lines[i].startswith("    ") else lines[i].lstrip("\t"))
                i += 1
            out += _callout(admonition.group(2), admonition.group(3) or "", body)
            continue

        container = _DOCUSAURUS_OPEN.match(line)
        if container and context.layout.tool in ("docusaurus", "markdown", "obsidian"):
            kind = container.group(1).lower()
            title = (container.group(2) or container.group(3) or "").strip()
            body = []
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                body.append(lines[i])
                i += 1
            i += 1
            mapped = {"caution": "warning", "danger": "danger", "info": "note"}.get(kind, kind)
            out += _callout(mapped, title, body)
            continue

        hint = _GITBOOK_HINT.match(line.strip())
        if hint:
            body = []
            i += 1
            while i < len(lines) and not _GITBOOK_END.match(lines[i].strip()):
                body.append(lines[i])
                i += 1
            i += 1
            out.append(f"> [!{_GITBOOK_KINDS.get(hint.group(1).lower(), 'NOTE')}]")
            out += [f"> {b}".rstrip() for b in body]
            continue

        obsidian = _OBSIDIAN_CALLOUT.match(line)
        if obsidian:
            # GitHub's own five kinds are already what DocuWaves renders --
            # only Obsidian's extra ones (info, danger, ...) are mapped.
            written = obsidian.group(1).upper()
            kind = written if written in _GITHUB_KINDS else _KINDS.get(obsidian.group(1).lower(), "NOTE")
            out.append(f"> [!{kind}]")
            if obsidian.group(2).strip():
                out.append(f"> **{obsidian.group(2).strip()}**")
            i += 1
            continue

        if context.layout.tool == "docusaurus" or context.source.lower().endswith(".mdx"):
            if _MDX_LINE.match(line):
                mdx_dropped = True
                i += 1
                continue

        line = _GITBOOK_EMBED.sub(lambda m: f"<{m.group(1)}>", line)
        if _GITBOOK_TAG.search(line):
            context.warn.append(f"GitBook tag removed: {_GITBOOK_TAG.search(line).group(0)[:60]}")
            line = _GITBOOK_TAG.sub("", line)
        out.append(line)
        i += 1

    if mdx_dropped:
        context.warn.append("MDX import/export lines removed; components on the page may need rewriting")
    return out


_LINK = re.compile(r"(!?)\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\s*(<[^>]+>|[^)\s]+)(\s+\"[^\"]*\")?\s*\)")
_REF_DEF = re.compile(r"^(\s{0,3}\[[^\]]+\]:\s*)(\S+)(.*)$")
_HTML_SRC = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.IGNORECASE)
_WIKI = re.compile(r"(!?)\[\[([^\]|#]*)(#[^\]|]*)?(?:\|([^\]]*))?\]\]")
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#)", re.IGNORECASE)


def _resolve(target: str, context: _Context) -> str | None:
    """A link target as an archive path, or None."""
    if target.startswith("/"):
        candidates = [target.lstrip("/")]
        if context.layout.static:
            candidates.insert(0, posixpath.join(context.layout.static, target.lstrip("/")))
        if context.layout.root:
            candidates.append(posixpath.join(context.layout.root, target.lstrip("/")))
    else:
        candidates = [posixpath.normpath(posixpath.join(posixpath.dirname(context.source), target))]
    for candidate in candidates:
        if candidate.startswith("../"):
            continue
        options = [candidate]
        if not posixpath.splitext(candidate)[1]:
            options += [candidate + ext for ext in MARKDOWN_EXTENSIONS]
            options += [posixpath.join(candidate, f"{name}{ext}") for name in _INDEX_NAMES for ext in MARKDOWN_EXTENSIONS]
        elif candidate.lower().endswith(".html"):
            options.append(candidate[:-5] + ".md")
        for option in options:
            if option in context.files:
                return option
            if option.rstrip("/") + "/index.md" in context.files:
                return option.rstrip("/") + "/index.md"
    return None


def _rewrite_target(raw: str, context: _Context, is_image: bool) -> str:
    target = raw[1:-1] if raw.startswith("<") and raw.endswith(">") else raw
    if _EXTERNAL.match(target):
        return raw
    path_part, _, fragment = target.partition("#")
    path_part = unquote(path_part.split("?")[0])
    if not path_part:
        return raw
    found = _resolve(path_part, context)
    if found and found in context.page_by_path:
        anchor = f"#{fragment}" if fragment else ""
        return f"/p/{context.project_slug}/pages/{context.page_by_path[found].slug}{anchor}"
    if found and found in context.files and not found.lower().endswith(MARKDOWN_EXTENSIONS):
        reason = content_assets.rejection_reason(found.split("/")[-1], context.files[found])
        if reason is None:
            return f"../assets/{context.asset_target(found)}"
        context.rejected.add(found)
        context.warn.append(f"file not imported: {path_part} ({reason})")
        return raw
    context.warn.append(f"{'image' if is_image else 'link'} points nowhere in the archive: {path_part}")
    return raw


def _wiki(match: re.Match, context: _Context) -> str:
    embed, name, heading, alias = match.group(1), match.group(2).strip(), match.group(3) or "", match.group(4)
    if embed:
        found = next((p for p in context.files if p.split("/")[-1] == name), None)
        if found:
            return f"![{alias or ''}]({_rewrite_target(found_relative(found, context), context, True)})"
        context.warn.append(f"embed points nowhere in the archive: {name}")
        return match.group(0)
    path = context.stems.get(name.lower()) or context.stems.get(posixpath.splitext(name)[0].lower())
    label = alias or name or heading.lstrip("#")
    if path is None and not name and heading:
        return f"[{label}]({link_heading(heading)})"
    if path is None:
        context.warn.append(f"wiki link to a page that is not in the archive: {name}")
        return label
    anchor = link_heading(heading) if heading else ""
    return f"[{label}](/p/{context.project_slug}/pages/{context.page_by_path[path].slug}{anchor})"


def found_relative(path: str, context: _Context) -> str:
    return posixpath.relpath(path, posixpath.dirname(context.source) or ".")


def link_heading(heading: str) -> str:
    text = heading.lstrip("#").strip().lower()
    return "#" + re.sub(r"[\s-]+", "-", re.sub(r"[^\w\s-]", "", text).replace("_", "")).strip("-")


def convert(markdown: str, context: _Context) -> str:
    out: list[str] = []
    fence = None
    for line in _blocks(markdown, context):
        match = _FENCE.match(line)
        if match:
            if fence is None:
                fence = match.group(1)[0] * len(match.group(1))
            elif line.strip().startswith(fence):
                fence = None
            out.append(line)
            continue
        if fence is not None:
            out.append(line)
            continue
        line = _WIKI.sub(lambda m: _wiki(m, context), line)
        line = _LINK.sub(
            lambda m: f"{m.group(1)}[{m.group(2)}]({_rewrite_target(m.group(3), context, bool(m.group(1)))}{m.group(4) or ''})",
            line,
        )
        line = _HTML_SRC.sub(lambda m: m.group(1) + _rewrite_target(m.group(2), context, True) + m.group(3), line)
        ref = _REF_DEF.match(line)
        if ref:
            line = ref.group(1) + _rewrite_target(ref.group(2), context, False) + ref.group(3)
        out.append(line)
    return "\n".join(out).strip("\n") + "\n"


# ---- Writing it ----


def apply(data: bytes, author: str, *, archive_name: str = "", project_slug: str = "", new_project_name: str = "") -> dict:
    """Runs plan() and writes the result: drafts only, one commit."""
    result = plan(data, project_slug=project_slug, new_project_name=new_project_name)
    # The assets' bytes. Every converter keeps attachments at their archive
    # paths, so the plain read is where they are.
    files, _, _ = read_archive(data)
    if not result.new_project:
        content_versions.ensure_writable(result.project_slug, result.version)
    paths: list[str] = []
    if result.new_project:
        order = max((p["sort_order"] for p in projects_store.list_projects()), default=-1) + 1
        paths += content_files.write_project(result.project_slug, result.project_name, "", "", "", "", order)
    for category in result.categories:
        if not category.pages:
            continue
        paths += content_files.write_category(
            result.project_slug, category.slug, category.name, "", "", category.order, version=result.version
        )
        for page in category.pages:
            paths += content_files.write_page(
                result.project_slug, category.slug, page.slug, page.title, page.body, page.order, False,
                "", result.version, review={"review_changed_by": author},
            )
    asset_dir = content_files.project_content_dir(result.project_slug, result.version) / "assets"
    for source, target in result.assets.items():
        destination = asset_dir / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(files[source])
            paths.append(content_files._rel(destination))
    pages = sum(len(c.pages) for c in result.categories)
    label = f" from {archive_name}" if archive_name else ""
    git_content_repo.commit_and_push(
        paths,
        f"Import {pages} pages{label} ({result.tool})\n\nAll imported as drafts. Reverting this commit undoes the import.",
        author,
    )
    content_sync.full_sync()
    return result.summary()
