"""Approval before publishing: the review workflow.

A project can say `review: required` in its `_project.yml`. From then on
nothing in it goes live without a second person's approval:

- A DRAFT is written as before. Instead of "publish", its author submits it
  for review; an approval publishes it.
- A PUBLISHED page keeps its live text while somebody works on it. Every save
  goes to a PROPOSED version next to it, `<category>/_pending/<page file>`,
  and readers keep reading the live file until the proposal is approved --
  then the proposal becomes the page, in one commit, and `_pending/` is
  cleaned up. Discarding a proposal deletes the file; the live page never
  noticed.

FOUR EYES. Whoever last changed the text (`review_changed_by`) may not
approve it -- not the person who submitted it, the person who WROTE it: a
colleague pressing "submit" on somebody's text does not make that somebody
a reviewer. Approving, or asking for changes, is open to every role that
can open the admin area, read-only accounts included (see auth_guard.py):
reviewing is reading, and the people best placed to check a text are often
the ones who should not be editing it.

WHERE THE STATE LIVES. In the frontmatter of the text under review -- the
proposal file when there is one, the page file for a draft -- like every
other fact about a page, so the content repo stays the whole truth and a
reindex rebuilds the queue (pages.review_status, see content_sync.py).
Approving clears it: a published page carries no workflow lines, only the
review note (`reviewed_by`/`reviewed_at`) that the approval writes.

Every write is an ordinary content write: refused on a frozen version, one
commit, one reindex, and holding the editor's save lock -- an approval must
not slip in between a save's revision check and its write.
"""
import difflib
import secrets
from datetime import datetime, timezone

from app.services import (
    categories_store,
    content_files,
    content_sync,
    content_versions,
    db,
    git_content_repo,
    pages_store,
    projects_store,
    proposal_branches,
    webhooks,
)

PENDING = "pending"
CHANGES_REQUESTED = "changes_requested"

_TEXT_MAX = 2000
# The same limit as the review note's name (pages_store._REVIEWER_MAX_LENGTH).
_NAME_MAX = 80


# A passage is a sentence or a paragraph, not a section: long enough to say
# which words are meant, short enough to find again after an edit.
_QUOTE_MAX = 500
# Beyond this a page needs a conversation, not more margin notes.
_COMMENTS_MAX = 100


