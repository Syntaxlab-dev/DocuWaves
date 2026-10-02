"""Notion exports ("Markdown & CSV"), turned into the Markdown the importer
already takes in (services/importer.py) -- the same idea as the Confluence
converter next to it.

What Notion writes: every page as `Title <32 hex id>.md`, its sub-pages and
images in a folder of the same name, every database as `Name <id>.csv`
(often also `Name <id>_all.csv`) with one Markdown page per row in the
database's folder. Links are URL-encoded paths to those files.

What this does:
- removes the ids from every name, and the links follow;
- the page tree becomes categories by the same rule as Confluence: a single
  top page is the home page; the home page and top-level pages without
  sub-pages go into "General", every top-level page WITH sub-pages becomes
  a category -- the page first, then everything below it;
- a database becomes a page of its own with the table from the CSV (the
  first column linking to the row's page when there is one), and its row
  pages become its sub-pages;
- `<aside>` callouts become DocuWaves callouts, by their emoji (💡 tip,
  ⚠️ warning, ❗/🚨 caution, anything else a note).
"""
import csv
import io
import posixpath
import re
from dataclasses import dataclass, field
from urllib.parse import quote, unquote

from app.services import content_files

_ID = re.compile(r"\s+[0-9a-f]{32}(?=$|\.|_all\.)", re.IGNORECASE)
_MAX_TABLE_ROWS = 500


def looks_like(files: dict[str, bytes]) -> bool:
    hits = sum(1 for p in files if any(_ID.search(part) for part in p.split("/")))
    return hits > 0 and hits * 2 >= sum(1 for p in files if p.lower().endswith((".md", ".csv")))


def _clean(name: str) -> str:
    return _ID.sub("", name).strip()


@dataclass
class _Page:
    path: str  # original archive path (.md or .csv)
    title: str
    children: list = field(default_factory=list)


def _text(raw: bytes) -> str:
    return raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n")


def _tree(files: dict[str, bytes]) -> list[_Page]:
    """Pages and databases, nested by Notion's folder-next-to-file rule."""
    sources = sorted(
        p for p in files
        if p.lower().endswith(".md") or (p.lower().endswith(".csv") and not p.lower().endswith("_all.csv"))
    )
    # A database exported only as _all.csv still counts.
    for p in files:
        if p.lower().endswith("_all.csv") and p[:-8] + ".csv" not in files:
            sources.append(p)
    nodes = {p: _Page(p, _clean(posixpath.splitext(p.split("/")[-1])[0]).removesuffix("_all")) for p in sources}
    by_folder = {posixpath.splitext(p)[0].removesuffix("_all"): node for p, node in nodes.items()}
    roots: list[_Page] = []
    for p in sorted(sources):
        parent = by_folder.get(posixpath.dirname(p))
        (parent.children if parent else roots).append(nodes[p])
    return roots


_ASIDE = re.compile(r"<aside>\s*\n?(.*?)\n?\s*</aside>", re.DOTALL)
_EMOJI_KINDS = (("💡", "TIP"), ("⚠️", "WARNING"), ("⚠", "WARNING"), ("❗", "CAUTION"), ("🚨", "CAUTION"), ("‼️", "CAUTION"))
_LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\))")


def _aside(match: re.Match) -> str:
    body = match.group(1).strip()
    kind = "NOTE"
    for emoji, mapped in _EMOJI_KINDS:
        if body.startswith(emoji):
            kind, body = mapped, body[len(emoji):].lstrip(" \ufe0f")
            break
    else:
        # Whatever other emoji the callout had is decoration, not meaning.
        body = re.sub(r"^[^\w\s\[*_`#>(-]{1,3}\s*", "", body)
    return "\n".join([f"> [!{kind}]"] + [f"> {line}".rstrip() for line in body.split("\n")]) + "\n"


def _table(raw: bytes, row_links: dict[str, str]) -> tuple[str, bool]:
    rows = list(csv.reader(io.StringIO(_text(raw))))
    if not rows:
        return "", False
    header, body = rows[0], rows[1:]
    truncated = len(body) > _MAX_TABLE_ROWS
    body = body[:_MAX_TABLE_ROWS]

    def cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ").strip()

    lines = ["| " + " | ".join(cell(h) for h in header) + " |", "|" + " --- |" * len(header)]
    for row in body:
        row = row + [""] * (len(header) - len(row))
        first = cell(row[0])
        if row[0].strip() in row_links:
            first = f"[{first}]({row_links[row[0].strip()]})"
        lines.append("| " + " | ".join([first] + [cell(v) for v in row[1:len(header)]]) + " |")
    return "\n".join(lines) + "\n", truncated


