"""Individual doc pages. Content is stored as raw Markdown text (rendered
client-side by the frontend, see frontend/src/lib/markdown.tsx) -- the
backend never parses or transforms it, just stores and searches it.

Search is genuinely two different implementations per backend rather than
one shared query, because SQLite and Postgres have unrelated full-text
mechanisms:
- SQLite: the pages_fts FTS5 virtual table (see db.py), queried with a
  MATCH expression built from the user's search terms, each term quoted as
  its own FTS5 string literal (`"term"`) so punctuation inside a term can't
  break FTS5's own query-syntax parser -- terms are OR'd together, ranked
  by FTS5's built-in bm25().
- Postgres: to_tsvector('simple', title || ' ' || content) computed live
  in the query (no materialized tsvector column/trigger -- simpler, and
  fast enough at the row counts a self-hosted docs tool actually holds)
  matched against plainto_tsquery('simple', %s), which safely tokenizes
  arbitrary user input as a parameterized value (no injection risk, unlike
  hand-building an FTS5 MATCH string).
'simple' text search config on the Postgres side deliberately skips
English-specific stemming, matching FTS5's own non-stemming default --
keeps search behavior close to identical between the two backends.
"""

from datetime import datetime, timezone

from app.services import db

_COLUMNS = "id, project_id, category_id, title, slug, markdown_content, sort_order, published, created_at, updated_at"


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "project_id": row[1],
        "category_id": row[2],
        "title": row[3],
        "slug": row[4],
        "markdown_content": row[5],
        "sort_order": row[6],
        "published": bool(row[7]),
        "created_at": row[8],
        "updated_at": row[9],
    }


def list_pages(category_id: int, published_only: bool = False) -> list[dict]:
    placeholder = "%s" if db.is_postgres() else "?"
    query = f"SELECT {_COLUMNS} FROM pages WHERE category_id = {placeholder}"
    params: tuple = (category_id,)
    if published_only:
        query += " AND published = " + ("TRUE" if db.is_postgres() else "1")
    query += " ORDER BY sort_order, title"
    with db.get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_page(page_id: int) -> dict | None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM pages WHERE id = {placeholder}", (page_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_page_by_slug(project_id: int, slug: str) -> dict | None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM pages WHERE project_id = {placeholder} AND slug = {placeholder}",
            (project_id, slug),
        ).fetchone()
    return _row_to_dict(row) if row else None


def slug_taken(project_id: int, slug: str, exclude_id: int | None = None) -> bool:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        if exclude_id is not None:
            row = conn.execute(
                f"SELECT 1 FROM pages WHERE project_id = {placeholder} AND slug = {placeholder} AND id != {placeholder}",
                (project_id, slug, exclude_id),
            ).fetchone()
        else:
            row = conn.execute(
                f"SELECT 1 FROM pages WHERE project_id = {placeholder} AND slug = {placeholder}",
                (project_id, slug),
            ).fetchone()
    return row is not None


def create_page(project_id: int, category_id: int, title: str, slug: str, markdown_content: str) -> int:
    placeholder = "%s" if db.is_postgres() else "?"
    now = datetime.now(timezone.utc).isoformat()
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT COALESCE(MAX(sort_order), -1) + 1 FROM pages WHERE category_id = {placeholder}",
            (category_id,),
        ).fetchone()
        next_order = row[0]
        args = (project_id, category_id, title, slug, markdown_content, next_order, now, now)
        if db.is_postgres():
            result = conn.execute(
                f"INSERT INTO pages (project_id, category_id, title, slug, markdown_content, sort_order, "
                f"published, created_at, updated_at) VALUES ({placeholder}, {placeholder}, {placeholder}, "
                f"{placeholder}, {placeholder}, {placeholder}, FALSE, {placeholder}, {placeholder}) RETURNING id",
                args,
            )
            return result.fetchone()[0]
        cursor = conn.execute(
            f"INSERT INTO pages (project_id, category_id, title, slug, markdown_content, sort_order, "
            f"published, created_at, updated_at) VALUES ({placeholder}, {placeholder}, {placeholder}, "
            f"{placeholder}, {placeholder}, {placeholder}, 0, {placeholder}, {placeholder})",
            args,
        )
        return cursor.lastrowid


