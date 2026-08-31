import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth_guard import AuthGuardMiddleware
from app.routers import admin_content, auth, public_content
from app.services import content_sync, db, git_content_repo, session_secret
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
            content_sync.full_sync()
        except git_content_repo.GitContentError as exc:
            # Doesn't prevent startup -- the admin UI's connection status
            # panel surfaces this instead of the app refusing to boot over
            # what might just be a transient network issue.
            log.warning("Initial content repo sync failed: %s", exc)
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

app.include_router(auth.router)
app.include_router(admin_content.router)
app.include_router(public_content.router)


@app.get("/health", summary="Health check", description="Confirms the database is reachable -- used by Docker's own HEALTHCHECK.")
def health():
    with db.get_connection() as conn:
        conn.execute("SELECT 1")
    return {"ok": True}

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "static"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
