"""BookStack exports, turned into the Markdown the importer already takes in
(services/importer.py) -- the same idea as the Confluence and Notion
converters next to it.

What it reads is BookStack's PORTABLE ZIP (a book, chapter or page ->
Export -> "Portable ZIP", BookStack v25.02 and later): `data.json` with the
book's chapters and pages, and `files/` with their images and attachments.
Inside the pages' text, BookStack writes references instead of addresses:
`[[bsexport:image:12]]`, `[[bsexport:attachment:3]]`, `[[bsexport:page:7]]`
and so on; they become the paths of the converted files.

THE TREE. A book has chapters and pages; DocuWaves has categories and pages.
Pages directly in the book go into "General", every chapter becomes a
category, both in BookStack's own order (`priority`). A page with Markdown
(written in BookStack's Markdown editor) keeps it; any other page is
converted from its HTML. Attachments are listed at the end of their page:
links as links, images and media as files; other files (PDFs, archives)
by name only, since DocuWaves keeps no documents, and the preview says so. Tags are not taken over.
"""
import json
import posixpath
import re

from app.services import content_assets, content_files, import_confluence, site_languages

DATA = "data.json"
_REFERENCE = re.compile(r"\[\[bsexport:(\w+):(\d+)\]\]")


def looks_like(files: dict[str, bytes]) -> bool:
    raw = files.get(DATA)
    if raw is None:
        return False
    try:
        data = json.loads(raw.decode("utf-8-sig", errors="replace"))
    except ValueError:
        return False
    return isinstance(data, dict) and any(isinstance(data.get(k), dict) for k in ("book", "chapter", "page"))


def _attachments_heading() -> str:
    return "Attachments" if site_languages.default_language().startswith("en") else "Anhänge"


def _sorted(items) -> list[dict]:
    items = [i for i in (items or []) if isinstance(i, dict)]
    return sorted(items, key=lambda i: (i.get("priority") if isinstance(i.get("priority"), (int, float)) else 1 << 30))


def _unique(stem: str, taken: set[str]) -> str:
    stem = stem or "page"
    candidate, n = stem, 2
    while candidate in taken:
        candidate = f"{stem}-{n}"
        n += 1
    taken.add(candidate)
    return candidate


