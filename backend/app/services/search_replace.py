"""Search and replace across one project: "the product was renamed" without
opening forty pages by hand.

TWO STEPS, ON PURPOSE. A preview lists every page with a match, how many,
and a few lines around each, plus the page's revision. Applying names the
pages to change (a subset of the preview, ticked by a person) and the
revision each one had when it was previewed. A page somebody saved in
between is skipped as `changed` rather than rewritten on top of text nobody
looked at -- the same rule an editor's save follows.

ONE COMMIT for all pages (git_content_repo.batch), so the whole replacement
is one entry in the history and undone in one step.

WHAT IT SEARCHES is the text an editor would open: a waiting proposal's
when there is one, the page otherwise. Writing goes through
pages_store.update_page, so every rule a save follows holds here too: in a
project that requires approval, a live page gets a PROPOSAL, not a new live
text; a frozen version or a docs-as-code project is refused; the review
note is dropped for text that changed.

PLAIN TEXT, NOT REGULAR EXPRESSIONS. A regular expression runs in the
server process with no time limit, and one badly written pattern can keep
a worker busy for minutes. Case and whole-word matching cover what a rename
needs; anything cleverer is a job for the content repository and a text
editor. The replacement is literal too: no backreferences, no surprises
from a `\\1` in a product name.

Only the body is searched, never the title or the front matter.
"""
import re

from app.services import categories_store, content_sync, content_versions, git_content_repo, pages_store

MAX_FIND = 200
MAX_REPLACE = 1000
SNIPPETS_PER_PAGE = 5
CONTEXT = 40


class SearchError(ValueError):
    pass


def compile_pattern(find: str, case_sensitive: bool, whole_word: bool) -> re.Pattern:
    if not find or not find.strip():
        raise SearchError("Enter the text to search for.")
    if len(find) > MAX_FIND:
        raise SearchError(f"The search text can be at most {MAX_FIND} characters.")
    body = re.escape(find)
    if whole_word:
        # \b only means "word boundary" next to a word character. "C++" ends
        # in a non-word character, so the check is made on each side that
        # needs one, and skipped on the side that doesn't.
        if re.match(r"\w", find[0]):
            body = r"(?<!\w)" + body
        if re.match(r"\w", find[-1]):
            body = body + r"(?!\w)"
    return re.compile(body, 0 if case_sensitive else re.IGNORECASE)


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _editor_texts(project: dict, version: str, language: str | None):
    """(page, the text the editor would open) for every language file of
    every page of one version of the project."""
    for category in categories_store.list_categories(project["id"], version=version):
        for page in pages_store.list_all_pages(category["id"]):
            if language and page["language"] != language:
                continue
            pending = pages_store.pending_version(project, category, page) if page.get("has_pending") else None
            base = {**page, **({"title": pending["title"], "markdown_content": pending["markdown_content"]} if pending else {})}
            yield page, category, base, pending is not None


def preview(project: dict, version: str, pattern: re.Pattern, language: str | None = None) -> dict:
    pages = []
    total = 0
    for page, category, base, proposal in _editor_texts(project, version, language):
        text = base["markdown_content"]
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        total += len(matches)
        pages.append(
            {
                "id": page["id"],
                "title": base["title"],
                "slug": page["slug"],
                "language": page["language"],
                "category": category["name"],
                "published": bool(page["published"]),
                "proposal": proposal,
                # A live page in a project that needs approval: replacing
                # makes a proposal for somebody to approve, not a new text.
                "becomes_proposal": pages_store.review_required(project) and bool(page["published"]),
                "revision": pages_store.page_revision(base),
                "count": len(matches),
                "snippets": [
                    {
                        "before": _one_line(text[max(0, m.start() - CONTEXT) : m.start()]),
                        "match": m.group(0),
                        "after": _one_line(text[m.end() : m.end() + CONTEXT]),
                    }
                    for m in matches[:SNIPPETS_PER_PAGE]
                ],
            }
        )
    return {"pages": pages, "total": total}


def _commit_message(find: str, replace: str, count: int) -> str:
    def short(value: str) -> str:
        value = _one_line(value)
        return value if len(value) <= 60 else value[:57] + "..."

    return f'Replace "{short(find)}" with "{short(replace)}" in {count} page{"s" if count != 1 else ""}'


def apply(
    project: dict,
    version: str,
    pattern: re.Pattern,
    find: str,
    replace: str,
    revisions: dict[int, str],
    author: str,
) -> dict:
    """Replaces in the pages named in `revisions` (page id -> the revision
    the preview showed). Returns what was done and what was skipped, and
    why."""
    if len(replace) > MAX_REPLACE:
        raise SearchError(f"The replacement can be at most {MAX_REPLACE} characters.")
    content_versions.ensure_editable(project["slug"], version)
    wanted = dict(revisions)
    plan = []
    for page, _category, base, _proposal in _editor_texts(project, version, None):
        if page["id"] not in wanted:
            continue
        expected = wanted.pop(page["id"])
        if pages_store.page_revision(base) != expected:
            plan.append((page, base, expected, "changed"))
            continue
        plan.append((page, base, expected, None))
    skipped = [{"id": page_id, "reason": "not_found"} for page_id in wanted]

    todo = []
    for page, base, expected, reason in plan:
        if reason:
            skipped.append({"id": page["id"], "reason": reason})
            continue
        new_text, count = pattern.subn(lambda _m: replace, base["markdown_content"])
        if count == 0 or new_text == base["markdown_content"]:
            skipped.append({"id": page["id"], "reason": "unchanged"})
            continue
        todo.append((page, base, expected, new_text, count))

    done = []
    replacements = 0
    if todo:
        with git_content_repo.batch(_commit_message(find, replace, len(todo)), author), content_sync.deferred():
            for page, base, expected, new_text, count in todo:
                try:
                    pages_store.update_page(
                        page["id"], base["title"], page["slug"], new_text, page["category_id"], author,
                        expected_revision=expected,
                    )
                except pages_store.PageChangedError:
                    skipped.append({"id": page["id"], "reason": "changed"})
                    continue
                replacements += count
                done.append(
                    {
                        "id": page["id"],
                        "count": count,
                        "proposal": pages_store.review_required(project) and bool(page["published"]),
                    }
                )
    return {"done": done, "skipped": skipped, "replacements": replacements}
