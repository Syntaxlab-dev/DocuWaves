"""CRUD for projects/categories/pages -- admin-only (guarded centrally by
AuthGuardMiddleware, this router doesn't sit under /api/public/ or
/api/auth/ so every route here already requires a valid session).

Every mutating endpoint requires the content repo to be configured (see
_require_content_repo()) -- checked BEFORE any file is written, so an
unconfigured instance never leaves an orphan file on disk that never made
it into a commit. GitContentError from a write's git_content_repo call
(push rejected/conflicted after the file was already written+committed
locally) surfaces as 409, everything else content-repo-related as 400."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slugify import slugify

from app.services import categories_store, content_sync, git_content_repo, pages_store, projects_store

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _author(request: Request) -> str:
    return request.session.get("username") or "admin"


def _require_content_repo() -> None:
    if not git_content_repo.is_configured():
        raise HTTPException(
            status_code=400,
            detail="No content repo is configured (CONTENT_REPO_URL is not set) -- see the README for setup.",
        )


def _unique_slug(base: str, taken_fn, *args) -> str:
    slug = slugify(base) or "item"
    candidate = slug
    n = 2
    while taken_fn(*args, candidate):
        candidate = f"{slug}-{n}"
        n += 1
    return candidate


def _git_error_response(exc: git_content_repo.GitContentError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


# ---- Content repo status ----


@router.get(
    "/content-repo/status",
    summary="Content repo connection status",
    description="Whether a content repo is configured, currently reachable, and its last synced commit -- "
    "for the admin UI's connection banner. Never raises: a connection problem is shown here, not thrown.",
)
def admin_content_repo_status():
    return git_content_repo.status()


@router.post(
    "/content-repo/sync",
    summary="Pull the content repo and reindex",
    description="Fetches the latest commits from the content repo's remote (e.g. a community pull request "
    "that just got merged) and rebuilds the projects/categories/pages database index from what's now on "
    "disk. Safe to call any time; also runs automatically on a timer, see CONTENT_REPO_SYNC_INTERVAL_SECONDS.",
)
def admin_content_repo_sync():
    _require_content_repo()
    try:
        git_content_repo.sync_pull()
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    content_sync.full_sync()
    return {"ok": True}


# ---- Projects ----


class ProjectIn(BaseModel):
    name: str
    icon: str = ""
    color: str = ""
    description: str = ""


@router.get("/projects")
def admin_list_projects():
    return {"projects": projects_store.list_projects()}


@router.post("/projects")
def admin_create_project(body: ProjectIn, request: Request):
    _require_content_repo()
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    slug = _unique_slug(name, projects_store.slug_taken)
    try:
        project = projects_store.create_project(name, slug, body.icon.strip(), body.color.strip(), body.description.strip(), _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"id": project["id"], "slug": project["slug"]}


@router.put("/projects/{project_id}")
def admin_update_project(project_id: int, body: ProjectIn, request: Request):
    _require_content_repo()
    project = projects_store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    slug = project["slug"] if name == project["name"] else _unique_slug(name, projects_store.slug_taken, project_id)
    try:
        updated = projects_store.update_project(project_id, name, slug, body.icon.strip(), body.color.strip(), body.description.strip(), _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True, "slug": updated["slug"] if updated else slug}


@router.post("/projects/{project_id}/move")
def admin_move_project(project_id: int, direction: int, request: Request):
    _require_content_repo()
    if direction not in (-1, 1):
        raise HTTPException(status_code=400, detail="direction must be -1 or 1.")
    try:
        projects_store.reorder_project(project_id, direction, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


@router.delete("/projects/{project_id}")
def admin_delete_project(project_id: int, request: Request):
    _require_content_repo()
    if projects_store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    try:
        projects_store.delete_project(project_id, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


# ---- Categories ----


class CategoryIn(BaseModel):
    name: str
    icon: str = ""


@router.get("/projects/{project_id}/categories")
def admin_list_categories(project_id: int):
    return {"categories": categories_store.list_categories(project_id)}


@router.post("/projects/{project_id}/categories")
def admin_create_category(project_id: int, body: CategoryIn, request: Request):
    _require_content_repo()
    if projects_store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    slug = _unique_slug(name, categories_store.slug_taken, project_id)
    try:
        category = categories_store.create_category(project_id, name, slug, body.icon.strip(), _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"id": category["id"], "slug": category["slug"]}


@router.put("/categories/{category_id}")
def admin_update_category(category_id: int, body: CategoryIn, request: Request):
    _require_content_repo()
    category = categories_store.get_category(category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    slug = (
        category["slug"]
        if name == category["name"]
        else _unique_slug(name, categories_store.slug_taken, category["project_id"], category_id)
    )
    try:
        updated = categories_store.update_category(category_id, name, slug, body.icon.strip(), _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True, "slug": updated["slug"] if updated else slug}


@router.post("/categories/{category_id}/move")
def admin_move_category(category_id: int, direction: int, request: Request):
    _require_content_repo()
    if direction not in (-1, 1):
        raise HTTPException(status_code=400, detail="direction must be -1 or 1.")
    category = categories_store.get_category(category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    try:
        categories_store.reorder_category(category["project_id"], category_id, direction, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


@router.delete("/categories/{category_id}")
def admin_delete_category(category_id: int, request: Request):
    _require_content_repo()
    if categories_store.get_category(category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    try:
        categories_store.delete_category(category_id, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


# ---- Pages ----


class PageIn(BaseModel):
    title: str
    markdown_content: str = ""
    category_id: int


@router.get("/categories/{category_id}/pages")
def admin_list_pages(category_id: int):
    return {"pages": pages_store.list_pages(category_id)}


@router.get("/pages/{page_id}")
def admin_get_page(page_id: int):
    page = pages_store.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    return page


@router.post("/pages")
def admin_create_page(body: PageIn, request: Request):
    _require_content_repo()
    category = categories_store.get_category(body.category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")
    slug = _unique_slug(title, pages_store.slug_taken, category["project_id"])
    try:
        page = pages_store.create_page(category["project_id"], body.category_id, title, slug, body.markdown_content, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"id": page["id"], "slug": page["slug"]}


@router.put("/pages/{page_id}")
def admin_update_page(page_id: int, body: PageIn, request: Request):
    _require_content_repo()
    page = pages_store.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    category = categories_store.get_category(body.category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")
    slug = (
        page["slug"]
        if title == page["title"]
        else _unique_slug(title, pages_store.slug_taken, page["project_id"], page_id)
    )
    try:
        updated = pages_store.update_page(page_id, title, slug, body.markdown_content, body.category_id, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True, "slug": updated["slug"] if updated else slug}


@router.post("/pages/{page_id}/publish")
def admin_publish_page(page_id: int, published: bool, request: Request):
    _require_content_repo()
    if pages_store.get_page(page_id) is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    try:
        pages_store.set_published(page_id, published, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


@router.post("/pages/{page_id}/move")
def admin_move_page(page_id: int, direction: int, request: Request):
    _require_content_repo()
    if direction not in (-1, 1):
        raise HTTPException(status_code=400, detail="direction must be -1 or 1.")
    page = pages_store.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    try:
        pages_store.reorder_page(page["category_id"], page_id, direction, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


@router.delete("/pages/{page_id}")
def admin_delete_page(page_id: int, request: Request):
    _require_content_repo()
    if pages_store.get_page(page_id) is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    try:
        pages_store.delete_page(page_id, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}
