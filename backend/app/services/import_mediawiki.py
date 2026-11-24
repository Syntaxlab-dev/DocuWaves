"""MediaWiki XML dumps (Special:Export, or `dumpBackup.php --current`),
turned into the Markdown the importer already takes in
(services/importer.py).

The dump is one XML file with every page's wikitext. It can be uploaded as
it is, or in a ZIP together with the wiki's images (any folder; they are
found by file name, the way `[[File:Diagram.png]]` names them).

THE TREE. A wiki is flat, its order comes from categories: every page goes
into the category of its FIRST `[[Category:...]]`, pages without one into
"General". Main-namespace pages only; talk pages, templates, user pages and
the rest are left out, and redirects too (they are not content).

WIKITEXT. Converted: headings, bold and italics, lists (also nested and
numbered), definition lists, internal links (`[[Page|text]]`, with
section), external links, images (`[[File:...|caption]]`), `<pre>`,
`<syntaxhighlight>` / `<source>` and lines starting with a space as code
blocks, `<code>` and simple HTML formatting, tables (`{| ... |}`) as
Markdown tables, `<ref>` as footnotes, horizontal rules. Templates
(`{{...}}`) and parser functions cannot be evaluated outside the wiki: they
are removed, and the preview lists them per page.

The XML is parsed by Python's expat (which refuses entity expansion bombs);
a dump never has a DOCTYPE, so one is refused outright -- nothing in the
file is fetched or resolved.
"""
import json
import posixpath
import re
import xml.etree.ElementTree as ET

from app.services import content_files

MAIN_NAMESPACE = "0"


def is_dump(data: bytes) -> bool:
    head = data[:2000].lstrip(b"\xef\xbb\xbf \t\r\n")
    return head.startswith(b"<?xml") and b"<mediawiki" in head or head.startswith(b"<mediawiki")


def looks_like(files: dict[str, bytes]) -> bool:
    return any(p.lower().endswith(".xml") and is_dump(b) for p, b in files.items())


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _pages(data: bytes) -> list[tuple[str, str]]:
    """(title, wikitext of the newest revision) of every content page."""
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ValueError("The XML file declares a DOCTYPE or entities; a MediaWiki export never does.")
    root = ET.fromstring(data)
    pages = []
    for page in root:
        if _local(page.tag) != "page":
            continue
        fields = {_local(child.tag): child for child in page}
        namespace = (fields.get("ns").text or "").strip() if fields.get("ns") is not None else MAIN_NAMESPACE
        if namespace != MAIN_NAMESPACE or "redirect" in fields:
            continue
        revisions = [child for child in page if _local(child.tag) == "revision"]
        if not revisions:
            continue
        text = next((c for c in revisions[-1] if _local(c.tag) == "text"), None)
        wikitext = (text.text or "") if text is not None else ""
        if re.match(r"^\s*#(REDIRECT|WEITERLEITUNG)\b", wikitext, re.IGNORECASE):
            continue
        title = (fields["title"].text or "").strip() if "title" in fields else ""
        if title:
            pages.append((title, wikitext.replace("\r\n", "\n")))
    return pages


def _canonical(name: str) -> str:
    """MediaWiki's form of a title: spaces as underscores' twin, the first
    letter upper case."""
    name = re.sub(r"[\s_]+", " ", name).strip()
    return name[:1].upper() + name[1:]


# ---- Wikitext ----

_NAMESPACE_FILE = ("file", "image", "datei", "bild")
_NAMESPACE_CATEGORY = ("category", "kategorie")
_NAMESPACE_MEDIA = ("media",)
_FILE_OPTIONS = re.compile(
    r"^(thumb|thumbnail|frame|frameless|border|left|right|center|centre|none|upright(=.*)?|\d*x?\d+px|"
    r"mini|miniatur|hochkant(=.*)?|links|rechts|zentriert|ohne|rahmen|rahmenlos|link=.*|alt=.*|page=.*|class=.*|lang=.*)$",
    re.IGNORECASE,
)