def update_page(page_id: int, title: str, slug: str, markdown_content: str, category_id: int) -> None:
    placeholder = "%s" if db.is_postgres() else "?"
    now = datetime.now(timezone.utc).isoformat()
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE pages SET title = {placeholder}, slug = {placeholder}, markdown_content = {placeholder}, "
            f"category_id = {placeholder}, updated_at = {placeholder} WHERE id = {placeholder}",
            (title, slug, markdown_content, category_id, now, page_id),
        )


def set_published(page_id: int, published: bool) -> None:
    placeholder = "%s" if db.is_postgres() else "?"
    value = published if db.is_postgres() else (1 if published else 0)
    with db.get_connection() as conn:
        conn.execute(f"UPDATE pages SET published = {placeholder} WHERE id = {placeholder}", (value, page_id))


def reorder_page(category_id: int, page_id: int, direction: int) -> None:
    pages = list_pages(category_id)
    index = next((i for i, p in enumerate(pages) if p["id"] == page_id), None)
    if index is None:
        return
    swap_index = index + direction
    if not (0 <= swap_index < len(pages)):
        return
    a, b = pages[index], pages[swap_index]
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(f"UPDATE pages SET sort_order = {placeholder} WHERE id = {placeholder}", (b["sort_order"], a["id"]))
        conn.execute(f"UPDATE pages SET sort_order = {placeholder} WHERE id = {placeholder}", (a["sort_order"], b["id"]))


def delete_page(page_id: int) -> None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM pages WHERE id = {placeholder}", (page_id,))


def _fts5_query(raw: str) -> str | None:
    terms = [t.replace('"', '') for t in raw.strip().split() if t.strip()]
    terms = [t for t in terms if t]
    if not terms:
        return None
    return " OR ".join(f'"{t}"' for t in terms)


def search(query: str, limit: int = 20) -> list[dict]:
    """Published pages only, across every project. Each result also carries
    its project/category name+slug so the UI can show where a hit lives."""
    query = query.strip()
    if not query:
        return []

    if db.is_postgres():
        sql = f"""
            SELECT p.id, p.title, p.slug, p.markdown_content, pr.name, pr.slug, c.name, c.slug
            FROM pages p
            JOIN projects pr ON pr.id = p.project_id
            JOIN categories c ON c.id = p.category_id
            WHERE p.published = TRUE
              AND to_tsvector('simple', p.title || ' ' || p.markdown_content) @@ plainto_tsquery('simple', %s)
            ORDER BY ts_rank(to_tsvector('simple', p.title || ' ' || p.markdown_content), plainto_tsquery('simple', %s)) DESC
            LIMIT %s
        """
        with db.get_connection() as conn:
            rows = conn.execute(sql, (query, query, limit)).fetchall()
    else:
        fts_query = _fts5_query(query)
        if fts_query is None:
            return []
        sql = """
            SELECT p.id, p.title, p.slug, p.markdown_content, pr.name, pr.slug, c.name, c.slug
            FROM pages_fts
            JOIN pages p ON p.id = pages_fts.rowid
            JOIN projects pr ON pr.id = p.project_id
            JOIN categories c ON c.id = p.category_id
            WHERE pages_fts MATCH ? AND p.published = 1
            ORDER BY bm25(pages_fts)
            LIMIT ?
        """
        with db.get_connection() as conn:
            rows = conn.execute(sql, (fts_query, limit)).fetchall()

    results = []
    for r in rows:
        snippet_source = r[3] or ""
        snippet = snippet_source[:220] + ("..." if len(snippet_source) > 220 else "")
        results.append(
            {
                "page_id": r[0],
                "title": r[1],
                "page_slug": r[2],
                "snippet": snippet,
                "project_name": r[4],
                "project_slug": r[5],
                "category_name": r[6],
                "category_slug": r[7],
            }
        )
    return results
