"""Storage backend: SQLite by default (a single file under /data, zero
config -- matches the "easy to install" goal), or PostgreSQL when
DATABASE_URL is set. Unlike CachePanel (where the non-Postgres path is
flat JSON files), DocuWaves' content is inherently relational
(projects -> categories -> pages, plus full-text search), so BOTH backends
here are real SQL databases -- every store branches on is_postgres() and
writes each query twice (SQLite's `?` placeholders vs Postgres' `%s`,
and two different full-text-search strategies, see pages_store.py)
rather than hiding the difference behind a fake shared query layer.

get_connection() is used identically for both backends via
`with db.get_connection() as conn: ...` -- psycopg3's own Connection
already commits-and-closes as a context manager; _SqliteConnWrapper below
exists purely to make sqlite3.Connection behave the same way (its own
context manager only handles the transaction, never closes the
connection), so store code never has to care which backend it's talking
to beyond the one `if is_postgres():` branch.
"""

import logging
import sqlite3
from pathlib import Path

import psycopg

from app.settings import settings

log = logging.getLogger("docuwaves")


def is_postgres() -> bool:
    return bool(settings.database_url)


class _SqliteConnWrapper:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
        return False


def get_connection():
    if is_postgres():
        return psycopg.connect(settings.database_url)
    Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return _SqliteConnWrapper(conn)


_SQLITE_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS auth (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        client_ip TEXT NOT NULL,
        user_agent TEXT NOT NULL
    )
    """,
    # name_i18n / description_i18n hold the per-language MAPPING a
    # `_project.yml` may spell its name with (see site_languages.py), as a
    # JSON object, or '' for the plain-string form every single-language
    # repo uses. It's stored verbatim rather than normalized into rows of
    # its own because it is two short strings that vary per language, not a
    # second entity: a project_names table would put a join on the path of
    # every homepage tile and every sidebar, to carry what the file already
    # holds as one mapping. `name` stays the DEFAULT language's value, so
    # every existing query (ORDER BY name included) reads as it always did.
    """
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        name_i18n TEXT NOT NULL DEFAULT '',
        slug TEXT UNIQUE NOT NULL,
        icon TEXT NOT NULL DEFAULT '',
        color TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        description_i18n TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0
    )
    """,
    # `version` is the documentation version a row belongs to (see
    # content_versions.py): '' for a project that has no `_versions.yml` at
    # all -- so such a project keeps exactly one row per category/page and
    # (project, slug) is the same uniqueness it always had -- and otherwise
    # the version's directory name, 'current' for the working one. It is
    # part of the key rather than a filter because a frozen version holds
    # its OWN copy of every category and page: the same slug legitimately
    # exists once per version, and they are different rows describing
    # different files.
    """
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        name_i18n TEXT NOT NULL DEFAULT '',
        slug TEXT NOT NULL,
        version TEXT NOT NULL DEFAULT '',
        icon TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0,
        UNIQUE(project_id, version, slug)
    )
    """,
    # One row per page PER LANGUAGE -- `installation.de.md` and
    # `installation.en.md` are two rows sharing one slug, which is what lets
    # a reader switch language and stay on the same page. `language` is ''
    # on an instance with no `languages:` configured, so such an install
    # still has exactly one row per page and (project, slug, '') is the same
    # uniqueness the old UNIQUE(project_id, slug) gave it.
    """
    CREATE TABLE IF NOT EXISTS pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        slug TEXT NOT NULL,
        language TEXT NOT NULL DEFAULT '',
        version TEXT NOT NULL DEFAULT '',
        markdown_content TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0,
        published INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(project_id, version, slug, language)
    )
    """,
    # External-content FTS5 index -- content='pages' means the index stores
    # no page text of its own, just the search structures, and always reads
    # the real row via content_rowid=id; the three triggers below are what
    # SQLite's own FTS5 docs recommend for keeping such an index in sync
    # (there's no built-in "auto-sync" mode).
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
        title, markdown_content, content='pages', content_rowid='id'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS pages_fts_insert AFTER INSERT ON pages BEGIN
        INSERT INTO pages_fts(rowid, title, markdown_content) VALUES (new.id, new.title, new.markdown_content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS pages_fts_delete AFTER DELETE ON pages BEGIN
        INSERT INTO pages_fts(pages_fts, rowid, title, markdown_content) VALUES ('delete', old.id, old.title, old.markdown_content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS pages_fts_update AFTER UPDATE ON pages BEGIN
        INSERT INTO pages_fts(pages_fts, rowid, title, markdown_content) VALUES ('delete', old.id, old.title, old.markdown_content);
        INSERT INTO pages_fts(rowid, title, markdown_content) VALUES (new.id, new.title, new.markdown_content);
    END
    """,
]

