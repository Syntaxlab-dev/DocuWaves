"""Top-level content grouping -- one row per SyntaxLab project/app whose
docs live in this DocuWaves instance.

Reads (list_projects, get_project, get_project_by_slug, slug_taken) still
just query the `projects` table exactly as before -- that table is a
database INDEX kept in sync with content_files.py's on-disk `_project.yml`
files by content_sync.py, not the source of truth itself. Writes
(create/update/reorder/delete) go through content_files.py + git_content_repo.py
instead of a plain SQL INSERT/UPDATE/DELETE: they write the file(s), commit +
push to the content repo, then re-run content_sync.full_sync() so the
database reflects exactly what's now on disk (and picks up its assigned id
for a brand-new project) before returning. sort_order is a plain integer the
admin UI shifts with up/down arrows (same "no drag-and-drop library" choice
CachePanel already made deliberately) -- persisted in `order:` inside
`_project.yml` now, not just a DB column.
"""

from app.services import content_files, content_sync, db, git_content_repo


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "slug": row[2],
        "icon": row[3],
        "color": row[4],
        "description": row[5],
        "sort_order": row[6],
    }


_COLUMNS = "id, name, slug, icon, color, description, sort_order"


def list_projects() -> list[dict]:
    with db.get_connection() as conn:
        rows = conn.execute(f"SELECT {_COLUMNS} FROM projects ORDER BY sort_order, name").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_project(project_id: int) -> dict | None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM projects WHERE id = {placeholder}", (project_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_project_by_slug(slug: str) -> dict | None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM projects WHERE slug = {placeholder}", (slug,)).fetchone()
    return _row_to_dict(row) if row else None


def slug_taken(slug: str, exclude_id: int | None = None) -> bool:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        if exclude_id is not None:
            row = conn.execute(
                f"SELECT 1 FROM projects WHERE slug = {placeholder} AND id != {placeholder}", (slug, exclude_id)
            ).fetchone()
        else:
            row = conn.execute(f"SELECT 1 FROM projects WHERE slug = {placeholder}", (slug,)).fetchone()
    return row is not None


def _next_order() -> int:
    with db.get_connection() as conn:
        row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM projects").fetchone()
    return row[0]


def create_project(name: str, slug: str, icon: str, color: str, description: str, author: str) -> dict:
    order = _next_order()
    paths = content_files.write_project(slug, name, icon, color, description, order)
    git_content_repo.commit_and_push(paths, f"Add project: {name}", author)
    content_sync.full_sync()
    return get_project_by_slug(slug)


def update_project(project_id: int, name: str, slug: str, icon: str, color: str, description: str, author: str) -> dict | None:
    current = get_project(project_id)
    if current is None:
        return None
    paths: list[str] = []
    if slug != current["slug"]:
        paths += content_files.rename_project(current["slug"], slug)
    paths += content_files.write_project(slug, name, icon, color, description, current["sort_order"])
    git_content_repo.commit_and_push(paths, f"Update project: {name}", author)
    content_sync.full_sync()
    return get_project_by_slug(slug)


def reorder_project(project_id: int, direction: int, author: str) -> None:
    """direction: -1 (move up) or +1 (move down) -- swaps the `order:` field
    in the two affected projects' _project.yml files with their adjacent
    project in that direction, same up/down-arrow mechanism
    categories_store.py and pages_store.py use for their own ordering."""
    projects = list_projects()
    index = next((i for i, pr in enumerate(projects) if pr["id"] == project_id), None)
    if index is None:
        return
    swap_index = index + direction
    if not (0 <= swap_index < len(projects)):
        return
    a, b = projects[index], projects[swap_index]
    paths = content_files.write_project(a["slug"], a["name"], a["icon"], a["color"], a["description"], b["sort_order"])
    paths += content_files.write_project(b["slug"], b["name"], b["icon"], b["color"], b["description"], a["sort_order"])
    git_content_repo.commit_and_push(paths, f"Reorder projects: {a['name']} / {b['name']}", author)
    content_sync.full_sync()


def delete_project(project_id: int, author: str) -> None:
    current = get_project(project_id)
    if current is None:
        return
    paths = content_files.delete_project(current["slug"])
    if paths:
        git_content_repo.commit_and_push(paths, f"Remove project: {current['name']}", author)
        content_sync.full_sync()
