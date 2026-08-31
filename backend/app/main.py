from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth_guard import AuthGuardMiddleware
from app.routers import admin_content, auth, public_content
from app.services import db, session_secret


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_schema()
    yield


app = FastAPI(
    title="ClarityDocs API",
    description="Self-hosted documentation CMS: multiple projects, each with categories and Markdown pages, "
    "edited through a browser UI and backed by a real database (SQLite by default, optional PostgreSQL). "
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
