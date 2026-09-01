"""Read-only content endpoints for the public-facing site -- no
authentication (see auth_guard.py's unconditional /api/public/* exemption),
and every query here filters to published=True: an unpublished page must
never be reachable through this router by slug-guessing, only through the
admin endpoints."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.services import categories_store, content_assets, pages_store, projects_store

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/projects")
def public_list_projects():
    return {"projects": projects_store.list_projects()}


@router.get("/projects/{project_slug}")
def public_get_project(project_slug: str):
    project = projects_store.get_project_by_slug(project_slug)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    categories = categories_store.list_categories(project["id"])
    # Only categories that actually have at least one published page are
    # worth showing -- an empty category tile the admin hasn't filled in
    # yet would just be a dead end for a visitor.
    visible = []
    for c in categories:
        pages = pages_store.list_pages(c["id"], published_only=True)
        if pages:
            visible.append({**c, "page_count": len(pages)})
    return {"project": project, "categories": visible}


@router.get("/projects/{project_slug}/categories/{category_slug}")
def public_get_category(project_slug: str, category_slug: str):
    project = projects_store.get_project_by_slug(project_slug)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    category = categories_store.get_category_by_slug(project["id"], category_slug)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    pages = pages_store.list_pages(category["id"], published_only=True)
    return {
        "project": project,
        "category": category,
        "pages": [{"id": p["id"], "title": p["title"], "slug": p["slug"]} for p in pages],
    }


@router.get("/projects/{project_slug}/pages/{page_slug}")
def public_get_page(project_slug: str, page_slug: str):
    project = projects_store.get_project_by_slug(project_slug)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    page = pages_store.get_page_by_slug(project["id"], page_slug)
    if page is None or not page["published"]:
        raise HTTPException(status_code=404, detail="Page not found.")
    category = categories_store.get_category(page["category_id"])
    return {"project": project, "category": category, "page": page}


@router.get("/search")
def public_search(q: str = Query(..., min_length=1, max_length=200)):
    return {"results": pages_store.search(q)}


@router.get(
    "/assets/{project_slug}/{asset_path:path}",
    summary="Serve an image from a project's content directory",
    description="Images live in the content repo next to the Markdown that uses them (see the README's "
    "'Content repo structure'). `asset_path` is relative to the project's own directory -- the frontend "
    "resolves a page's relative Markdown src against the page's directory first, so `../assets/x.png` on a "
    "page arrives here as `assets/x.png`.",
)
def public_get_asset(project_slug: str, asset_path: str):
    """Unlike every other route in this router there's no published= filter,
    and that's deliberate: assets aren't secret, only PAGES are. Gating an
    image on whether some page happens to reference it from a draft would
    mean an author couldn't see their own image in the editor preview, while
    protecting nothing -- the file is already in the content repo, which is
    the thing anyone with repo access can read anyway."""
    path = content_assets.resolve_asset(project_slug, asset_path)
    if path is None:
        # One 404 for missing / wrong type / outside the project / no such
        # project -- a 403 on the traversal cases would confirm what's there.
        raise HTTPException(status_code=404, detail="Asset not found.")

    content_type = content_assets.content_type_for(path)
    headers = {
        "X-Content-Type-Options": "nosniff",
        # Not `immutable`: an author can replace an image under the same
        # filename in the next commit, and a visitor holding a year-long
        # cached copy would never see the corrected screenshot.
        "Cache-Control": "public, max-age=300",
    }
    if content_type == "image/svg+xml":
        # SVG is XML that can carry <script>/event handlers, and it's served
        # from this app's own origin. Uploads are screened for exactly that
        # (content_assets.rejection_reason), but a file committed straight
        # into the content repo by hand never passed through the uploader --
        # this header is what makes such a file inert regardless.
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"

    return FileResponse(path, media_type=content_type, headers=headers)
