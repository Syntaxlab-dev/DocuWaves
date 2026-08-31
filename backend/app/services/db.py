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

import sqlite3
from pathlib import Path

import psycopg

from app.settings import settings


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
    """
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        icon TEXT NOT NULL DEFAULT '',
        color TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        slug TEXT NOT NULL,
        icon TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0,
        UNIQUE(project_id, slug)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        slug TEXT NOT NULL,
        markdown_content TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0,
        published INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(project_id, slug)
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
    """
    CREATE TABLE IF NOT EXISTS projects (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        icon TEXT NOT NULL DEFAULT '',
        color TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS categories (
        id SERIAL PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        slug TEXT NOT NULL,
        icon TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0,
        UNIQUE(project_id, slug)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pages (
        id SERIAL PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        slug TEXT NOT NULL,
        markdown_content TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0,
        published BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(project_id, slug)
    )
    """,
    # No triggers/materialized tsvector column here -- to_tsvector() is
    # computed live in pages_store.py's search query instead (see that
    # module's own docstring for why: simpler, and fast enough at the
    # scale a self-hosted docs tool actually runs at).
    "CREATE INDEX IF NOT EXISTS pages_project_idx ON pages(project_id)",
]


def init_schema() -> None:
    """Called once at startup (see main.py's lifespan) for BOTH backends --
    unlike CachePanel, where this was a Postgres-only no-op, DocuWaves
    always has a real schema to create (SQLite included)."""
    with get_connection() as conn:
        for statement in (_POSTGRES_SCHEMA if is_postgres() else _SQLITE_SCHEMA):
            conn.execute(statement)
