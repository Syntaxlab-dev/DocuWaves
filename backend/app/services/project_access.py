"""Permissions per project: an account's role, different in one project.

An account has ONE role for the whole instance (services/users_store.py).
This adds exceptions to it, project by project, so that "may write in
project A, may only read everything else" is something an admin can say:

    viewer account + `editor` in A   writes in A, reads the rest
    editor account + `viewer` in B   writes everywhere except B

WHAT AN EXCEPTION CAN BE. Only `viewer` (read only here) or `editor` (may
write here). Never `admin`: what an admin may do is about the instance, not
about a project, so "admin of project A" would mean nothing. Never `reader`:
a reader cannot open the admin area at all, and hiding ONE project from an
account that can is a different feature (reading is not narrowed here --
see "WHAT THIS IS NOT" below).

WHO IT APPLIES TO. Viewer and editor accounts. An admin's exceptions would
be dead rows (an admin may do everything, everywhere) and a reader's could
not be reached (the admin area is closed to readers before any project is
looked at), so effective_role() ignores both and the admin UI offers
neither.

KEYED BY SLUG, not by id. A project's id belongs to the content index,
which is rebuilt from the files and renumbered whenever the schema changes;
its slug is its directory name in the content repository, the thing that
actually stays put. Renaming a project changes its slug, so the router
that renames moves the exceptions with it (rename_project), and the one
that deletes takes them away (forget_project). A project that vanishes
another way -- a commit that deletes its directory -- leaves its rows
behind; they are harmless (nothing is in that project to write) and come
back into force only if a project with the very same slug does.

WHERE IT IS ENFORCED. In the middleware, like the rest of the role rules
(see auth_guard.py), for every write whose PATH names the project -- a page
id, a category id, a project id or slug. A few writes name it in the
request BODY instead (creating a page names its category; a snippet names
its project); the middleware cannot read a body, so it lets those through
to the endpoint for an account that might be allowed, and the endpoint calls
require_write(). WRITE_ROUTES below says which kind every admin write is,
and a test fails when a write route is added without saying.

WHAT THIS IS NOT. It does not hide projects. A viewer with `editor` in A
still reads the drafts of B in the admin area, exactly as a viewer always
could. Read access per project is a separate, larger change (every list
and search in the admin API would have to be filtered) and is not needed
for the case this exists for: letting somebody write where they should,
and only there.
"""

import re

from fastapi import HTTPException, Request

from app.services import db, users_store

# The two roles an exception may set. See the module docstring for why
# these and only these.
GRANTABLE = (users_store.VIEWER, users_store.EDITOR)
# The account roles exceptions apply to.
_APPLIES_TO = (users_store.VIEWER, users_store.EDITOR)


def _placeholder() -> str:
    return "%s" if db.is_postgres() else "?"


# ---- Storage ----


def grants(username: str) -> dict[str, str]:
    """{project slug: role} for one account; {} for none."""
    p = _placeholder()
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT project_slug, role FROM project_roles WHERE username = {p} ORDER BY project_slug",
            (username,),
        ).fetchall()
    return {row[0]: row[1] for row in rows if row[1] in GRANTABLE}


def all_grants() -> dict[str, dict[str, str]]:
    """{username: {project slug: role}} -- for the accounts list, in one query."""
    with db.get_connection() as conn:
        rows = conn.execute("SELECT username, project_slug, role FROM project_roles").fetchall()
    result: dict[str, dict[str, str]] = {}
    for username, slug, role in rows:
        if role in GRANTABLE:
            result.setdefault(username, {})[slug] = role
    return result


def set_grants(username: str, new: dict[str, str]) -> dict[str, str]:
    """Replaces every exception of one account. Unknown roles are refused by
    the caller (routers/users.py); this only writes what it is given."""
    p = _placeholder()
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM project_roles WHERE username = {p}", (username,))
        for slug, role in sorted(new.items()):
            conn.execute(
                f"INSERT INTO project_roles (username, project_slug, role) VALUES ({p}, {p}, {p})",
                (username, slug, role),
            )
    return grants(username)


def forget_user(username: str) -> None:
    p = _placeholder()
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM project_roles WHERE username = {p}", (username,))


def forget_project(slug: str) -> None:
    p = _placeholder()
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM project_roles WHERE project_slug = {p}", (slug,))


def rename_project(old_slug: str, new_slug: str) -> None:
    if old_slug == new_slug:
        return
    p = _placeholder()
    with db.get_connection() as conn:
        # A row already keyed by the new slug (left over from a project that
        # vanished by commit) would collide; the renamed project's own
        # exceptions are the ones that mean something now.
        conn.execute(f"DELETE FROM project_roles WHERE project_slug = {p}", (new_slug,))
        conn.execute(
            f"UPDATE project_roles SET project_slug = {p} WHERE project_slug = {p}", (new_slug, old_slug)
        )


# ---- Deciding ----


def effective_role(user: dict, project_slug: str | None) -> str:
    """The role this account has in this project. No project (an
    instance-wide write) or no exception = the account's own role."""
    role = users_store.normalize_role(user.get("role", ""))
    if not project_slug or role not in _APPLIES_TO:
        return role
    return grants(user["username"]).get(project_slug, role)


def may_write_somewhere(user: dict) -> bool:
    """Whether this account can write in at least one project -- the
    middleware's test for letting a body-checked write through to its
    endpoint, which then decides with require_write()."""
    role = users_store.normalize_role(user.get("role", ""))
    if users_store.may_write(role):
        return True
    return role in _APPLIES_TO and users_store.EDITOR in grants(user["username"]).values()


