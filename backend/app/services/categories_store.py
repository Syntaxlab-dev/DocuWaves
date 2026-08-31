"""Categories group pages within one project -- the "tile" navigation
level between a project's landing page and its individual pages. Slugs
are unique per project (not globally), enforced by the DB's own
UNIQUE(project_id, slug) constraint."""

from app.services import db

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


def create_category(project_id: int, name: str, slug: str, icon: str) -> int:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT COALESCE(MAX(sort_order), -1) + 1 FROM categories WHERE project_id = {placeholder}",
            (project_id,),
        ).fetchone()
        next_order = row[0]
        if db.is_postgres():
            result = conn.execute(
                f"INSERT INTO categories (project_id, name, slug, icon, sort_order) "
                f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}) RETURNING id",
                (project_id, name, slug, icon, next_order),
            )
            return result.fetchone()[0]
        cursor = conn.execute(
            f"INSERT INTO categories (project_id, name, slug, icon, sort_order) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
            (project_id, name, slug, icon, next_order),
        )
        return cursor.lastrowid


def update_category(category_id: int, name: str, slug: str, icon: str) -> None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE categories SET name = {placeholder}, slug = {placeholder}, icon = {placeholder} WHERE id = {placeholder}",
            (name, slug, icon, category_id),
        )


def reorder_category(project_id: int, category_id: int, direction: int) -> None:
    categories = list_categories(project_id)
    index = next((i for i, c in enumerate(categories) if c["id"] == category_id), None)
    if index is None:
        return
    swap_index = index + direction
    if not (0 <= swap_index < len(categories)):
        return
    a, b = categories[index], categories[swap_index]
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(f"UPDATE categories SET sort_order = {placeholder} WHERE id = {placeholder}", (b["sort_order"], a["id"]))
        conn.execute(f"UPDATE categories SET sort_order = {placeholder} WHERE id = {placeholder}", (a["sort_order"], b["id"]))


def delete_category(category_id: int) -> None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM categories WHERE id = {placeholder}", (category_id,))
