"""Confluence space exports (Space tools -> Export -> HTML), turned into the
Markdown the importer already knows how to take in (services/importer.py).

An HTML export is a folder with `index.html` (the space's page tree under
"Available Pages"), one HTML file per page, and `attachments/<page>/<id>.png`.
Each page is converted here into a Markdown file -- with front matter for
its title -- and its links and images point at the other converted files
and at the attachments. Everything after that (slugs, link rewriting, image
copying, drafts, one commit) is the importer's ordinary path, so a
Confluence import obeys exactly the same rules as any other.

THE TREE. Confluence nests pages without limit; DocuWaves has one level of
categories. So: the space's home page and every top-level page WITHOUT
children go into "General"; every top-level page WITH children becomes a
category of its own -- the page first, then all of its descendants in the
order Confluence shows them.

MACROS, as the export renders them:
- info / note / warning / tip panels -> callouts (Confluence's "note" is
  its yellow one and becomes a warning, "warning" its red one -> caution);
- code blocks -> fenced code with the language from the `brush`;
- expand -> a callout with the expand's title;
- status lozenges -> bold text; emoticons -> their text; user mentions ->
  the name; the table of contents, the attachments list, labels, likes and
  comments are dropped (DocuWaves shows its own contents);
- anything else is kept as the text it rendered to, and listed.

Only HTML parsing (BeautifulSoup with Python's own parser) -- nothing is
fetched, nothing in the export is executed.
"""
import posixpath
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, NavigableString, Tag
from markdownify import MarkdownConverter

from app.services import content_files

_HTML = (".html", ".htm")

_PANEL_KINDS = {
    "information": "NOTE",
    "info": "NOTE",
    "note": "WARNING",
    "warning": "CAUTION",
    "tip": "TIP",
    "success": "TIP",
    "error": "CAUTION",
}
_DROP_SELECTORS = (
    "script", "style", "#footer", "#comments-section", ".pageSection", "#likes-and-labels-container",
    ".page-metadata", "#breadcrumb-section", ".toc-macro", "div.toc", ".plugin_attachments_container",
    "span.aui-icon", ".confluence-information-macro-icon",
)
_HANDLED_MACROS = {"code", "info", "note", "warning", "tip", "panel", "expand", "status", "toc", "anchor", "noformat"}


def looks_like(files: dict[str, bytes]) -> bool:
    """A Confluence export, judged by what its pages contain."""
    for path, data in files.items():
        if path.lower().endswith(_HTML):
            head = data[:20000].lower()
            if b"confluence" in head and (b'id="main-content"' in head or b"available pages" in head):
                return True
    return False


@dataclass
class _Node:
    path: str
    title: str
    children: list


