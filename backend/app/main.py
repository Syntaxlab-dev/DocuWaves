import asyncio
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth_guard import AuthGuardMiddleware
from app.routers import admin_content, api_tokens, auth, mcp, public_content
from app.services import content_sync, content_versions, db, git_content_repo, session_secret
from app.settings import settings

log = logging.getLogger("docuwaves")


async def _periodic_content_sync() -> None:
    """Background loop: pulls the content repo and reindexes on a timer, so
    a merged community pull request shows up without anyone having to press
    'Sync now' -- see CONTENT_REPO_SYNC_INTERVAL_SECONDS. Runs forever until
    the app shuts down (see lifespan's task.cancel() below); a single failed
    sync (network blip, transient conflict) just gets logged and retried
    next interval, never crashes the app."""
    while True:
        await asyncio.sleep(settings.content_repo_sync_interval_seconds)
        try:
            git_content_repo.sync_pull()
            content_sync.full_sync()
        except git_content_repo.GitContentError as exc:
            log.warning("Periodic content repo sync failed: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_schema()
    sync_task: asyncio.Task | None = None
    if git_content_repo.is_configured():
        try:
            git_content_repo.ensure_clone()
            # Pull before indexing. ensure_clone() only clones when the
            # working copy is missing; on every restart after the first it
            # reuses what's already on disk, so without this the index was
            # rebuilt from a checkout that could be days old and commits
            # pushed while the container was down stayed invisible until
            # the first periodic sync or a manual "Sync now".
            git_content_repo.sync_pull()
        except git_content_repo.GitContentError as exc:
            # Doesn't prevent startup -- the admin UI's connection status
            # panel surfaces this instead of the app refusing to boot over
            # what might just be a transient network issue.
            log.warning("Initial content repo sync failed: %s", exc)
        # Reindex from the working clone on disk whether or not the pull
        # above got through: the clone lives on the same persistent volume
        # as the index, so its files are there either way -- and after
        # db.init_schema() has rebuilt the content tables for a new schema
        # (see db.py) this is the call that fills them again, which must not
        # hinge on the network being up at that moment. full_sync() itself
        # no-ops when there is no checkout at all, so a failed FIRST clone
        # still can't empty anything.
        try:
            content_sync.full_sync()
        except Exception:
            # Deliberately broad, and deliberately not fatal. Whatever the
            # index makes of the files, one committed file must never be able
            # to stop the application from starting -- a duplicate page slug
            # used to raise straight out of here and the container exited,
            # taking the public site down with no way in to see why. Coming
            # up with a stale or partial index and a logged reason leaves the
            # admin area reachable, which is where the operator fixes it.
            log.exception("Initial content index failed; starting with whatever the index already holds")
        sync_task = asyncio.create_task(_periodic_content_sync())
    yield
    if sync_task is not None:
        sync_task.cancel()


app = FastAPI(
    title="DocuWaves API",
    description="Self-hosted documentation CMS: multiple projects, each with categories and Markdown pages. "
    "Content lives as Markdown+YAML files in a connected Git repo (so a community can contribute via pull "
    "request too); edited through a browser UI that commits and pushes on save. The database (SQLite by "
    "default, optional PostgreSQL) is just a rebuildable search/browse index over those files. "
    "Interactive docs at /docs.",
    lifespan=lifespan,
)

# Middleware order: Starlette wraps the LAST-added middleware as the
# OUTERMOST layer. SessionMiddleware must run before AuthGuardMiddleware so
# request.session is populated by the time the guard reads it -- so
# AuthGuardMiddleware is added first (innermost), SessionMiddleware second.
app.add_middleware(AuthGuardMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret.get_or_create_secret(),
    max_age=30 * 24 * 3600,
    same_site="lax",
    https_only=False,  # typically sits behind a reverse proxy or is hit directly over plain HTTP on a LAN
)


@app.exception_handler(content_versions.FrozenVersionError)
def _frozen_version_handler(_request: Request, exc: content_versions.FrozenVersionError) -> JSONResponse:
    """A write aimed at a frozen documentation version, refused. Registered
    centrally rather than caught in each admin route so that EVERY write
    path is covered by construction -- including one added later that
    forgets to wrap its store call -- and so the reason the store raised
    (which names the version and the file to edit instead) is what the
    caller actually reads. 403 rather than 409: nothing conflicted, this
    version is simply read-only. `detail` matches the shape every other
    error in this API uses, so the frontend's own error handling shows it
    without a special case."""
    return JSONResponse(status_code=403, content={"detail": str(exc)})


app.include_router(auth.router)
app.include_router(admin_content.router)
app.include_router(api_tokens.router)
# Before the catch-all SPA route below, like every other router -- and after
# the admin ones, so /api/admin/tokens is matched by its own router rather
# than by anything more general.
app.include_router(mcp.router)
app.include_router(public_content.router)


@app.get("/health", summary="Health check", description="Confirms the database is reachable -- used by Docker's own HEALTHCHECK.")
def health():
    with db.get_connection() as conn:
        conn.execute("SELECT 1")
    return {"ok": True}

# Resolved (not just absolute): serve_spa below compares it against a resolved
# candidate path, so a symlinked bundle directory would otherwise never match.
FRONTEND_DIST = (Path(__file__).resolve().parent.parent / "static").resolve()

class _ImmutableStatic(StaticFiles):
    """The bundle's filenames contain a content hash (index-DEpV2D4Z.js), so a
    changed file is a changed URL and an old one can be kept forever."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = _IMMUTABLE_CACHE
        return response


_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"

# A named set of extensions rather than "anything that looks like a file":
# a documentation version is part of the URL and its id routinely contains a
# dot (/p/cachepanel/v2.0), so a general rule would 404 a real page. These
# are extensions a client-side route never ends in -- server languages and
# config files nobody here serves (what the scanners ask for), plus the
# static types a browser requests on its own and should be told plainly do
# not exist instead of being handed HTML.
_SCANNABLE_FILE = re.compile(
    r"\.(php\d?|asp|aspx|jsp|cgi|pl|sh|bash|exe|dll|env|sql|bak|old|swp|ini|conf|cfg|log|"
    r"git|zip|tar|gz|rar|7z|xml|png|jpe?g|gif|ico|svg|webp|avif|woff2?|ttf|map)$",
    re.IGNORECASE,
)

if FRONTEND_DIST.exists():
    app.mount("/assets", _ImmutableStatic(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # full_path is whatever the client asked for, so it has to be contained
        # to the bundle directory before it is ever handed to FileResponse.
        # Without this, `GET /../../data/content-repo/.git/config` walked
        # straight out of the bundle and returned the content repo's push
        # token (git_content_repo embeds it in the clone's origin URL), the
        # SQLite index with the admin password hash, and the session secret --
        # unauthenticated. Resolve both sides and compare the resolved paths;
        # a prefix check on the unresolved path would still be fooled by a
        # symlink inside the bundle pointing outward.
        # An /api/ path that reached this catch-all matched no router, so it
        # is a wrong URL, not a client-side route. Returning the SPA shell
        # with a 200 hands an API caller HTML where it expects JSON, and the
        # status code says it worked -- a typo'd endpoint then looks like an
        # empty success rather than a mistake.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")

        candidate = (FRONTEND_DIST / full_path).resolve()
        index = FRONTEND_DIST / "index.html"
        if full_path and candidate.is_relative_to(FRONTEND_DIST) and candidate.is_file():
            return FileResponse(candidate)

        # A reader's URL is a client-side route and has no file extension
        # (/p/cachepanel/pages/installation). A request for a FILE that the
        # bundle does not contain is either a browser asking for something
        # optional (favicon.png) or a scanner walking a list -- wp-login.php,
        # wlwmanifest.xml, and twenty variations. Answering those with the SPA
        # shell and a 200 tells the scanner it found something, so it keeps
        # going, and hands a browser HTML where it asked for an image.
        if _SCANNABLE_FILE.search(full_path):
            raise HTTPException(status_code=404, detail="Not found.")

        # Anything else is a client-side route (or an escape attempt): hand back
        # the SPA shell and let the router decide, exactly as before.
        #
        # no-cache (revalidate, not "never store"): index.html names the
        # content-hashed bundle, so a stale copy of THIS file pins a browser
        # to the previous release -- an operator who deploys an update keeps
        # seeing the old UI and reasonably concludes the deploy did nothing.
        # FileResponse answers a revalidation with the whole file rather than
        # a 304 (only StaticFiles handles If-None-Match) -- fine at a few KB,
        # and the big hashed bundle it points at is cached forever anyway.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
