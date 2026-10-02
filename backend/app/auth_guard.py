"""Middleware requiring a logged-in admin session for everything under
/api/ EXCEPT two always-exempt prefixes:
- /api/auth/* -- the login/setup/OIDC flow itself, which obviously can't
  require already being logged in.
- /api/public/* -- read-only content endpoints the public-facing site
  uses (project/category/page listing, page content, search). No auth at
  all: the documentation is public, so a visitor either edits (a session)
  or reads (these endpoints).

...plus ONE non-browser credential: an API token, presented as
`Authorization: Bearer dwt_...` (see services/api_tokens_store.py). It is
checked BEFORE the session path, because a request carrying one is by
definition not a browser session and running the session checks first would
answer "not_authenticated" to a perfectly valid token. A token authorizes
exactly one prefix, /api/mcp -- and /api/mcp accepts nothing else:

- A token on any other /api/ route is refused, with the reason. The token
  scopes ('read'/'write') describe documentation, not the admin API: a
  `read` token that could reach /api/admin/* would be able to delete a
  project, which is exactly the shape of authority this whole feature is
  built to withhold.
- A browser SESSION on /api/mcp is refused too. The MCP endpoint is the
  interface an assistant sees, and every one of its answers depends on the
  caller's scope -- a session has no scope, so "the admin is logged in"
  would have to mean either read or write, and both are wrong answers to a
  question nobody asked. There is deliberately no anonymous access and no
  second way in.

An expired or revoked token is rejected exactly like an absent one (see
api_tokens_store.verify): a caller holding a stolen token learns nothing
about whether it ever worked. A token value is never logged, and never put
into an error message.

While no admin account exists yet, every /api/ route other than the two
exempt prefixes above is blocked with 401 setup_required, forcing whoever
opens the instance first through setup (or an OIDC first-login bootstrap,
see routers/auth.py) before anything else works -- API tokens included,
since there is nobody to have created one yet.

---- ROLES ----

A session's account is one of viewer / editor / admin (see
services/users_store.py). What each may do is decided HERE, in the
middleware, and not endpoint by endpoint. That is the whole design:

- The write rule is the HTTP METHOD. GET and HEAD are reading; everything
  else changes something. So a viewer is "GET and HEAD only", stated once,
  and an endpoint added next year is covered by it before anyone remembers
  to think about roles. A per-endpoint decorator would be a list that has to
  stay complete, and the failure mode of an incomplete list is an unguarded
  write.
- The admin rule is a short list of PREFIXES, because those really are
  specific: accounts, API tokens, branding, diagnostics and the export.
  Every one of them is a different kind of authority from "may edit the
  documentation" -- handing out a credential, changing what the site claims
  to be, and downloading the whole instance are not editing.

The role is read from the DATABASE on every request rather than from the
session cookie. It costs one indexed lookup and it means a role that was
taken away is taken away NOW, for sessions that are already open -- rather
than whenever the person happens to log in again. An account that has been
deleted while logged in fails the same lookup and is signed out.
"""

import re

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.services import api_tokens_store, session_registry_store, users_store
from app.services.same_origin import is_same_origin

_EXEMPT_PREFIXES = ("/api/auth/", "/api/public/")

# The only prefix an API token authorizes, and the only prefix that refuses
# a session. Kept as a constant so the two rules below can't drift apart.
_TOKEN_ONLY_PREFIX = "/api/mcp"
# Docs-as-code (services/docs_sync.py): token-only too, and only for a SYNC
# token -- which in turn opens nothing else.
_SYNC_PREFIX = "/api/sync/"
_TOKEN_PREFIXES = (_TOKEN_ONLY_PREFIX, _SYNC_PREFIX)

_BEARER = "bearer "

# Reading. Everything else is a change, and a viewer may not make one.
_READ_METHODS = ("GET", "HEAD")

# The two changes a read-only account MAY make: deciding on a page somebody
# submitted for approval. Reviewing is reading -- often the people best
# placed to check a text are the ones who should not be editing it -- and
# the decision changes no word of it (services/page_review.py).
_REVIEW_DECISION_RE = re.compile(r"^/api/admin/pages/\d+/review/(approve|request-changes)$")

# Prefixes only an admin may touch, by ANY method -- a viewer's GET included.
# Each one is authority over the instance rather than over its documentation:
#
#   users        -- creating accounts and handing out roles
#   tokens       -- creating a credential that writes through the MCP endpoint
#   site         -- the branding: what this instance claims to be
#   diagnostics  -- paths, disk, counts; harmless to an admin, not an
#                   editor's business
#   export       -- the entire instance in one downloadable file
_ADMIN_ONLY_PREFIXES = (
    "/api/admin/users",
    "/api/admin/tokens",
    "/api/admin/site",
    "/api/admin/diagnostics",
    "/api/admin/export",
)