class ReviewError(Exception):
    """Why this review action is not possible right now. `code` is what the
    API answers with:

    not_found          no such page
    nothing_to_review  a live page with no proposed changes in a project that
                       needs approval -- there is nothing to look at
    already_submitted  it is waiting for a decision already
    not_submitted      approve/request changes/withdraw on something nobody
                       submitted
    own_change         the four-eyes rule: you wrote this text
    no_draft           a comment on a live page with no proposed changes:
                       there is no text under review to comment on
    empty              a comment with no text, or no passage
    too_many           the page already has _COMMENTS_MAX comments
    no_comment         no comment with that id
    not_yours          deleting somebody else's comment"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clip(text: str, limit: int = _TEXT_MAX) -> str:
    return (text or "").strip()[:limit]


def _resolve(page: dict) -> tuple[dict, dict]:
    project = projects_store.get_project(page["project_id"])
    category = categories_store.get_category(page["category_id"])
    if project is None or category is None:
        raise ReviewError("not_found")
    return project, category


def _load(page_id: int) -> tuple[dict, dict, dict, dict | None, dict]:
    """(page, project, category, proposal or None, review state)."""
    page = pages_store.get_page(page_id)
    if page is None:
        raise ReviewError("not_found")
    project, category = _resolve(page)
    pending = pages_store.pending_version(project, category, page)
    if pending is not None:
        review = pending["review"]
    else:
        live = content_files.read_page(project["slug"], category["slug"], page["slug"], page["language"], page["version"])
        review = (live or {}).get("review", {})
    return page, project, category, pending, review


def _comments_state(review: dict, text: str | None) -> list[dict]:
    """The comments as the editor shows them. `outdated`: the passage is no
    longer in the text under review -- somebody rewrote it, which usually
    means the comment was dealt with, and in any case it can no longer be
    pointed at. Shown apart, never dropped: only resolving or deleting
    removes a comment from the list."""
    return [
        {**c, "outdated": text is not None and bool(c["quote"]) and c["quote"] not in text}
        for c in content_files.comments_from(review.get(content_files.COMMENTS_KEY))
    ]


def _state(project: dict, pending: dict | None, review: dict, text: str | None = None) -> dict:
    return {
        "comments": _comments_state(review, text),
        "required": bool(project.get("review_required")),
        "status": review.get("review_status", ""),
        "pending": pending is not None,
        "submitted_by": review.get("review_submitted_by", ""),
        "submitted_at": review.get("review_submitted_at", ""),
        "note": review.get("review_note", ""),
        "comment": review.get("review_comment", ""),
        "decided_by": review.get("review_decided_by", ""),
        "changed_by": review.get("review_changed_by", ""),
    }


def editor_view(page: dict) -> dict:
    """The page as the editor should open it: the proposed text when one is
    waiting (that is what the next save builds on), the live title kept as
    `live_title` for the banner, and the review state under `review`."""
    project, category = _resolve(page)
    pending = pages_store.pending_version(project, category, page)
    if pending is not None:
        view = {**page, "title": pending["title"], "markdown_content": pending["markdown_content"]}
        review = pending["review"]
    else:
        view = dict(page)
        live = content_files.read_page(project["slug"], category["slug"], page["slug"], page["language"], page["version"])
        review = (live or {}).get("review", {})
    view["live_title"] = page["title"]
    view["review"] = _state(project, pending, review, view["markdown_content"])
    branch = pending is not None and proposal_branches.branch_for(
        project["slug"], category["slug"], page["slug"], page["language"], page["version"]
    )
    if branch:
        view["review"]["branch"] = branch
    return view


def _write_state(page: dict, project: dict, category: dict, pending: dict | None, review: dict, message: str, author: str) -> None:
    if pending is not None:
        paths = content_files.write_pending(
            project["slug"], category["slug"], page["slug"], page["language"], page["version"],
            pending["title"], pending["markdown_content"], review,
        )
    else:
        paths = content_files.write_page(
            project["slug"], category["slug"], page["slug"], page["title"], page["markdown_content"],
            page["sort_order"], page["published"], page["language"], page["version"],
            reviewed_by=page["reviewed_by"], reviewed_at=page["reviewed_at"], review=review,
        )
    git_content_repo.commit_and_push(paths, message, author)
    content_sync.full_sync()


def _label(page: dict, pending: dict | None) -> str:
    return f"{(pending or page)['title']} [{page['language'] or 'default'}]"


def submit(page_id: int, author: str, note: str = "") -> dict:
    with pages_store._update_lock:
        page, project, category, pending, review = _load(page_id)
        content_versions.ensure_editable(project["slug"], page["version"])
        if pending is None and page["published"] and project.get("review_required"):
            raise ReviewError("nothing_to_review")
        if review.get("review_status") == PENDING:
            raise ReviewError("already_submitted")
        review = {
            **review,
            "review_status": PENDING,
            "review_submitted_by": author,
            "review_submitted_at": _now(),
            "review_note": _clip(note),
            "review_comment": "",
            "review_decided_by": "",
        }
        # A page from before this feature has no author on record; the one
        # submitting it is the closest thing to one.
        if not review.get("review_changed_by"):
            review["review_changed_by"] = author
        _write_state(page, project, category, pending, review, f"Submit for review: {_label(page, pending)}", author)
    announced = {**page, "title": (pending or page)["title"]}
    webhooks.notify(
        "review_requested", announced, project, category, {"kind": "change" if pending else "new"}, actor=author
    )
    return editor_view(pages_store.get_page(page_id) or page)


def request_changes(page_id: int, reviewer: str, comment: str = "") -> dict:
    with pages_store._update_lock:
        page, project, category, pending, review = _load(page_id)
        content_versions.ensure_editable(project["slug"], page["version"])
        if review.get("review_status") != PENDING:
            raise ReviewError("not_submitted")
        review = {
            **review,
            "review_status": CHANGES_REQUESTED,
            "review_comment": _clip(comment),
            "review_decided_by": reviewer,
        }
        _write_state(page, project, category, pending, review, f"Request changes: {_label(page, pending)}", reviewer)
    announced = {**page, "title": (pending or page)["title"]}
    webhooks.notify(
        "review_decided", announced, project, category, {"decision": "changes_requested"},
        actor=reviewer, submitter=review.get("review_submitted_by", ""), comment=review.get("review_comment", ""),
    )
    return editor_view(pages_store.get_page(page_id) or page)


def withdraw(page_id: int, author: str) -> dict:
    """Takes a submission back -- the text stays exactly as it is."""
    with pages_store._update_lock:
        page, project, category, pending, review = _load(page_id)
        content_versions.ensure_editable(project["slug"], page["version"])
        if review.get("review_status") != PENDING:
            raise ReviewError("not_submitted")
        review = {**review, "review_status": ""}
        _write_state(page, project, category, pending, review, f"Withdraw from review: {_label(page, pending)}", author)
    return editor_view(pages_store.get_page(page_id) or page)


def discard(page_id: int, author: str) -> dict:
    """Throws the proposed changes to a live page away. The live page is
    untouched -- it never had them."""
    with pages_store._update_lock:
        page, project, category, pending, _review = _load(page_id)
        content_versions.ensure_editable(project["slug"], page["version"])
        if pending is None:
            raise ReviewError("nothing_to_review")
        paths = content_files.delete_pending(project["slug"], category["slug"], page["slug"], page["language"], page["version"])
        git_content_repo.commit_and_push(paths, f"Discard proposed changes: {_label(page, pending)}", author)
        content_sync.full_sync()
    return editor_view(pages_store.get_page(page_id) or page)


def approve(page_id: int, reviewer: str) -> dict:
    """Publishes what was submitted: the proposal replaces the live text, or
    the draft goes live. Writes the review note (who, today) and clears the
    workflow state, in one commit."""
    with pages_store._update_lock:
        page, project, category, pending, review = _load(page_id)
        content_versions.ensure_editable(project["slug"], page["version"])
        if review.get("review_status") != PENDING:
            raise ReviewError("not_submitted")
        wrote = review.get("review_changed_by") or review.get("review_submitted_by") or ""
        if wrote and wrote == reviewer:
            raise ReviewError("own_change")
        title, markdown = (pending["title"], pending["markdown_content"]) if pending else (page["title"], page["markdown_content"])
        today = datetime.now(timezone.utc).date().isoformat()
        paths = content_files.write_page(
            project["slug"], category["slug"], page["slug"], title, markdown, page["sort_order"], True,
            page["language"], page["version"], reviewed_by=reviewer[:_NAME_MAX], reviewed_at=today, review={},
        )
        if pending is not None:
            paths += content_files.delete_pending(
                project["slug"], category["slug"], page["slug"], page["language"], page["version"]
            )
        git_content_repo.commit_and_push(paths, f"Approve: {_label(page, pending)}", reviewer)
        content_sync.full_sync()
        updated = pages_store.get_page_by_slug(page["project_id"], page["slug"], page["language"], page["version"])
    webhooks.notify(
        "review_decided", updated or page, project, category, {"decision": "approved"},
        actor=reviewer, submitter=review.get("review_submitted_by", ""),
    )
    if not page["published"]:
        webhooks.notify("published", updated or page, project, category, actor=reviewer)
    elif title != page["title"] or markdown != page["markdown_content"]:
        webhooks.notify(
            "updated", updated or {**page, "title": title, "markdown_content": markdown}, project, category,
            actor=reviewer,
        )
    return editor_view(updated or page)


def _under_review(page: dict, pending: dict | None) -> str:
    """The text a comment is about: the proposal, or the draft. A live page
    with neither has nothing under review -- a comment on it would sit in
    the published file's frontmatter until some later approval cleared it."""
    if pending is not None:
        return pending["markdown_content"]
    if not page["published"]:
        return page["markdown_content"]
    raise ReviewError("no_draft")