class _Page:
    def __init__(self, convert_link, convert_file, notes: list[str]):
        self.link = convert_link
        self.file = convert_file
        self.notes = notes
        self.footnotes: list[str] = []
        self.templates: list[str] = []


def _strip_templates(text: str, page: _Page) -> str:
    """Every `{{...}}`, nested ones included, removed and remembered;
    `{{{parameters}}}` too."""
    out = []
    depth = 0
    i = 0
    start = 0
    while i < len(text):
        if text.startswith("{{", i):
            if depth == 0:
                start = i
            depth += 1
            i += 2
            continue
        if text.startswith("}}", i) and depth:
            depth -= 1
            i += 2
            if depth == 0:
                name = re.split(r"[|:}]", text[start + 2:i - 2], maxsplit=1)[0].strip()
                if name and not name.startswith("{"):
                    page.templates.append(name)
            continue
        if depth == 0:
            out.append(text[i])
        i += 1
    return "".join(out)


def _split_pipes(inner: str) -> list[str]:
    """`a|b [[c|d]]|e` -> ["a", "b [[c|d]]", "e"]: a pipe inside a nested
    link belongs to that link."""
    parts, depth, current = [], 0, []
    i = 0
    while i < len(inner):
        if inner.startswith("[[", i):
            depth += 1
            current.append("[[")
            i += 2
            continue
        if inner.startswith("]]", i) and depth:
            depth -= 1
            current.append("]]")
            i += 2
            continue
        if inner[i] == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(inner[i])
        i += 1
    parts.append("".join(current))
    return parts


def _internal_links(text: str, page: _Page) -> str:
    out = []
    i = 0
    while True:
        start = text.find("[[", i)
        if start < 0:
            out.append(text[i:])
            break
        # The matching `]]`, counting nested `[[...]]` (a caption with a link).
        depth, j = 0, start
        while j < len(text):
            if text.startswith("[[", j):
                depth += 1
                j += 2
            elif text.startswith("]]", j):
                depth -= 1
                j += 2
                if depth == 0:
                    break
            else:
                j += 1
        if depth:
            out.append(text[i:])
            break
        out.append(text[i:start])
        inner = text[start + 2:j - 2]
        trail = re.match(r"[a-zäöüß]*", text[j:]).group(0)
        parts = _split_pipes(inner)
        target = parts[0].strip()
        prefix, _, rest = target.partition(":")
        namespace = prefix.strip().lower() if rest else ""
        if namespace in _NAMESPACE_CATEGORY and not target.startswith(":"):
            out.append("")
        elif namespace in _NAMESPACE_FILE:
            options = [p.strip() for p in parts[1:]]
            caption = next((o for o in reversed(options) if o and not _FILE_OPTIONS.match(o)), "")
            caption = _internal_links(caption, page) if caption else ""
            out.append(page.file(rest.strip(), re.sub(r"[\[\]]", "", caption), embed=True))
        elif namespace in _NAMESPACE_MEDIA:
            label = parts[1].strip() if len(parts) > 1 else rest.strip()
            out.append(page.file(rest.strip(), label, embed=False))
        elif re.match(r"^:?[a-z]{2,3}(-[a-z]+)?$", namespace or "-") and rest:
            out.append("")  # a language link to the same page in another wiki
        else:
            label = (parts[1] if len(parts) > 1 else target.lstrip(":")).strip() or target
            out.append(page.link(target.lstrip(":"), label + trail))
            j += len(trail)
        i = j
    return "".join(out)


_EXTERNAL = re.compile(r"\[((?:https?|ftp|mailto):[^\s\]]+)(?:\s+([^\]]*))?\]")
_REF = re.compile(r"<ref(?:\s[^>/]*)?>(.*?)</ref>|<ref(?:\s[^>]*)?/>", re.DOTALL | re.IGNORECASE)
_SIMPLE_TAGS = [
    (re.compile(r"</?(?:b|strong)>", re.I), "**"),
    (re.compile(r"</?(?:i|em)>", re.I), "*"),
    (re.compile(r"</?(?:s|del|strike)>", re.I), "~~"),
]