def writable_projects(user: dict) -> dict[str, str]:
    """The exceptions that matter for the UI, for /api/auth/status."""
    role = users_store.normalize_role(user.get("role", ""))
    return grants(user["username"]) if role in _APPLIES_TO else {}


def require_write(request: Request, project_slug: str | None = None, *, project_id: int | None = None) -> None:
    """For an endpoint that learns its project from the request body. 403
    unless the signed-in account may write there. A request with no account
    on it (an API token, which never reaches the admin API, or a test that
    calls the endpoint function directly) has nothing to check -- and looks
    nothing up, which is why a project can be named by id here."""
    user = getattr(getattr(request, "state", None), "user", None)
    if user is None:
        return
    if project_id is not None:
        from app.services import projects_store

        project = projects_store.get_project(project_id)
        project_slug = project["slug"] if project else None
    if not users_store.may_write(effective_role(user, project_slug)):
        raise HTTPException(status_code=403, detail=PROJECT_READ_ONLY)


PROJECT_READ_ONLY = "Your account can read this project but not change it."
INSTANCE_READ_ONLY = "Your account may write in single projects only, and this change is about the whole instance."


# ---- Which project a write is about ----
#
# Every write route of the admin API, by how its project is found:
#
#   "page" / "category" / "project_id" / "project_slug" / "preview_link"
#                -- from the path (the first capture group), so the
#                   middleware decides
#   "query"      -- from the `project` query parameter; blank = instance-wide
#   "body"       -- from the request body: the middleware lets an account
#                   that may write somewhere through, and the endpoint calls
#                   require_write()
#   "instance"   -- about no one project (or about all of them: creating a
#                   project, reordering them, the content repo's sync), so
#                   only the account's own role counts
#
# Keys are (method, regex). Matched in order; the first match wins.

_ID = r"(\d+)"
_SLUG = r"([^/]+)"

WRITE_ROUTES: list[tuple[str, re.Pattern, str]] = [
    (m, re.compile(rf"^/api/admin{path}$"), kind)
    for m, path, kind in [
        ("POST", "/content-repo/sync", "instance"),
        ("POST", "/resolve-markdown", "body"),
        ("PUT", "/variables", "body"),
        ("PUT", "/snippets/[^/]+", "body"),
        ("DELETE", "/snippets/[^/]+", "query"),
        ("POST", "/projects", "instance"),
        ("PUT", f"/projects/{_ID}", "project_id"),
        ("DELETE", f"/projects/{_ID}", "project_id"),
        ("POST", f"/projects/{_ID}/move", "instance"),
        ("POST", f"/projects/{_ID}/categories", "project_id"),
        ("POST", f"/projects/{_ID}/replace", "project_id"),
        ("POST", f"/projects/{_ID}/replace/preview", "project_id"),
        ("PUT", f"/categories/{_ID}", "category"),
        ("DELETE", f"/categories/{_ID}", "category"),
        ("POST", f"/categories/{_ID}/move", "category"),
        ("POST", "/pages", "body"),
        ("POST", "/pages/bulk", "body"),
        ("PUT", f"/pages/{_ID}", "body"),
        ("DELETE", f"/pages/{_ID}", "page"),
        ("POST", f"/pages/{_ID}/.+", "page"),
        ("PUT", f"/pages/{_ID}/.+", "page"),
        ("DELETE", f"/pages/{_ID}/.+", "page"),
        ("DELETE", f"/preview-links/{_ID}", "preview_link"),
        ("POST", f"/projects/{_SLUG}/versions", "project_slug"),
        ("DELETE", f"/projects/{_SLUG}/versions/[^/]+", "project_slug"),
        ("POST", f"/projects/{_SLUG}/assets", "project_slug"),
        ("DELETE", f"/projects/{_SLUG}/assets/[^/]+", "project_slug"),
        ("POST", "/import/preview", "query"),
        ("POST", "/import", "query"),
        ("POST", "/import/git/preview", "query"),
        ("POST", "/import/git", "query"),
        ("DELETE", f"/feedback/{_SLUG}/[^/]+", "project_slug"),
        ("POST", "/search-gaps/draft", "body"),
        ("POST", "/writing-help", "body"),
        ("POST", "/translation-draft", "body"),
        ("DELETE", "/search-gaps", "instance"),
        ("DELETE", f"/search-gaps/{_ID}", "instance"),
    ]
]


def classify(method: str, path: str) -> tuple[str, str | None]:
    """(kind, captured value) for a write; ("instance", None) when no rule
    matches. Admin-only areas (users, tokens, site) never get here with a
    non-admin account, so they need no rule."""
    for rule_method, pattern, kind in WRITE_ROUTES:
        if rule_method != method:
            continue
        match = pattern.match(path)
        if match:
            return kind, (match.group(1) if match.groups() else None)
    return "instance", None


def project_of(kind: str, value: str | None, query_project: str = "") -> str | None:
    """The slug of the project a path-classified write is about, or None
    when the thing it names does not exist (the endpoint answers 404 for
    that; the middleware then applies the account's own role)."""
    from app.services import categories_store, pages_store, preview_links_store, projects_store

    if kind == "query":
        return query_project or None
    if kind == "project_slug":
        return value
    if value is None or not value.isdigit():
        return None
    number = int(value)
    project_id: int | None = None
    if kind == "project_id":
        project_id = number
    elif kind == "category":
        category = categories_store.get_category(number)
        project_id = category["project_id"] if category else None
    elif kind == "page":
        page = pages_store.get_page(number)
        project_id = page["project_id"] if page else None
    elif kind == "preview_link":
        link = preview_links_store.get(number)
        return link["project_slug"] if link else None
    if project_id is None:
        return None
    project = projects_store.get_project(project_id)
    return project["slug"] if project else None
