"""Middleware requiring a logged-in admin session for everything under
/api/ EXCEPT two always-exempt prefixes:
- /api/auth/* -- the login/setup/OIDC flow itself, which obviously can't
  require already being logged in.
- /api/public/* -- read-only content endpoints the public-facing site
  uses (project/category/page listing, page content, search). No auth at
  all, and no partial "viewer role" concept like CachePanel has: v1 is
  single-admin-account, so there's nothing to be a viewer of *as* -- a
  visitor either edits (admin session) or reads (public endpoints), no
  third state.

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
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.services import api_tokens_store, auth_credentials_store, session_registry_store

_EXEMPT_PREFIXES = ("/api/auth/", "/api/public/")

# The only prefix an API token authorizes, and the only prefix that refuses
# a session. Kept as a constant so the two rules below can't drift apart.
_TOKEN_ONLY_PREFIX = "/api/mcp"

_BEARER = "bearer "


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

        if path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        if not auth_credentials_store.is_configured():
            return JSONResponse({"detail": "setup_required"}, status_code=401)

        # ---- API token path (before the session path, see the docstring) --
        credential = _bearer_credential(request)
        if credential is not None:
            if not path.startswith(_TOKEN_ONLY_PREFIX):
                return JSONResponse(
                    {
                        "detail": "An API token only authorizes the MCP endpoint at /api/mcp. The rest of the "
                        "admin API is reached with an admin session (a browser login).",
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
            request.state.api_token = record
            return await call_next(request)

        if path.startswith(_TOKEN_ONLY_PREFIX):
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
        session_registry_store.touch(session_id)

        return await call_next(request)