def _inline(text: str, page: _Page) -> str:
    text = re.sub(
        r"<code>(.*?)</code>|<tt>(.*?)</tt>",
        lambda m: "`" + (m.group(1) or m.group(2) or "").replace("`", "'") + "`",
        text, flags=re.I | re.S,
    )
    text = re.sub(r"'''''(.+?)'''''", r"***\1***", text)
    text = re.sub(r"'''(.+?)'''", r"**\1**", text)
    text = re.sub(r"''(.+?)''", r"*\1*", text)

    def ref(match: re.Match) -> str:
        content = (match.group(1) or "").strip()
        if not content:
            return ""
        page.footnotes.append(content)
        return f"[^{len(page.footnotes)}]"

    text = _REF.sub(ref, text)
    text = _internal_links(text, page)
    text = _EXTERNAL.sub(lambda m: f"[{m.group(2).strip()}]({m.group(1)})" if m.group(2) and m.group(2).strip() else f"<{m.group(1)}>", text)
    for pattern, replacement in _SIMPLE_TAGS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"</?(?:span|div|font|center|small|big|u|sup|sub|abbr|references|poem|blockquote)(?:\s[^>]*)?/?>", "", text, flags=re.I)
    return text


def _cell_text(text: str, page: _Page) -> str:
    return _inline(text.strip(), page).replace("\n", " ").replace("|", "\\|").strip()


def _cell_content(cell: str) -> str:
    """`style="x" | content` -> content (a single pipe outside a link)."""
    parts = _split_pipes(cell)
    return parts[-1] if len(parts) > 1 and "=" in parts[0] else cell


def _table(lines: list[str], page: _Page) -> list[str]:
    rows: list[list[str]] = []
    header_row: list[bool] = []
    caption = ""
    current: list[str] | None = None
    for raw in lines[1:]:
        line = raw.strip()
        if line.startswith("|}"):
            break
        if line.startswith("|+"):
            caption = _cell_text(_cell_content(line[2:]), page)
        elif line.startswith("|-"):
            current = None
        elif line.startswith(("!", "|")):
            if current is None:
                current = []
                rows.append(current)
                header_row.append(line.startswith("!"))
            separator = "!!" if line.startswith("!") else "||"
            cells = line[1:].split(separator) if separator in line else [line[1:]]
            if line.startswith("!"):
                cells = [c for part in cells for c in part.split("||")]
            current.extend(_cell_text(_cell_content(c), page) for c in cells)
        elif current:
            current[-1] = (current[-1] + " " + _cell_text(line, page)).strip()
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    if header_row[0]:
        head, body = rows[0], rows[1:]
    else:
        head, body = [""] * width, rows
    out = []
    if caption:
        out += [f"**{caption}**", ""]
    out.append("| " + " | ".join(head) + " |")
    out.append("|" + "|".join(" --- " for _ in head) + "|")
    out += ["| " + " | ".join(r) + " |" for r in body]
    return out


_HEADING = re.compile(r"^(={1,6})\s*(.+?)\s*\1\s*$")
_LIST = re.compile(r"^([*#:;]+)\s*(.*)$")