def convert(files: dict[str, bytes]) -> tuple[dict[str, bytes], dict[str, int], list[str]]:
    """(the export as Markdown + its files, page order, notes per page)."""
    data = json.loads(files[DATA].decode("utf-8-sig", errors="replace"))
    notes: list[str] = []

    # (directory, chapter label or "", page) in reading order.
    placement: list[tuple[str, str, dict]] = []
    categories: list[tuple[str, str]] = []
    used_dirs: set[str] = set()
    chapter_dirs: dict[int, str] = {}

    def add_chapter(chapter: dict) -> None:
        name = str(chapter.get("name") or "").strip() or "Chapter"
        directory = _unique(content_files.make_slug(name), used_dirs)
        categories.append((directory, name))
        if isinstance(chapter.get("id"), int):
            chapter_dirs[chapter["id"]] = directory
        for page in _sorted(chapter.get("pages")):
            placement.append((directory, name, page))

    if isinstance(data.get("book"), dict):
        book = data["book"]
        # Pages and chapters share one order in a BookStack book.
        entries = [("page", p) for p in book.get("pages") or [] if isinstance(p, dict)]
        entries += [("chapter", c) for c in book.get("chapters") or [] if isinstance(c, dict)]
        entries.sort(key=lambda e: e[1].get("priority") if isinstance(e[1].get("priority"), (int, float)) else 1 << 30)
        for kind, entry in entries:
            if kind == "page":
                placement.append(("", "", entry))
            else:
                add_chapter(entry)
    elif isinstance(data.get("chapter"), dict):
        add_chapter(data["chapter"])
    else:
        placement.append(("", "", data["page"]))

    # File names first: references between pages point at them.
    images: dict[int, str] = {}
    attachments: dict[int, dict] = {}
    for _, _, page in placement:
        for image in page.get("images") or []:
            if isinstance(image, dict) and isinstance(image.get("id"), int) and image.get("file"):
                images[image["id"]] = posixpath.join("files", str(image["file"]))
        for attachment in page.get("attachments") or []:
            if isinstance(attachment, dict) and isinstance(attachment.get("id"), int):
                attachments[attachment["id"]] = attachment

    targets: dict[int, str] = {}
    order: dict[str, int] = {}
    names_in_dir: dict[str, set[str]] = {}
    first_in_dir: dict[str, str] = {}
    pages: list[tuple[str, dict]] = []
    for position, (directory, _, page) in enumerate(placement):
        title = str(page.get("name") or "").strip() or "Page"
        stem = _unique(content_files.make_slug(title), names_in_dir.setdefault(directory, set()))
        target = posixpath.join(directory, f"{stem}.md")
        order[target] = position
        first_in_dir.setdefault(directory, target)
        if isinstance(page.get("id"), int):
            targets[page["id"]] = target
        pages.append((target, page))
    first_page = pages[0][0] if pages else ""

    result: dict[str, bytes] = {p: b for p, b in files.items() if p != DATA}
    for target, page in pages:
        own_dir = posixpath.dirname(target) or "."
        page_notes: list[str] = []

        def relative(path: str, own_dir=own_dir) -> str:
            return posixpath.relpath(path, own_dir)

        def reference(match: re.Match, page_notes=page_notes) -> str:
            kind, number = match.group(1), int(match.group(2))
            if kind == "image" and number in images:
                return relative(images[number])
            if kind == "page" and number in targets:
                return relative(targets[number])
            if kind == "chapter" and number in chapter_dirs and chapter_dirs[number] in first_in_dir:
                return relative(first_in_dir[chapter_dirs[number]])
            if kind == "book" and first_page:
                return relative(first_page)
            if kind == "attachment" and number in attachments:
                attachment = attachments[number]
                if attachment.get("file"):
                    return relative(posixpath.join("files", str(attachment["file"])))
                if attachment.get("link"):
                    return str(attachment["link"])
            page_notes.append(f"BookStack reference to a {kind} that is not in the export")
            return "#"

        markdown = str(page.get("markdown") or "")
        if markdown.strip():
            body = _REFERENCE.sub(reference, markdown.replace("\r\n", "\n")).strip() + "\n"
        else:
            body = import_confluence.html_to_markdown(_REFERENCE.sub(reference, str(page.get("html") or "")))

        listed = []
        for attachment in page.get("attachments") or []:
            if not isinstance(attachment, dict):
                continue
            name = str(attachment.get("name") or "").strip() or "Attachment"
            if attachment.get("file"):
                file = str(attachment["file"])
                if posixpath.splitext(file)[1].lower() in content_assets.CONTENT_TYPES:
                    listed.append(f"- [{name}]({relative(posixpath.join('files', file))})")
                else:
                    # DocuWaves keeps images and media, not documents.
                    listed.append(f"- {name}")
                    page_notes.append(f"attachment '{name}' not taken over (only images, audio and video are)")
            elif attachment.get("link"):
                listed.append(f"- [{name}]({attachment['link']})")
        if listed:
            body = body.rstrip("\n") + "\n\n## " + _attachments_heading() + "\n\n" + "\n".join(listed) + "\n"

        title = str(page.get("name") or "").strip() or "Page"
        front = "---\ntitle: " + import_confluence.yaml_string(title) + "\n---\n\n"
        result[target] = (front + body).encode("utf-8")
        notes += [f"{target}: {n}" for n in dict.fromkeys(page_notes)]

    for position, (directory, label) in enumerate(categories):
        result[f"{directory}/_category_.json"] = (
            '{"label": ' + json.dumps(label, ensure_ascii=False) + f', "position": {position + 1}' + "}"
        ).encode("utf-8")
    return result, order, notes