def _text(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _tree(files: dict[str, bytes]) -> list[_Node]:
    """The page tree from index.html, or [] when there is none."""
    index = next((p for p in files if p.split("/")[-1].lower() == "index.html"), None)
    if index is None:
        return []
    soup = BeautifulSoup(_text(files[index]), "html.parser")
    heading = next(
        (h for h in soup.find_all(["h2", "h3"]) if "available pages" in h.get_text(" ", strip=True).lower()), None
    )
    container = heading.find_next("ul") if heading else None
    if container is None:
        return []
    base = posixpath.dirname(index)

    def walk(ul: Tag) -> list[_Node]:
        nodes = []
        for li in ul.find_all("li", recursive=False):
            link = li.find("a", href=True)
            if link is None:
                continue
            href = link["href"].split("#")[0]
            path = posixpath.normpath(posixpath.join(base, href))
            nested = li.find("ul", recursive=False)
            nodes.append(_Node(path, link.get_text(" ", strip=True), walk(nested) if nested else []))
        return nodes

    return walk(container)


def _title(soup: BeautifulSoup) -> str:
    element = soup.find(id="title-text") or soup.find("title")
    text = element.get_text(" ", strip=True) if element else ""
    # "SPACE : Page title" -- the space name is not part of the page's.
    return text.split(" : ", 1)[1].strip() if " : " in text else text


class _Converter(MarkdownConverter):
    def convert_pre(self, el, text, parent_tags):
        language = el.get("data-language", "")
        code = el.get_text()
        fence = "````" if "```" in code else "```"
        return f"\n\n{fence}{language}\n{code.rstrip()}\n{fence}\n\n"


def _markdown(html: str) -> str:
    text = _Converter(
        heading_style="ATX", bullets="-", escape_underscores=False, escape_asterisks=False, escape_misc=False,
    ).convert(html)
    # A callout marker on a line of its own, directly followed by its body:
    # the shape GitHub (and DocuWaves) expect.
    text = re.sub(r"^> \[!(\w+)\]\s*\n>\s*\n", r"> [!\1]\n", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def _callout(soup: BeautifulSoup, element: Tag, kind: str, title: str, body: Tag | None) -> None:
    quote = soup.new_tag("blockquote")
    marker = soup.new_tag("p")
    marker.string = f"[!{kind}]"
    quote.append(marker)
    if title:
        heading = soup.new_tag("p")
        strong = soup.new_tag("strong")
        strong.string = title
        heading.append(strong)
        quote.append(heading)
    for child in list((body or element).children):
        quote.append(child.extract())
    element.replace_with(quote)


def _convert_page(path: str, soup: BeautifulSoup, targets: dict[str, str], own: str, notes: list[str]) -> str:
    content = soup.find(id="main-content") or soup.body or soup
    for selector in _DROP_SELECTORS:
        for element in content.select(selector):
            element.decompose()

    # Code blocks.
    for panel in content.select("div.code, div.preformatted"):
        pre = panel.find("pre")
        if pre is None:
            continue
        params = pre.get("data-syntaxhighlighter-params", "")
        match = re.search(r"brush:\s*([\w+#-]+)", params)
        language = {"plain": "", "text": "", "none": ""}.get(match.group(1), match.group(1)) if match else ""
        new = soup.new_tag("pre")
        new["data-language"] = language
        new.string = pre.get_text()
        panel.replace_with(new)

    # Info / note / warning / tip panels.
    for panel in content.select("div.confluence-information-macro"):
        classes = " ".join(panel.get("class", []))
        found = re.search(r"confluence-information-macro-(\w+)", classes.replace("confluence-information-macro-body", ""))
        kind = _PANEL_KINDS.get(found.group(1) if found else "information", "NOTE")
        title_el = panel.find(class_="title")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        if title_el:
            title_el.decompose()
        _callout(soup, panel, kind, title, panel.find(class_="confluence-information-macro-body"))

    # Expand.
    for expand in content.select("div.expand-container"):
        control = expand.find(class_="expand-control-text")
        title = control.get_text(" ", strip=True) if control else ""
        _callout(soup, expand, "NOTE", title, expand.find(class_="expand-content"))

    # Small inline things.
    for lozenge in content.select("span.status-macro"):
        strong = soup.new_tag("strong")
        strong.string = lozenge.get_text(" ", strip=True)
        lozenge.replace_with(strong)
    for emoticon in content.select("img.emoticon"):
        emoticon.replace_with(NavigableString(emoticon.get("alt") or ""))
    for user in content.select("a.confluence-userlink, a.user-mention"):
        user.replace_with(NavigableString(user.get_text(" ", strip=True)))

    # Links between pages, and images, relative to the Markdown file that
    # will hold this page.
    base = posixpath.dirname(path)
    own_dir = posixpath.dirname(own)
    for link in content.find_all("a", href=True):
        href = link["href"]
        if re.match(r"^[a-z][a-z0-9+.-]*:|^//|^#", href, re.IGNORECASE):
            continue
        target, _, fragment = href.partition("#")
        resolved = posixpath.normpath(posixpath.join(base, target.split("?")[0]))
        if resolved in targets:
            relative = posixpath.relpath(targets[resolved], own_dir or ".")
            link["href"] = relative + (f"#{fragment}" if fragment else "")
        else:
            link["href"] = posixpath.relpath(resolved, own_dir or ".")
    for image in content.find_all("img"):
        src = image.get("data-image-src") or image.get("src") or ""
        if not src or re.match(r"^[a-z][a-z0-9+.-]*:|^//", src, re.IGNORECASE):
            continue
        resolved = posixpath.normpath(posixpath.join(base, src.split("?")[0]))
        image["src"] = posixpath.relpath(resolved, own_dir or ".")
        image["alt"] = image.get("alt") or image.get("data-linked-resource-default-alias") or ""

    # Whatever macro is left: kept as the text it rendered to, and said.
    for macro in content.find_all(attrs={"data-macro-name": True}):
        name = macro.get("data-macro-name", "")
        if name not in _HANDLED_MACROS:
            notes.append(f"Confluence macro '{name}' kept as plain text")

    return _markdown(str(content))


def convert(files: dict[str, bytes]) -> tuple[dict[str, bytes], dict[str, int], list[str]]:
    """(the archive as Markdown + attachments, page order, notes per page as
    "<path>: <message>"). The HTML files themselves are not in the result."""
    pages = [p for p in files if p.lower().endswith(_HTML) and p.split("/")[-1].lower() != "index.html"]
    soups = {p: BeautifulSoup(_text(files[p]), "html.parser") for p in pages}
    tree = _tree(files)

    # Where each page goes: a directory per top-level page with children.
    placement: list[tuple[str, str, str]] = []  # (html path, directory, title)
    seen: set[str] = set()
    roots = tree[0].children if len(tree) == 1 and tree[0].children else tree
    if len(tree) == 1 and tree[0].children:
        placement.append((tree[0].path, "", tree[0].title))
        seen.add(tree[0].path)
    used_dirs: set[str] = set()
    categories: list[tuple[str, str]] = []  # (directory, label)

    def flatten(node: _Node, directory: str) -> None:
        if node.path in seen:
            return
        seen.add(node.path)
        placement.append((node.path, directory, node.title))
        for child in node.children:
            flatten(child, directory)

    for node in roots:
        if node.children:
            directory = content_files.make_slug(node.title)
            n = 2
            while directory in used_dirs:
                directory = f"{content_files.make_slug(node.title)}-{n}"
                n += 1
            used_dirs.add(directory)
            categories.append((directory, node.title))
            flatten(node, directory)
        else:
            flatten(node, "")
    # Pages the tree does not mention (no index.html, or an orphan).
    for path in sorted(pages):
        if path not in seen:
            seen.add(path)
            placement.append((path, "", _title(soups[path]) if path in soups else ""))

    # File names first, so links can point at them.
    targets: dict[str, str] = {}
    names_in_dir: dict[str, set[str]] = {}
    order: dict[str, int] = {}
    titles: dict[str, str] = {}
    for position, (path, directory, title) in enumerate(placement):
        if path not in soups:
            continue
        title = title or _title(soups[path]) or posixpath.splitext(path.split("/")[-1])[0]
        stem = content_files.make_slug(title)
        taken = names_in_dir.setdefault(directory, set())
        candidate, n = stem, 2
        while candidate in taken:
            candidate = f"{stem}-{n}"
            n += 1
        taken.add(candidate)
        target = posixpath.join(directory, f"{candidate}.md")
        targets[path] = target
        order[target] = position
        titles[target] = title

    result: dict[str, bytes] = {p: b for p, b in files.items() if not p.lower().endswith(_HTML)}
    notes: list[str] = []
    for path, target in targets.items():
        page_notes: list[str] = []
        body = _convert_page(path, soups[path], targets, target, page_notes)
        front = "---\ntitle: " + _yaml_string(titles[target]) + "\n---\n\n"
        result[target] = (front + body).encode("utf-8")
        notes += [f"{target}: {n}" for n in dict.fromkeys(page_notes)]
    for position, (directory, label) in enumerate(categories):
        result[f"{directory}/_category_.json"] = (
            '{"label": ' + _json_string(label) + f', "position": {position}' + "}"
        ).encode("utf-8")
    return result, order, notes


def _yaml_string(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _json_string(text: str) -> str:
    import json

    return json.dumps(text, ensure_ascii=False)
