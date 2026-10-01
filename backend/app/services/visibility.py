"""Who may see a PRIVATE project.

A project is public unless its `_project.yml` says `visibility: private`.
A private project exists only for signed-in accounts -- any role, the
`reader` role included (see users_store.py). For everybody else it does not
exist at all: not a 403, a 404, the same answer as a slug nobody ever used,
so a stranger cannot even learn that it is there.

THE RULE IS APPLIED AT EVERY DOOR, and that is the whole difficulty: hiding
the project page while the search, the sitemap, a feed, the typo
suggestions, the page description, the chat or a webhook still say what is
in it would be hiding nothing. Each of those asks here (or filters on the
`projects.private` column with the flag from here); the tests in
test_private_projects.py walk every one of them, signed in and not.

WHAT IS DELIBERATELY NOT SIGNED-IN-AWARE:
- the RSS feeds and the sitemap -- read by machines that never sign in, and
  cached by them; a private page in either would be a private page in
  somebody's feed reader forever;
- the typo-correction vocabulary (search_suggest.py) -- it is shared by all
  readers, so it is built from public projects only;
- webhooks -- they post to channels whose members are unknown.

A preview link still shows its one page to whoever holds it: that is what a
preview link is for, and it was made by somebody who could see the page.

PRIVATE IS ABOUT THE WEBSITE. The content repo holds the same files; if that
repository is public, so is everything in it. The README and the admin form
say so.
"""
from starlette.requests import Request

from app.services import db, session_registry_store, users_store


def signed_in(request: Request | None) -> bool:
    """Whether this request carries a live session of an existing account.

    The same three checks the admin middleware makes (auth_guard.py) -- an
    authenticated session, still registered (not signed out or revoked), of
    an account that still exists -- because the public routes are exempt
    from that middleware and must not trust a bare cookie flag. Cached on the
    request: one page view asks several times."""
    if request is None:
        return False
    cached = getattr(request.state, "can_see_private", None)
    if cached is not None:
        return cached
    allowed = False
    session = request.scope.get("session") or {}
    if session.get("authenticated"):
        session_id = session.get("session_id")
        if session_id and session_registry_store.exists(session_id):
            allowed = users_store.get_user(session.get("username") or "") is not None
    request.state.can_see_private = allowed
    return allowed


def can_see(project: dict | None, request: Request | None) -> bool:
    """A project row this request may see: public, or private and signed in."""
    return project is not None and (not project.get("private") or signed_in(request))


def private_project_ids() -> set[int]:
    with db.get_connection() as conn:
        rows = conn.execute("SELECT id FROM projects WHERE private = 1").fetchall()
    return {r[0] for r in rows}
