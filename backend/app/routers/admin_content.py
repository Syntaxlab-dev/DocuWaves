"""CRUD for projects/categories/pages -- admin-only (guarded centrally by
AuthGuardMiddleware, this router doesn't sit under /api/public/ or
/api/auth/ so every route here already requires a valid session)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from slugify import slugify

from app.services import categories_store, pages_store, projects_store

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _unique_slug(base: str, taken_fn, *args) -> str:
    slug = slugify(base) or "item"
    candidate = slug
    n = 2
    while taken_fn(*args, candidate):
        candidate = f"{slug}-{n}"
        n += 1
    return candidate


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
def admin_create_project(body: ProjectIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    slug = _unique_slug(name, projects_store.slug_taken)
    project_id = projects_store.create_project(name, slug, body.icon.strip(), body.color.strip(), body.description.strip())
    return {"id": project_id, "slug": slug}


@router.put("/projects/{project_id}")
def admin_update_project(project_id: int, body: ProjectIn):
    project = projects_store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    slug = project["slug"] if name == project["name"] else _unique_slug(name, projects_store.slug_taken, project_id)
    projects_store.update_project(project_id, name, slug, body.icon.strip(), body.color.strip(), body.description.strip())
    return {"ok": True, "slug": slug}


@router.post("/projects/{project_id}/move")
def admin_move_project(project_id: int, direction: int):
    if direction not in (-1, 1):
        raise HTTPException(status_code=400, detail="direction must be -1 or 1.")
    projects_store.reorder_project(project_id, direction)
    return {"ok": True}


@router.delete("/projects/{project_id}")
def admin_delete_project(project_id: int):
    if projects_store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    projects_store.delete_project(project_id)
    return {"ok": True}


# ---- Categories ----


class CategoryIn(BaseModel):
    name: str
    icon: str = ""


@router.get("/projects/{project_id}/categories")
def admin_list_categories(project_id: int):
    return {"categories": categories_store.list_categories(project_id)}


@router.post("/projects/{project_id}/categories")
def admin_create_category(project_id: int, body: CategoryIn):
    if projects_store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    slug = _unique_slug(name, categories_store.slug_taken, project_id)
    category_id = categories_store.create_category(project_id, name, slug, body.icon.strip())
    return {"id": category_id, "slug": slug}


@router.put("/categories/{category_id}")
def admin_update_category(category_id: int, body: CategoryIn):
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
    categories_store.update_category(category_id, name, slug, body.icon.strip())
    return {"ok": True, "slug": slug}


@router.post("/categories/{category_id}/move")
def admin_move_category(category_id: int, direction: int):
    if direction not in (-1, 1):
        raise HTTPException(status_code=400, detail="direction must be -1 or 1.")
    category = categories_store.get_category(category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    categories_store.reorder_category(category["project_id"], category_id, direction)
    return {"ok": True}


@router.delete("/categories/{category_id}")
def admin_delete_category(category_id: int):
    if categories_store.get_category(category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    categories_store.delete_category(category_id)
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
def admin_create_page(body: PageIn):
    category = categories_store.get_category(body.category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")
    slug = _unique_slug(title, pages_store.slug_taken, category["project_id"])
    page_id = pages_store.create_page(category["project_id"], body.category_id, title, slug, body.markdown_content)
    return {"id": page_id, "slug": slug}


@router.put("/pages/{page_id}")
def admin_update_page(page_id: int, body: PageIn):
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
    pages_store.update_page(page_id, title, slug, body.markdown_content, body.category_id)
    return {"ok": True, "slug": slug}


@router.post("/pages/{page_id}/publish")
def admin_publish_page(page_id: int, published: bool):
    if pages_store.get_page(page_id) is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    pages_store.set_published(page_id, published)
    return {"ok": True}


@router.post("/pages/{page_id}/move")
def admin_move_page(page_id: int, direction: int):
    if direction not in (-1, 1):
        raise HTTPException(status_code=400, detail="direction must be -1 or 1.")
    page = pages_store.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    pages_store.reorder_page(page["category_id"], page_id, direction)
    return {"ok": True}


@router.delete("/pages/{page_id}")
def admin_delete_page(page_id: int):
    if pages_store.get_page(page_id) is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    pages_store.delete_page(page_id)
    return {"ok": True}
