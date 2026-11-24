"""Wiki.js 2 content, turned into the Markdown the importer already takes in
(services/importer.py).

Wiki.js keeps every page as a file -- in a Git repository when the "Git"
storage target is on, in a folder with "Local File System" -- at its path:
`guide/install.md`, with an HTML comment in front that holds its title and
the rest of its properties:

    <!--
    title: Installation
    description: How to install
    published: true
    tags: setup
    editor: markdown
    -->

That comment becomes front matter. Pages written in the visual editor are
stored as `.html` with the same comment and are converted from HTML.
Folders become categories by the importer's usual rule. Links in Wiki.js
are absolute (`/guide/install`), and the importer already resolves those
against the archive; with the locale folders of a multilingual wiki
(`en/guide/install.md`), the locale is taken off the paths and the links.
A wiki in several languages imports its biggest language; the others are
named in the preview.

Callouts are Wiki.js blockquotes with a class line under them
(`{.is-info}`, `{.is-success}`, `{.is-warning}`, `{.is-danger}`); they
become DocuWaves callouts.
"""
import posixpath
import re

from app.services import import_confluence

_HEAD = re.compile(r"^﻿?\s*<!--\s*\n(.*?)\n\s*-->\s*\n?", re.DOTALL)
_PROPERTY = re.compile(r"^\s*([A-Za-z]+)\s*:\s*(.*?)\s*$")
_PAGE = (".md", ".html")
_LOCALE = re.compile(r"^[a-z]{2,3}(?:-[a-z]{2,4})?$", re.IGNORECASE)
_CLASS_LINE = re.compile(r"^\s*>?\s*\{\.is-(info|success|warning|danger)\}\s*$")
_KINDS = {"info": "NOTE", "success": "TIP", "warning": "WARNING", "danger": "CAUTION"}
_LINK_TARGET = re.compile(r"(\]\(\s*<?|\bhref=\"|\bsrc=\")/([^)\s\">]*)")


def _text(raw: bytes) -> str:
    return raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n")


def _head(raw: bytes) -> tuple[dict[str, str], str] | None:
    """(properties, the rest) for a Wiki.js page, None for anything else."""
    text = _text(raw)
    match = _HEAD.match(text)
    if not match:
        return None
    properties = {}
    for line in match.group(1).split("\n"):
        found = _PROPERTY.match(line)
        if found:
            properties[found.group(1).lower()] = found.group(2)
    if "title" not in properties:
        return None
    return properties, text[match.end():]


def looks_like(files: dict[str, bytes]) -> bool:
    pages = [p for p in files if p.lower().endswith(_PAGE)]
    hits = sum(1 for p in pages if _head(files[p]) is not None)
    return hits > 0 and hits * 2 >= len(pages)


def _callouts(body: str) -> str:
    """A blockquote followed by `{.is-warning}` -> a callout of that kind."""
    lines = body.split("\n")
    out: list[str] = []
    for line in lines:
        match = _CLASS_LINE.match(line)
        if match and out and out[-1].startswith(">"):
            start = len(out)
            while start > 0 and out[start - 1].startswith(">"):
                start -= 1
            out.insert(start, f"> [!{_KINDS[match.group(1)]}]")
            continue
        out.append(line)
    return "\n".join(out)


def convert(files: dict[str, bytes]) -> tuple[dict[str, bytes], dict[str, int], list[str]]:
    """(the wiki as Markdown + its files, page order, notes per page)."""
    notes: list[str] = []
    heads = {p: _head(files[p]) for p in files if p.lower().endswith(_PAGE)}
    pages = {p: h for p, h in heads.items() if h is not None}

    # Locale folders: only when EVERY page sits in one.
    tops = {p.split("/", 1)[0] for p in pages if "/" in p}
    locale = ""
    if pages and all("/" in p for p in pages) and tops and all(_LOCALE.match(t) for t in tops):
        counts = {t: sum(1 for p in pages if p.startswith(f"{t}/")) for t in tops}
        locale = max(sorted(counts), key=lambda t: counts[t])
        for other in sorted(t for t in tops if t != locale):
            notes.append(f"{other}/: Wiki.js language '{other}' not imported ({counts[other]} pages); only '{locale}'")

    def moved(path: str) -> str | None:
        if not locale:
            return path
        return path[len(locale) + 1:] if path.startswith(f"{locale}/") else None

    def strip_locale(text: str) -> str:
        if not locale:
            return text
        return _LINK_TARGET.sub(
            lambda m: m.group(1) + "/" + (m.group(2)[len(locale) + 1:] if m.group(2).startswith(f"{locale}/") else m.group(2)),
            text,
        )

    result: dict[str, bytes] = {}
    for path, data in files.items():
        if path in heads and heads[path] is None and path.lower().endswith(".html"):
            continue  # an HTML file that is not a page
        if path in pages:
            continue
        target = moved(path)
        if target:
            result[target] = data

    order: dict[str, int] = {}
    for path in sorted(pages):
        target = moved(path)
        if target is None:
            continue
        properties, body = pages[path]
        if path.lower().endswith(".html"):
            body = import_confluence.html_to_markdown(strip_locale(body))
            target = target[:-5] + ".md"
        else:
            body = _callouts(strip_locale(body))
        front = ["---", "title: " + import_confluence.yaml_string(properties["title"])]
        if properties.get("published", "").lower() == "false":
            front.append("published: false")
        front += ["---", "", ""]
        if target in result:
            notes.append(f"{target}: two pages with the same address; the second one was not imported")
            continue
        result[target] = ("\n".join(front) + body.lstrip("\n")).encode("utf-8")
        # home.md is Wiki.js's start page: first in its folder.
        stem = posixpath.splitext(target.split("/")[-1])[0].lower()
        order[target] = -1 if stem == "home" else len(order)
    return result, order, notes