def convert(files: dict[str, bytes]) -> tuple[dict[str, bytes], dict[str, int], list[str]]:
    """(the archive as cleaned Markdown + its images, page order, notes)."""
    roots = _tree(files)
    home = roots[0] if len(roots) == 1 and roots[0].children else None
    tops = home.children if home else roots

    placement: list[tuple[_Page, str]] = []  # (page, directory)
    categories: list[tuple[str, str]] = []

    def flatten(page: _Page, directory: str) -> None:
        placement.append((page, directory))
        for child in page.children:
            flatten(child, directory)

    if home:
        placement.append((home, ""))
    used_dirs: set[str] = set()
    for page in tops:
        if page.children:
            directory, n = content_files.make_slug(page.title), 2
            while directory in used_dirs:
                directory = f"{content_files.make_slug(page.title)}-{n}"
                n += 1
            used_dirs.add(directory)
            categories.append((directory, page.title))
            flatten(page, directory)
        else:
            flatten(page, "")

    targets: dict[str, str] = {}
    order: dict[str, int] = {}
    taken: dict[str, set[str]] = {}
    for position, (page, directory) in enumerate(placement):
        stem = content_files.make_slug(page.title) or "page"
        names = taken.setdefault(directory, set())
        candidate, n = stem, 2
        while candidate in names:
            candidate = f"{stem}-{n}"
            n += 1
        names.add(candidate)
        targets[page.path] = posixpath.join(directory, f"{candidate}.md")
        order[targets[page.path]] = position

    def relink(source: str, target: str, text: str) -> str:
        """Links and images, from the original file's place to the new one's."""
        def fix(match: re.Match) -> str:
            link = match.group(2)
            if re.match(r"^[a-z][a-z0-9+.-]*:|^//|^#", link, re.IGNORECASE):
                return match.group(0)
            path, _, fragment = unquote(link).partition("#")
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
            if resolved.lower().endswith("_all.csv") and resolved[:-8] + ".csv" in targets:
                resolved = resolved[:-8] + ".csv"
            destination = targets.get(resolved, resolved)
            relative = posixpath.relpath(destination, posixpath.dirname(target) or ".")
            return f"{match.group(1)}{quote(relative)}{'#' + fragment if fragment else ''}{match.group(3)}"
        return _LINK.sub(fix, text)

    # Images and media lose their ids too: `assets/imported/Setup/diagram.png`
    # rather than a 32-character hex string in every path.
    result: dict[str, bytes] = {}
    for path, data in files.items():
        if path.lower().endswith((".md", ".csv")):
            continue
        clean = "/".join(_clean(part) or part for part in path.split("/"))
        candidate, n = clean, 2
        while candidate in result:
            stem, ext = posixpath.splitext(clean)
            candidate = f"{stem}-{n}{ext}"
            n += 1
        result[candidate] = data
        targets[path] = candidate
    notes: list[str] = []
    for page, _directory in placement:
        target = targets[page.path]
        if page.path.lower().endswith(".csv"):
            row_links = {
                child.title: quote(posixpath.relpath(targets[child.path], posixpath.dirname(target) or "."))
                for child in page.children if child.path in targets
            }
            table, truncated = _table(files[page.path], row_links)
            body = table
            if truncated:
                notes.append(f"{target}: only the first {_MAX_TABLE_ROWS} rows of the database were taken over")
        else:
            body = _ASIDE.sub(_aside, _text(files[page.path]))
            body = relink(page.path, target, body)
        # Notion starts every page with its title as a heading -- the real
        # title, where the file name is a sanitised copy. Then the heading is
        # the title (the importer takes it, and does not print it twice);
        # only a page without one gets its name as front matter.
        if body.lstrip().startswith("# "):
            front = ""
        else:
            front = "---\ntitle: '" + page.title.replace("'", "''") + "'\n---\n\n"
        result[target] = (front + body).encode("utf-8")
    for position, (directory, label) in enumerate(categories):
        import json

        result[f"{directory}/_category_.json"] = json.dumps(
            {"label": label, "position": position}, ensure_ascii=False
        ).encode("utf-8")
    return result, order, notes
