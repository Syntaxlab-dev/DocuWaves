"""Links inside the documentation that no longer go anywhere.

WHAT IS CHECKED: everything this instance can answer for itself and
answer definitively -- links to a project, a category or a page here, a
`#fragment` on a page here, and a relative image or media path. Those either
resolve against the content repo or they do not, the answer is instant, and
it is never a false alarm.

WHAT IS DELIBERATELY NOT CHECKED: external URLs. Fetching them would mean
this server making requests to arbitrary addresses on someone else's say-so
-- a request-forgery surface pointed at whatever is reachable from inside
the network it runs in -- and the answers would be unreliable anyway, since
a great many sites answer a datacentre IP with 403 while serving a browser
perfectly. A checker that cries wolf gets switched off, and then the real
breakages go unseen too. External links belong in a job that runs outside
the instance, from an address that looks like a reader.

The anchor rule below has to match frontend/src/lib/headings.ts exactly:
the ids being checked are the ones that file emits, and a second slugifier
that disagreed would report working links as broken. It is duplicated here
rather than shared because one is TypeScript in the browser and one is
Python on the server -- the honest options were duplication with this note
on it, or a build step to generate one from the other.
"""
import re

from app.services import categories_store, content_assets, content_versions, pages_store, projects_store

# `[text](target)` and `![alt](target)`. Titles (`(url "title")`) are
# tolerated by stopping the target at the first whitespace.
_LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?[^)]*\)")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")

_ATX_HEADING_RE = re.compile(r"^ {0,3}(#{2,3})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_INLINE_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_INLINE_NOISE_RE = re.compile(r"[`*~]")
_NON_SLUG_RE = re.compile(r"[^\w\s-]", re.UNICODE)
_SPACE_RUN_RE = re.compile(r"[\s-]+")

_SKIPPED_SCHEMES = ("http://", "https://", "mailto:", "tel:", "data:", "ftp://", "//")


def _inline_text(markdown: str) -> str:
    return _INLINE_NOISE_RE.sub("", _INLINE_LINK_RE.sub(r"\1", markdown)).strip()


def _slugify_heading(text: str) -> str:
    # \w in Python's re with re.UNICODE covers letters, digits AND underscore,
    # where the TypeScript side uses \p{L}\p{N} -- so underscores are stripped
    # explicitly to keep the two identical.
    cleaned = _NON_SLUG_RE.sub("", text.lower()).replace("_", "")
    return _SPACE_RUN_RE.sub("-", cleaned.strip()) or "section"


def heading_ids(markdown: str) -> set[str]:
    """Every anchor a page emits, with the same de-duplication suffixes the
    renderer applies."""
    ids: set[str] = set()
    fence: str | None = None
    for line in markdown.split("\n"):
        match = _FENCE_RE.match(line)
        if fence is not None:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence):
                fence = None
            continue
        if match:
            fence = match.group(1)
            continue
        heading = _ATX_HEADING_RE.match(line)
        if not heading:
            continue
        text = _inline_text(heading.group(2))
        if not text:
            continue
        base = _slugify_heading(text)
        candidate, n = base, 2
        while candidate in ids:
            candidate, n = f"{base}-{n}", n + 1
        ids.add(candidate)
    return ids


def _targets(markdown: str) -> list[str]:
    """Link targets outside fenced code. A URL inside a ``` block is a
    sample, not a link, and reporting it broken would be noise."""
    out: list[str] = []
    fence: str | None = None
    for line in markdown.split("\n"):
        match = _FENCE_RE.match(line)
        if fence is not None:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence):
                fence = None
            continue
        if match:
            fence = match.group(1)
            continue
        out.extend(_LINK_RE.findall(line))
    return out


def _check_internal(target: str, project_slug: str, own_ids: set[str]) -> str:
    """"" = fine, otherwise why not. `target` starts with `/p/`."""
    segments = [s for s in target.split("/") if s][1:]  # drop the leading "p"
    if not segments:
        return "links to /p/ with no project"

    project = projects_store.get_project_by_slug(segments[0])
    if project is None:
        return f"no project '{segments[0]}'"
    rest = segments[1:]

    # An optional version sits where `c` and `pages` do -- the same
    # disambiguation the router and seo.parse_route make.
    version = ""
    if rest and rest[0] not in ("c", "pages"):
        version = rest[0]
        rest = rest[1:]
        if version not in content_versions.version_ids(project["slug"]) + [content_versions.CURRENT_ID]:
            return f"no version '{version}' in '{project['slug']}'"

    if not rest:
        return ""  # the project's landing page

    if rest[0] == "c":
        if len(rest) < 2:
            return "links to /c/ with no category"
        if categories_store.get_category_by_slug(project["id"], rest[1], version=version) is None:
            return f"no category '{rest[1]}' in '{project['slug']}'"
        return ""

    if rest[0] == "pages":
        if len(rest) < 2:
            return "links to /pages/ with no page"
        page_slug = rest[1].split("#")[0]
        page = pages_store.resolve_page(project["id"], page_slug, None, published_only=True, version=version)
        if page is None:
            return f"no published page '{page_slug}' in '{project['slug']}'"
        # A fragment on another page: check it against THAT page's headings.
        if "#" in rest[1]:
            fragment = rest[1].split("#", 1)[1]
            if fragment and fragment not in heading_ids(page["markdown_content"]):
                return f"no section '#{fragment}' on '{page_slug}'"
        return ""

    return f"'{target}' is not a reading URL"


def broken_links(project_slug: str = "") -> list[dict]:
    """Every link in every published page that does not resolve.

    Drafts are skipped: a page still being written is allowed to point at
    the page that will exist by the time it is published, and reporting
    those as breakages would train an author to ignore the list.
    """
    findings: list[dict] = []
    projects = [projects_store.get_project_by_slug(project_slug)] if project_slug else projects_store.list_projects()
    for project in [p for p in projects if p]:
        for version in content_versions.index_versions(project["slug"]):
            for category in categories_store.list_categories(project["id"], version=version):
                for page in pages_store.list_pages(category["id"], published_only=True):
                    own_ids = heading_ids(page["markdown_content"])
                    for target in _targets(page["markdown_content"]):
                        reason = _reason(target, project, category, page, version, own_ids)
                        if reason:
                            findings.append(
                                {
                                    "project_slug": project["slug"],
                                    "page_slug": page["slug"],
                                    "page_title": page["title"],
                                    "version": version,
                                    "target": target,
                                    "reason": reason,
                                }
                            )
    return findings


def _reason(target: str, project: dict, category: dict, page: dict, version: str, own_ids: set[str]) -> str:
    lowered = target.lower()
    if lowered.startswith(_SKIPPED_SCHEMES):
        return ""  # external, see this module's docstring

    if target.startswith("#"):
        fragment = target[1:]
        return "" if not fragment or fragment in own_ids else f"no section '{target}' on this page"

    if target.startswith("/p/"):
        return _check_internal(target, project["slug"], own_ids)

    if target.startswith("/"):
        return ""  # some other route on this site; not ours to judge

    # Anything left is a relative path, which in a page means an asset. It is
    # resolved from the page's own directory, exactly as the renderer does.
    relative = f"{version + '/' if version else ''}{category['slug']}/{target}"
    if content_assets.resolve_asset(project["slug"], relative) is None:
        return f"no file at '{target}'"
    return ""