def wikitext_to_markdown(wikitext: str, page: _Page) -> str:
    text = re.sub(r"<!--.*?-->", "", wikitext, flags=re.S)
    # Verbatim parts first: code and <nowiki> keep what is written in them.
    kept: list[str] = []

    def keep(value: str) -> str:
        kept.append(value)
        return f"\x00{len(kept) - 1}\x00"

    def code_block(match: re.Match) -> str:
        language, content = match.group(2) or "", match.group(3)
        content = content.strip("\n")
        fence = "````" if "```" in content else "```"
        return "\n" + keep(f"{fence}{language}\n{content}\n{fence}") + "\n"

    text = re.sub(
        r"<(pre|syntaxhighlight|source)(?:\s[^>]*?(?:lang|language)=\"?([\w+#-]+)\"?[^>]*|\s[^>]*)?>(.*?)</\1>",
        code_block, text, flags=re.S | re.I,
    )
    text = re.sub(
        r"<nowiki>(.*?)</nowiki>", lambda m: keep(re.sub(r"([\[\]*_`])", r"\\\1", m.group(1))), text, flags=re.S | re.I
    )
    text = re.sub(r"<nowiki\s*/>", "", text, flags=re.I)
    text = _strip_templates(text, page)
    text = re.sub(r"__[A-Z]+__", "", text)

    lines = text.split("\n")
    out: list[str] = []
    previous = "text"
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("{|") or line.startswith(" ") or _HEADING.match(line):
            previous = "text"
        if line.lstrip().startswith("{|"):
            block = [line]
            depth = 1
            i += 1
            while i < len(lines) and depth:
                stripped = lines[i].strip()
                if stripped.startswith("{|"):
                    depth += 1
                elif stripped.startswith("|}"):
                    depth -= 1
                block.append(lines[i])
                i += 1
            if any(b.strip().startswith("{|") for b in block[1:]):
                page.notes.append("a table inside a table was flattened")
            out += ["", *_table(block, page), ""]
            continue
        if line.startswith(" ") and line.strip() and not line.strip().startswith("\x00"):
            block = []
            while i < len(lines) and lines[i].startswith(" ") and lines[i].strip():
                block.append(lines[i][1:])
                i += 1
            out += ["", "```", *block, "```", ""]
            continue
        heading = _HEADING.match(line)
        if heading:
            out += ["", "#" * len(heading.group(1)) + " " + _inline(heading.group(2), page), ""]
            i += 1
            continue
        if re.match(r"^-{4,}\s*$", line):
            out += ["", "---", ""]
            i += 1
            continue
        listed = _LIST.match(line)
        kind = {"*": "list", "#": "numbered", ";": "terms", ":": "indent"}[listed.group(1)[0]] if listed else "text"
        if kind != previous:
            # Markdown runs a list on into the next line unless a blank
            # line ends it; MediaWiki ends it at the first other line.
            out.append("")
        previous = kind
        if listed:
            markers, content = listed.group(1), listed.group(2)
            last = markers[-1]
            if last == ";":
                term, _, definition = content.partition(" : ") if " : " in content else content.partition(":")
                line = f"**{_inline(term.strip(), page)}**"
                out += [line + (f": {_inline(definition.strip(), page)}" if definition.strip() else ""), ""]
            elif kind == "indent":
                out.append(">" * len(markers) + f" {_inline(content, page)}")
            else:
                # `*:` / `#:` continue the item above them, on its level.
                indent = "".join("   " if m == "#" else "  " for m in markers[:-1])
                marker = {"#": "1. ", "*": "- "}.get(last, "")
                out.append(f"{indent}{marker}{_inline(content, page)}")
            i += 1
            continue
        out.append(_inline(line, page))
        i += 1

    body = "\n".join(out)
    body = re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
    if page.footnotes:
        body += "\n" + "\n".join(f"[^{n}]: {_inline(t, page)}" for n, t in enumerate(page.footnotes, 1)) + "\n"
    return body


# ---- The export as Markdown files ----


def _anchor(section: str) -> str:
    """The section as DocuWaves writes heading anchors (importer.link_heading)."""
    text = section.replace("_", " ").strip().lower()
    return "#" + re.sub(r"[\s-]+", "-", re.sub(r"[^\w\s-]", "", text).replace("_", "")).strip("-")


