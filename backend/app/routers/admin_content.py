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

from app.services import (
    categories_store,
    content_assets,
    content_sync,
    git_content_repo,
    pages_store,
    projects_store,
    site_branding,
)

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


# ---- Image assets ----
#
# Keyed by project SLUG, not by the numeric id every route above uses: an
# asset has no database row of its own (it's a plain file, not something the
# search index has any use for), so the slug -- which IS its directory name
# on disk and the path segment in its public URL -- is the only identifier
# these three endpoints need to look anything up.


def _asset_project(project_slug: str) -> dict:
    project = projects_store.get_project_by_slug(project_slug)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _asset_info(project_slug: str, filename: str, size: int) -> dict:
    return {
        "filename": filename,
        "size": size,
        "markdown_path": content_assets.markdown_path(filename),
        "url": content_assets.public_url(project_slug, filename),
    }


async def _read_capped_body(request: Request) -> bytes | None:
    """None = the upload went past the size limit. Read chunk by chunk and
    bail at the limit rather than `await request.body()`, which would buffer
    a deliberately huge upload in full before anything got the chance to
    reject it."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > content_assets.MAX_ASSET_BYTES:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


async def _read_validated_image(request: Request, filename: str) -> bytes:
    """Body bytes of an image upload, size-capped and content-checked, or the
    right HTTPException. Shared by the project uploader and the branding
    uploader further down so a logo goes through the identical extension +
    magic-number + SVG-script screening a page's screenshot does."""
    data = await _read_capped_body(request)
    if data is None:
        raise HTTPException(
            status_code=413,
            detail=f"That image is larger than the {content_assets.MAX_ASSET_BYTES // (1024 * 1024)} MB limit.",
        )
    reason = content_assets.rejection_reason(filename, data)
    if reason is not None:
        raise HTTPException(status_code=400, detail=reason)
    return data


@router.get(
    "/projects/{project_slug}/assets",
    summary="List a project's images",
    description="Everything under content/<project-slug>/assets/, with the relative path to paste into a page.",
)
def admin_list_assets(project_slug: str):
    _asset_project(project_slug)
    return {
        "assets": [_asset_info(project_slug, a["filename"], a["size"]) for a in content_assets.list_assets(project_slug)]
    }


@router.post(
    "/projects/{project_slug}/assets",
    summary="Upload an image into a project",
    description="The request BODY is the raw image bytes (not a multipart form -- parsing multipart would mean "
    "adding python-multipart to requirements.txt, and a single-file upload doesn't need it); `filename` is a "
    "query parameter. The stem is slugified and the real extension kept; an existing name gets -2, -3, ... "
    "rather than being overwritten. Max 10 MB, and the bytes themselves are checked against the extension.",
)
async def admin_upload_asset(project_slug: str, filename: str, request: Request):
    _require_content_repo()
    project = _asset_project(project_slug)

    data = await _read_validated_image(request, filename)

    stored_name = content_assets.unique_filename(project_slug, filename)
    path = content_assets.write_asset(project_slug, stored_name, data)
    try:
        git_content_repo.commit_and_push([path], f"Add image: {stored_name} ({project['name']})", _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return _asset_info(project_slug, stored_name, len(data))


@router.delete(
    "/projects/{project_slug}/assets/{filename}",
    summary="Delete a project's image",
    description="Removes the file and commits the deletion. Pages still referencing it are left alone -- the "
    "image just stops rendering, which is visible in the editor preview, rather than the delete silently "
    "rewriting someone's Markdown.",
)
def admin_delete_asset(project_slug: str, filename: str, request: Request):
    _require_content_repo()
    project = _asset_project(project_slug)
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        # A bare filename inside the project's own assets/ folder is the only
        # thing this endpoint ever addresses; anything path-shaped is a
        # traversal attempt, not a typo worth guessing at.
        raise HTTPException(status_code=400, detail="A filename can't contain a path separator.")

    paths = content_assets.delete_asset(project_slug, filename)
    if not paths:
        raise HTTPException(status_code=404, detail="Asset not found.")
    try:
        git_content_repo.commit_and_push(paths, f"Remove image: {filename} ({project['name']})", _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


# ---- Site branding ----
#
# Instance-level, so nothing here is keyed by a project at all: it edits
# content/_site.yml and content/_site/ at the top of the content repo (see
# services/site_branding.py for why branding lives in the repo rather than in
# a database row). Writes commit and push exactly like every other admin
# write above; there is no content_sync.full_sync() call because branding has
# no database index to rebuild -- the file IS the state, read on each request.


class FooterLinkIn(BaseModel):
    label: str = ""
    url: str = ""


class SiteBrandingIn(BaseModel):
    name: str = ""
    tagline: str = ""
    # Filenames inside _site/, put there by the upload endpoint below -- an
    # unknown or path-shaped name simply resolves to no URL when read back
    # (site_branding._asset_field), it can never point outside the folder.
    logo: str = ""
    logo_dark: str = ""
    favicon: str = ""
    accent: str = ""
    footer_text: str = ""
    footer_links: list[FooterLinkIn] = []


@router.get(
    "/site",
    summary="This instance's branding, for the admin form",
    description="The same resolved values GET /api/public/site returns, including the raw configured "
    "filenames so the form can show which logo/favicon is currently selected.",
)
def admin_get_site():
    return site_branding.read_branding()


@router.put(
    "/site",
    summary="Save this instance's branding",
    description="Writes content/_site.yml, then commits and pushes it. Values are normalized on the way in "
    "with the same validators reading uses: a colour that isn't #rgb/#rrggbb and a footer link that isn't "
    "http(s)/mailto/site-relative are dropped rather than stored. Returns the branding as it now reads back.",
)
def admin_update_site(body: SiteBrandingIn, request: Request):
    _require_content_repo()
    paths = site_branding.write_branding(body.model_dump())
    try:
        git_content_repo.commit_and_push(paths, "Update site branding", _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return site_branding.read_branding()


@router.post(
    "/site/assets",
    summary="Upload a branding image (logo, dark logo or favicon)",
    description="Raw image bytes as the request BODY, `filename` as a query parameter -- same contract, same "
    "size limit and same content validation as a project's image upload. Stored in content/_site/ under a "
    "slugified, never-overwriting name and committed. Saving the branding form afterwards is what points "
    "_site.yml at the new file.",
)
async def admin_upload_site_asset(filename: str, request: Request):
    _require_content_repo()
    data = await _read_validated_image(request, filename)

    stored_name = site_branding.unique_asset_filename(filename)
    path = site_branding.write_site_asset(stored_name, data)
    try:
        git_content_repo.commit_and_push([path], f"Add branding image: {stored_name}", _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"filename": stored_name, "size": len(data), "url": site_branding.asset_url(stored_name)}
