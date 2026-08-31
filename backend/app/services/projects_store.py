"""Top-level content grouping -- one row per SyntaxLab project/app whose
docs live in this DocuWaves instance. sort_order is a plain integer the
admin UI shifts with up/down arrows (same "no drag-and-drop library"
choice CachePanel already made deliberately) rather than a fractional
position scheme."""

from app.services import db


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


def create_project(name: str, slug: str, icon: str, color: str, description: str) -> int:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM projects").fetchone()
        next_order = row[0]
        if db.is_postgres():
            result = conn.execute(
                f"INSERT INTO projects (name, slug, icon, color, description, sort_order) "
                f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}) "
                f"RETURNING id",
                (name, slug, icon, color, description, next_order),
            )
            return result.fetchone()[0]
        cursor = conn.execute(
            f"INSERT INTO projects (name, slug, icon, color, description, sort_order) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
            (name, slug, icon, color, description, next_order),
        )
        return cursor.lastrowid


def update_project(project_id: int, name: str, slug: str, icon: str, color: str, description: str) -> None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE projects SET name = {placeholder}, slug = {placeholder}, icon = {placeholder}, "
            f"color = {placeholder}, description = {placeholder} WHERE id = {placeholder}",
            (name, slug, icon, color, description, project_id),
        )


def reorder_project(project_id: int, direction: int) -> None:
    """direction: -1 (move up) or +1 (move down) -- swaps sort_order with
    the adjacent project in that direction, same up/down-arrow mechanism
    categories_store.py and pages_store.py use for their own ordering."""
    projects = list_projects()
    index = next((i for i, p in enumerate(projects) if p["id"] == project_id), None)
    if index is None:
        return
    swap_index = index + direction
    if not (0 <= swap_index < len(projects)):
        return
    a, b = projects[index], projects[swap_index]
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(f"UPDATE projects SET sort_order = {placeholder} WHERE id = {placeholder}", (b["sort_order"], a["id"]))
        conn.execute(f"UPDATE projects SET sort_order = {placeholder} WHERE id = {placeholder}", (a["sort_order"], b["id"]))


def delete_project(project_id: int) -> None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM projects WHERE id = {placeholder}", (project_id,))
