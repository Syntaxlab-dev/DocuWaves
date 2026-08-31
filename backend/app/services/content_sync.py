"""Reconciles the database (projects/categories/pages tables, plus the FTS5/
tsvector search index built on top of them) with whatever's actually on disk
in the content repo's checkout -- the database is a rebuildable INDEX over
the files, never the other way around. On any doubt or divergence, the
filesystem wins and the database row is overwritten or removed to match it.

Matching existing DB rows to filesystem items is done by slug -- projects.slug
is globally unique, categories.slug is unique per project, pages.slug is
unique per project, exactly the same uniqueness the filesystem's own
directory/file naming already has to respect (two categories with the same
folder name inside one project directory is simply impossible on disk). A
row whose slug is still present on disk keeps its existing id (and every
existing admin-editor deep link / API caller that already has that id stays
valid); a slug that's new gets a freshly assigned id; a slug that's gone
gets its row (and, via ON DELETE CASCADE, everything under it) removed.

Pages are matched/retired at the PROJECT level, not per-category: a page's
slug is only unique within its project, and moving a page to a different
category of the same project (move_page() in content_files.py) must keep
its id. Doing the existing/seen/stale bookkeeping per-category instead would
see the page vanish from its old category's disk listing before its new
category's pass ever runs, and delete-then-recreate it with a fresh id --
this module resolves that by syncing every category's page directory first,
then reconciling all of that project's pages in one single pass.
"""

from datetime import datetime, timezone

from app.services import content_files, db


def full_sync() -> None:
    with db.get_connection() as conn:
        _sync_projects(conn)


def _placeholder() -> str:
    return "%s" if db.is_postgres() else "?"


def _sync_projects(conn) -> None:
    p = _placeholder()
    disk_slugs = content_files.list_project_slugs()
    existing = {row[0]: row[1] for row in conn.execute("SELECT slug, id FROM projects").fetchall()}

    seen_ids: set[int] = set()
    for slug in disk_slugs:
        data = content_files.read_project(slug)
        if data is None:
            continue
        if slug in existing:
            project_id = existing[slug]
            conn.execute(
                f"UPDATE projects SET name={p}, icon={p}, color={p}, description={p}, sort_order={p} WHERE id={p}",
                (data["name"], data["icon"], data["color"], data["description"], data["order"], project_id),
            )
        else:
            if db.is_postgres():
                row = conn.execute(
                    f"INSERT INTO projects (name, slug, icon, color, description, sort_order) "
                    f"VALUES ({p},{p},{p},{p},{p},{p}) RETURNING id",
                    (data["name"], slug, data["icon"], data["color"], data["description"], data["order"]),
                ).fetchone()
                project_id = row[0]
            else:
                cursor = conn.execute(
                    f"INSERT INTO projects (name, slug, icon, color, description, sort_order) "
                    f"VALUES ({p},{p},{p},{p},{p},{p})",
                    (data["name"], slug, data["icon"], data["color"], data["description"], data["order"]),
                )
                project_id = cursor.lastrowid
        seen_ids.add(project_id)
        _sync_categories_and_pages(conn, project_id, slug)

    stale_ids = set(existing.values()) - seen_ids
    for stale_id in stale_ids:
        conn.execute(f"DELETE FROM projects WHERE id={p}", (stale_id,))


def _sync_categories_and_pages(conn, project_id: int, project_slug: str) -> None:
    p = _placeholder()

    # -- Categories first (pages need a resolved category_id) --
    disk_category_slugs = content_files.list_category_slugs(project_slug)
    existing_categories = {
        row[0]: row[1]
        for row in conn.execute(f"SELECT slug, id FROM categories WHERE project_id={p}", (project_id,)).fetchall()
    }

    category_ids_by_slug: dict[str, int] = {}
    seen_category_ids: set[int] = set()
    for slug in disk_category_slugs:
        data = content_files.read_category(project_slug, slug)
        if data is None:
            continue
        if slug in existing_categories:
            category_id = existing_categories[slug]
            conn.execute(
                f"UPDATE categories SET name={p}, icon={p}, sort_order={p} WHERE id={p}",
                (data["name"], data["icon"], data["order"], category_id),
            )
        else:
            if db.is_postgres():
                row = conn.execute(
                    f"INSERT INTO categories (project_id, name, slug, icon, sort_order) "
                    f"VALUES ({p},{p},{p},{p},{p}) RETURNING id",
                    (project_id, data["name"], slug, data["icon"], data["order"]),
                ).fetchone()
                category_id = row[0]
            else:
                cursor = conn.execute(
                    f"INSERT INTO categories (project_id, name, slug, icon, sort_order) VALUES ({p},{p},{p},{p},{p})",
                    (project_id, data["name"], slug, data["icon"], data["order"]),
                )
                category_id = cursor.lastrowid
        category_ids_by_slug[slug] = category_id
        seen_category_ids.add(category_id)

    stale_category_ids = set(existing_categories.values()) - seen_category_ids
    for stale_id in stale_category_ids:
        conn.execute(f"DELETE FROM categories WHERE id={p}", (stale_id,))

    # -- Pages: one pass across ALL of this project's categories, see module docstring --
    existing_pages = {
        row[0]: row[1]
        for row in conn.execute(f"SELECT slug, id FROM pages WHERE project_id={p}", (project_id,)).fetchall()
    }
    seen_page_ids: set[int] = set()

    for category_slug, category_id in category_ids_by_slug.items():
        for slug in content_files.list_page_slugs(project_slug, category_slug):
            data = content_files.read_page(project_slug, category_slug, slug)
            if data is None:
                continue
            published_value = data["published"] if db.is_postgres() else (1 if data["published"] else 0)
            if slug in existing_pages:
                page_id = existing_pages[slug]
                conn.execute(
                    f"UPDATE pages SET title={p}, markdown_content={p}, sort_order={p}, published={p}, "
                    f"category_id={p} WHERE id={p}",
                    (data["title"], data["markdown_content"], data["order"], published_value, category_id, page_id),
                )
            else:
                if db.is_postgres():
                    row = conn.execute(
                        f"INSERT INTO pages (project_id, category_id, title, slug, markdown_content, sort_order, "
                        f"published, created_at, updated_at) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p}) "
                        f"RETURNING id",
                        (
                            project_id, category_id, data["title"], slug, data["markdown_content"],
                            data["order"], published_value,
                            datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(),
                        ),
                    ).fetchone()
                    page_id = row[0]
                else:
                    now = datetime.now(timezone.utc).isoformat()
                    cursor = conn.execute(
                        f"INSERT INTO pages (project_id, category_id, title, slug, markdown_content, sort_order, "
                        f"published, created_at, updated_at) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p})",
                        (project_id, category_id, data["title"], slug, data["markdown_content"], data["order"], published_value, now, now),
                    )
                    page_id = cursor.lastrowid
            seen_page_ids.add(page_id)

    stale_page_ids = set(existing_pages.values()) - seen_page_ids
    for stale_id in stale_page_ids:
        conn.execute(f"DELETE FROM pages WHERE id={p}", (stale_id,))