def _bearer_credential(request: Request) -> str | None:
    """The credential from an `Authorization: Bearer ...` header, or None
    when the header is absent or is some other scheme entirely (Basic, a
    proxy's own header) -- which is not this middleware's business and falls
    through to the session path untouched."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith(_BEARER):
        return None
    return header[len(_BEARER):].strip()


class AuthGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if not path.startswith("/api/"):
            return await call_next(request)

        if path.startswith("/api/public/"):
            response = await call_next(request)
            # A signed-in reader may be shown PRIVATE projects
            # (services/visibility.py), so the same URL answers differently
            # per person: never store a signed-in answer anywhere shared, and
            # tell every cache the answer depends on the cookie.
            if request.session.get("authenticated"):
                response.headers["Cache-Control"] = "private, no-store"
            # With a session, Starlette's SessionMiddleware (the outer layer)
            # adds `Vary: Cookie` itself on the way out; without one, nothing
            # would -- and the anonymous answer is exactly the one a shared
            # cache must not hand to a signed-in reader.
            vary = response.headers.get("Vary", "")
            if not request.session and "cookie" not in vary.lower():
                response.headers["Vary"] = f"{vary}, Cookie" if vary else "Cookie"
            return response

        if path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        # The checks below read (and, for the session's last-seen time, write)
        # the database. Run in the thread pool: done on the event loop, every
        # admin request serialised the whole process behind its queries, and
        # a reindex holding the database made the public site wait too.
        refusal = await run_in_threadpool(self._refusal, request, path)
        if refusal is not None:
            return refusal
        return await call_next(request)

    def _refusal(self, request: Request, path: str) -> Response | None:
        """The response that refuses this request, or None to let it through."""
        if not users_store.is_configured():
            return JSONResponse({"detail": "setup_required"}, status_code=401)

        # ---- API token path (before the session path, see the docstring) --
        credential = _bearer_credential(request)
        if credential is not None:
            if not path.startswith(_TOKEN_PREFIXES):
                return JSONResponse(
                    {
                        "detail": "An API token only authorizes the MCP endpoint at /api/mcp (and a sync token "
                        "/api/sync/). The rest of the admin API is reached with an admin session (a browser login).",
                    },
                    status_code=403,
                )
            # Rate limit BEFORE the database lookup, so a client already
            # over its limit costs one dict lookup rather than a full scan
            # of the token table on every one of its retries.
            if api_tokens_store.rate_limited(credential):
                return JSONResponse(
                    {"detail": f"Rate limit exceeded ({api_tokens_store.rate_limit_description()}). Slow down."},
                    status_code=429,
                )
            record = api_tokens_store.verify(credential)
            if record is None:
                # One answer for unknown / revoked / expired, deliberately.
                return JSONResponse({"detail": "invalid_token"}, status_code=401)
            # The record (name and scope, never the value) travels on the
            # request's own scope so the MCP router can decide what this
            # token may do without looking the header up a second time.
            # A sync token syncs and does nothing else; a read/write token
            # never syncs. Checked here, once, for both directions.
            if (record["scope"] == api_tokens_store.SYNC_SCOPE) != path.startswith(_SYNC_PREFIX):
                return JSONResponse(
                    {"detail": "This token is not for this endpoint: a sync token only works on /api/sync/<project>, "
                     "and only a sync token does."},
                    status_code=403,
                )
            request.state.api_token = record
            return None

        if path.startswith(_TOKEN_PREFIXES):
            return JSONResponse(
                {
                    "detail": "This endpoint requires an API token: send 'Authorization: Bearer dwt_...'. "
                    "Create one under 'API tokens' in the admin area.",
                },
                status_code=401,
            )

        # ---- Admin session path (unchanged) ----
        if not request.session.get("authenticated"):
            return JSONResponse({"detail": "not_authenticated"}, status_code=401)

        session_id = request.session.get("session_id")
        if not session_id or not session_registry_store.exists(session_id):
            return JSONResponse({"detail": "not_authenticated"}, status_code=401)

        # The account behind the session, looked up now rather than trusted
        # from the cookie -- see the docstring. Gone means the account was
        # deleted while this session was open: the session goes with it,
        # here, rather than being left to expire.
        user = users_store.get_user(request.session.get("username") or "")
        if user is None:
            session_registry_store.revoke(session_id)
            return JSONResponse({"detail": "not_authenticated"}, status_code=401)

        session_registry_store.touch(session_id)
        # A cookie-authenticated change must come from this site's own pages;
        # see services/same_origin.py. Only the session path: a bearer token
        # is sent deliberately by its holder, never ambiently by a browser.
        if request.method not in _READ_METHODS and not is_same_origin(request):
            return JSONResponse({"detail": "cross_site_request"}, status_code=403)
        role = user["role"]
        # On the request, so an endpoint that needs to say something
        # role-dependent (who am I, may I see this) reads it rather than
        # looking it up a second time.
        request.state.user = user

        # A reader account reads private projects on the public site and
        # nothing else; the admin API (drafts, history, reports) is closed to
        # it entirely. /api/auth/ -- who am I, sign out, change my password --
        # is exempt above and so stays open.
        if path.startswith("/api/admin") and not users_store.may_open_admin(role):
            return JSONResponse({"detail": "reader_account"}, status_code=403)
        if path.startswith(_ADMIN_ONLY_PREFIXES) and not users_store.is_admin(role):
            return JSONResponse(
                {"detail": "This part of the admin area is for administrators."},
                status_code=403,
            )
        reviewing = request.method == "POST" and _REVIEW_DECISION_RE.match(path) is not None
        if request.method not in _READ_METHODS and not users_store.may_write(role) and not reviewing:
            return JSONResponse(
                {"detail": "Your account can read the admin area but not change anything."},
                status_code=403,
            )

        return None