def add_comment(page_id: int, author: str, quote: str, text: str) -> dict:
    """A note on one passage of the text under review. Open to everyone who
    may review (read-only accounts included, see auth_guard.py): pointing
    at a sentence changes no word of it.

    Stored with the review state in the text's own frontmatter, so it is in
    the repository like the rest of the review, and the approval that
    publishes the text clears it (the history keeps it)."""
    quote = (quote or "").strip()[:_QUOTE_MAX]
    text = _clip(text)
    if not quote or not text:
        raise ReviewError("empty")
    with pages_store._update_lock:
        page, project, category, pending, review = _load(page_id)
        content_versions.ensure_editable(project["slug"], page["version"])
        _under_review(page, pending)
        comments = content_files.comments_from(review.get(content_files.COMMENTS_KEY))
        if len(comments) >= _COMMENTS_MAX:
            raise ReviewError("too_many")
        comments.append(
            {"id": secrets.token_hex(4), "quote": quote, "text": text, "by": author[:_NAME_MAX], "at": _now(), "resolved_by": ""}
        )
        review = {**review, content_files.COMMENTS_KEY: comments}
        _write_state(page, project, category, pending, review, f"Comment: {_label(page, pending)}", author)
    return editor_view(pages_store.get_page(page_id) or page)


def _change_comment(page_id: int, user: str, comment_id: str, change) -> dict:
    with pages_store._update_lock:
        page, project, category, pending, review = _load(page_id)
        content_versions.ensure_editable(project["slug"], page["version"])
        comments = content_files.comments_from(review.get(content_files.COMMENTS_KEY))
        target = next((c for c in comments if c["id"] == comment_id), None)
        if target is None:
            raise ReviewError("no_comment")
        comments, message = change(comments, target)
        review = {**review, content_files.COMMENTS_KEY: comments}
        _write_state(page, project, category, pending, review, f"{message}: {_label(page, pending)}", user)
    return editor_view(pages_store.get_page(page_id) or page)