_POSTGRES_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS auth (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        client_ip TEXT NOT NULL,
        user_agent TEXT NOT NULL
    )
    """,
    # See the SQLite block above for what name_i18n / language / version are
    # and why they are shaped this way -- the two schemas stay line-for-line
    # comparable on purpose.
    """
    CREATE TABLE IF NOT EXISTS projects (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        name_i18n TEXT NOT NULL DEFAULT '',
        slug TEXT UNIQUE NOT NULL,
        icon TEXT NOT NULL DEFAULT '',
        color TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        description_i18n TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS categories (
        id SERIAL PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        name_i18n TEXT NOT NULL DEFAULT '',
        slug TEXT NOT NULL,
        version TEXT NOT NULL DEFAULT '',
        icon TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0,
        UNIQUE(project_id, version, slug)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pages (
        id SERIAL PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        slug TEXT NOT NULL,
        language TEXT NOT NULL DEFAULT '',
        version TEXT NOT NULL DEFAULT '',
        markdown_content TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0,
        published BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(project_id, version, slug, language)
    )
    """,
    # No triggers/materialized tsvector column here -- to_tsvector() is
    # computed live in pages_store.py's search query instead (see that
    # module's own docstring for why: simpler, and fast enough at the
    # scale a self-hosted docs tool actually runs at).
    "CREATE INDEX IF NOT EXISTS pages_project_idx ON pages(project_id)",
]


# Every column the content index must have to be the CURRENT shape. Checked
# rather than version-stamped: the schema above is the single source of
# truth, and a stamp is one more thing that can disagree with it.
_REQUIRED_COLUMNS = {
    "projects": {"name_i18n", "description_i18n"},
    "categories": {"name_i18n", "version"},
    "pages": {"language", "version"},
}

# Only the content index is ever rebuilt. `auth` and `sessions` are real
# state that exists nowhere else (the admin's password hash, live logins) --
# they are NOT in this list and are never dropped.
_CONTENT_TABLES = ["pages", "categories", "projects"]

_SQLITE_FTS_OBJECTS = [
    "DROP TRIGGER IF EXISTS pages_fts_insert",
    "DROP TRIGGER IF EXISTS pages_fts_delete",
    "DROP TRIGGER IF EXISTS pages_fts_update",
    "DROP TABLE IF EXISTS pages_fts",
]


def _table_columns(conn, table: str) -> set[str]:
    """Empty set for a table that doesn't exist yet (both backends), which
    is exactly what a fresh install looks like."""
    if is_postgres():
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = %s",
            (table,),
        ).fetchall()
        return {r[0] for r in rows}
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _rebuild_content_index(conn) -> None:
    """Drops the projects/categories/pages tables (and SQLite's FTS index
    over them) so the CREATE TABLE statements above can lay them out afresh.

    This is the whole migration story, on purpose: these tables hold nothing
    that isn't already in the content repo's files -- they are documented
    everywhere in this codebase as a rebuildable INDEX (see content_sync.py)
    -- so recreating them costs one reindex of files that are already on
    disk, while an ALTER-by-ALTER migration would have to hand-write SQLite's
    12-step table rebuild for the changed UNIQUE constraint anyway, twice
    (once per backend), and get the back-filled values right by hand.

    Startup runs this, then repopulates from the working clone in the very
    same lifespan (main.py), so an existing deployment starting the new
    image needs no manual step and never serves an emptied index."""
    log.warning("Rebuilding the content index for the current schema (projects/categories/pages, from the content repo).")
    if is_postgres():
        for table in _CONTENT_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        return
    # SQLite: the FTS triggers reference `pages`, so they and the FTS table
    # go first -- dropping the table out from under a trigger leaves the
    # trigger behind, and the next INSERT then fails on a missing table.
    for statement in _SQLITE_FTS_OBJECTS:
        conn.execute(statement)
    for table in _CONTENT_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")


def init_schema() -> None:
    """Called once at startup (see main.py's lifespan) for BOTH backends --
    unlike CachePanel, where this was a Postgres-only no-op, DocuWaves
    always has a real schema to create (SQLite included)."""
    with get_connection() as conn:
        for table, required in _REQUIRED_COLUMNS.items():
            columns = _table_columns(conn, table)
            # Empty = the table isn't there at all (fresh install): nothing
            # to migrate, the CREATE statements below do the work.
            if columns and not required <= columns:
                _rebuild_content_index(conn)
                break
        for statement in (_POSTGRES_SCHEMA if is_postgres() else _SQLITE_SCHEMA):
            conn.execute(statement)
