"""Read-only content endpoints for the public-facing site -- no
authentication (see auth_guard.py's unconditional /api/public/* exemption),
and every query here filters to published=True: an unpublished page must
never be reachable through this router by slug-guessing, only through the
admin endpoints."""

from fastapi import APIRouter, HTTPException, Query

from app.services import categories_store, pages_store, projects_store

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