def resolve_comment(page_id: int, user: str, comment_id: str, resolved: bool = True) -> dict:
    """Marks a comment done (or open again). Anybody who may review may:
    the author answering "fixed" and the reviewer agreeing are both normal."""

    def change(comments, target):
        target["resolved_by"] = user[:_NAME_MAX] if resolved else ""
        return comments, "Resolve comment" if resolved else "Reopen comment"

    return _change_comment(page_id, user, comment_id, change)


def delete_comment(page_id: int, user: str, comment_id: str) -> dict:
    """Only by whoever wrote it -- taking back your own note is fine,
    deleting somebody else's objection is not (resolve it instead)."""

    def change(comments, target):
        if target["by"] != user:
            raise ReviewError("not_yours")
        return [c for c in comments if c is not target], "Delete comment"

    return _change_comment(page_id, user, comment_id, change)


def diff(page_id: int) -> dict:
    """What an approval would change: the live text against the proposal,
    or -- for a draft, which has no live text -- the whole draft as new."""
    page, project, category, pending, review = _load(page_id)
    if pending is not None:
        live = {"title": page["title"], "markdown_content": page["markdown_content"]}
        proposed = {"title": pending["title"], "markdown_content": pending["markdown_content"]}
    else:
        live = {"title": page["title"], "markdown_content": page["markdown_content"]} if page["published"] else None
        proposed = {"title": page["title"], "markdown_content": page["markdown_content"]}
    before = (live or {}).get("markdown_content", "").splitlines()
    after = proposed["markdown_content"].splitlines()
    return {
        "live": live,
        "proposed": proposed,
        "diff": "\n".join(difflib.unified_diff(before, after, "live", "proposed", lineterm="")),
        "review": _state(project, pending, review, proposed["markdown_content"]),
    }


def queue() -> list[dict]:
    """Everything waiting for a decision, oldest submission first."""
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        ids = [r[0] for r in conn.execute(
            f"SELECT id FROM pages WHERE review_status = {placeholder}", (PENDING,)
        ).fetchall()]
    entries = []
    for page_id in ids:
        try:
            page, project, category, pending, review = _load(page_id)
        except ReviewError:
            continue
        state = _state(project, pending, review)
        entries.append({
            "id": page["id"],
            "title": (pending or page)["title"],
            "slug": page["slug"],
            "language": page["language"],
            "version": page["version"],
            "published": page["published"],
            "project_slug": project["slug"],
            "project_name": project["name"],
            "category_name": category["name"],
            # What the admin needs to open the page in its editor.
            "category_id": category["id"],
            **{k: state[k] for k in ("pending", "submitted_by", "submitted_at", "note", "changed_by")},
        })
    return sorted(entries, key=lambda e: e["submitted_at"])
