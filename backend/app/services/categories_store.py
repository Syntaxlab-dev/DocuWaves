"""Categories group pages within one project -- the "tile" navigation level
between a project's landing page and its individual pages. Slugs are unique
per project (not globally), enforced by the DB's own UNIQUE(project_id,
slug) constraint -- matching the filesystem's own directory-naming
uniqueness inside one project's folder.

Reads unchanged (DB index, kept current by content_sync.py); writes go
through content_files.py + git_content_repo.py, see projects_store.py's own
docstring for the full reasoning, identical here."""

from app.services import content_files, content_sync, db, git_content_repo, projects_store

_COLUMNS = "id, project_id, name, slug, icon, sort_order"


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "project_id": row[1],
        "name": row[2],
        "slug": row[3],
        "icon": row[4],
        "sort_order": row[5],
    }


def list_categories(project_id: int) -> list[dict]:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM categories WHERE project_id = {placeholder} ORDER BY sort_order, name",
            (project_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_category(category_id: int) -> dict | None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM categories WHERE id = {placeholder}", (category_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_category_by_slug(project_id: int, slug: str) -> dict | None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM categories WHERE project_id = {placeholder} AND slug = {placeholder}",
            (project_id, slug),
        ).fetchone()
    return _row_to_dict(row) if row else None


def slug_taken(project_id: int, slug: str, exclude_id: int | None = None) -> bool:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        if exclude_id is not None:
            row = conn.execute(
                f"SELECT 1 FROM categories WHERE project_id = {placeholder} AND slug = {placeholder} AND id != {placeholder}",
                (project_id, slug, exclude_id),
            ).fetchone()
        else:
            row = conn.execute(
                f"SELECT 1 FROM categories WHERE project_id = {placeholder} AND slug = {placeholder}",
                (project_id, slug),
            ).fetchone()
    return row is not None


def _next_order(project_id: int) -> int:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT COALESCE(MAX(sort_order), -1) + 1 FROM categories WHERE project_id = {placeholder}",
            (project_id,),
        ).fetchone()
    return row[0]


def create_category(project_id: int, name: str, slug: str, icon: str, author: str) -> dict | None:
    project = projects_store.get_project(project_id)
    if project is None:
        return None
    order = _next_order(project_id)
    paths = content_files.write_category(project["slug"], slug, name, icon, order)
    git_content_repo.commit_and_push(paths, f"Add category: {name} ({project['name']})", author)
    content_sync.full_sync()
    return get_category_by_slug(project_id, slug)


def update_category(category_id: int, name: str, slug: str, icon: str, author: str) -> dict | None:
    current = get_category(category_id)
    if current is None:
        return None
    project = projects_store.get_project(current["project_id"])
    paths: list[str] = []
    if slug != current["slug"]:
        paths += content_files.rename_category(project["slug"], current["slug"], slug)
    paths += content_files.write_category(project["slug"], slug, name, icon, current["sort_order"])
    git_content_repo.commit_and_push(paths, f"Update category: {name} ({project['name']})", author)
    content_sync.full_sync()
    return get_category_by_slug(current["project_id"], slug)


def reorder_category(project_id: int, category_id: int, direction: int, author: str) -> None:
    categories = list_categories(project_id)
    index = next((i for i, c in enumerate(categories) if c["id"] == category_id), None)
    if index is None:
        return
    swap_index = index + direction
    if not (0 <= swap_index < len(categories)):
        return
    a, b = categories[index], categories[swap_index]
    project = projects_store.get_project(project_id)
    paths = content_files.write_category(project["slug"], a["slug"], a["name"], a["icon"], b["sort_order"])
    paths += content_files.write_category(project["slug"], b["slug"], b["name"], b["icon"], a["sort_order"])
    git_content_repo.commit_and_push(paths, f"Reorder categories: {a['name']} / {b['name']}", author)
    content_sync.full_sync()


def delete_category(category_id: int, author: str) -> None:
    current = get_category(category_id)
    if current is None:
        return
    project = projects_store.get_project(current["project_id"])
    paths = content_files.delete_category(project["slug"], current["slug"])
    if paths:
        git_content_repo.commit_and_push(paths, f"Remove category: {current['name']} ({project['name']})", author)
        content_sync.full_sync()
