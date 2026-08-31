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

While no admin account exists yet, every /api/ route other than the two
exempt prefixes above is blocked with 401 setup_required, forcing whoever
opens the instance first through setup (or an OIDC first-login bootstrap,
see routers/auth.py) before anything else works.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.services import auth_credentials_store, session_registry_store

_EXEMPT_PREFIXES = ("/api/auth/", "/api/public/")


class AuthGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if not path.startswith("/api/"):
            return await call_next(request)

        if path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        if not auth_credentials_store.is_configured():
            return JSONResponse({"detail": "setup_required"}, status_code=401)

        if not request.session.get("authenticated"):
            return JSONResponse({"detail": "not_authenticated"}, status_code=401)

        session_id = request.session.get("session_id")
        if not session_id or not session_registry_store.exists(session_id):
            return JSONResponse({"detail": "not_authenticated"}, status_code=401)
        session_registry_store.touch(session_id)

        return await call_next(request)