def convert(files: dict[str, bytes]) -> tuple[dict[str, bytes], dict[str, int], list[str]]:
    """(the wiki as Markdown + its images, page order, notes per page)."""
    dumps = sorted(p for p, b in files.items() if p.lower().endswith(".xml") and is_dump(b))
    notes: list[str] = []
    pages: list[tuple[str, str]] = []
    for dump in dumps:
        try:
            pages += _pages(files[dump])
        except (ET.ParseError, ValueError) as exc:
            notes.append(f"{dump}: not readable as a MediaWiki export ({exc})")

    # Images by MediaWiki's name for them.
    images = {}
    for path in files:
        if not path.lower().endswith((".xml", ".md")):
            images.setdefault(_canonical(path.split("/")[-1]), path)

    # Category per page: its first [[Category:...]].
    category_of: dict[str, str] = {}
    labels: dict[str, str] = {}
    category_pattern = re.compile(r"\[\[\s*(?:" + "|".join(_NAMESPACE_CATEGORY) + r")\s*:\s*([^\]|]+)", re.IGNORECASE)
    for title, wikitext in pages:
        found = category_pattern.search(re.sub(r"<!--.*?-->", "", wikitext, flags=re.S))
        if found:
            name = found.group(1).strip().replace("_", " ")
            directory = content_files.make_slug(name)
            labels.setdefault(directory, name)
            category_of[title] = directory
        else:
            category_of[title] = ""

    targets: dict[str, str] = {}
    names_in_dir: dict[str, set[str]] = {}
    order: dict[str, int] = {}
    for position, (title, _) in enumerate(sorted(pages, key=lambda p: p[0].lower())):
        directory = category_of[title]
        taken = names_in_dir.setdefault(directory, set())
        stem = content_files.make_slug(title) or "page"
        candidate, n = stem, 2
        while candidate in taken:
            candidate = f"{stem}-{n}"
            n += 1
        taken.add(candidate)
        target = posixpath.join(directory, f"{candidate}.md")
        targets[_canonical(title)] = target
        order[target] = position

    result: dict[str, bytes] = {p: b for p, b in files.items() if p not in dumps}
    for title, wikitext in pages:
        target = targets[_canonical(title)]
        own_dir = posixpath.dirname(target) or "."
        page_notes: list[str] = []
        missing_pages: set[str] = set()
        missing_files: set[str] = set()

        def link(name: str, label: str, _own_dir=own_dir, _missing=missing_pages) -> str:
            name, _, section = name.partition("#")
            anchor = _anchor(section) if section.strip() else ""
            if not name.strip():
                return f"[{label}]({anchor})" if anchor else label
            found = targets.get(_canonical(name))
            if found is None:
                _missing.add(name.strip())
                return label
            return f"[{label}]({posixpath.relpath(found, _own_dir)}{anchor})"

        def file(name: str, label: str, embed: bool, _own_dir=own_dir, _missing=missing_files) -> str:
            found = images.get(_canonical(name))
            if found is None:
                _missing.add(name)
                return f"*{label}*" if label else ""
            relative = posixpath.relpath(found, _own_dir).replace(" ", "%20")
            return f"![{label}]({relative})" if embed else f"[{label or name}]({relative})"

        page = _Page(link, file, page_notes)
        body = wikitext_to_markdown(wikitext, page)
        if page.templates:
            names = ", ".join(sorted(dict.fromkeys(page.templates))[:8])
            page_notes.append(f"templates removed: {names}")
        if missing_pages:
            page_notes.append(f"links to pages not in the export kept as text: {', '.join(sorted(missing_pages)[:8])}")
        if missing_files:
            page_notes.append(f"files not in the archive: {', '.join(sorted(missing_files)[:8])}")
        front = "---\ntitle: '" + title.replace("'", "''") + "'\n---\n\n"
        result[target] = (front + body).encode("utf-8")
        notes += [f"{target}: {n}" for n in dict.fromkeys(page_notes)]

    for position, directory in enumerate(sorted(labels, key=lambda d: labels[d].lower())):
        result[f"{directory}/_category_.json"] = (
            '{"label": ' + json.dumps(labels[directory], ensure_ascii=False) + f', "position": {position + 1}' + "}"
        ).encode("utf-8")
    return result, order, notes
