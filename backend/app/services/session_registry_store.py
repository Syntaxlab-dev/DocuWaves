"""Server-side overlay on top of Starlette's stateless signed-cookie
session -- lets a login be revoked (logout) even though the cookie's own
signature stays valid until it expires. Same pattern as CachePanel's own
session_registry_store.py."""

from datetime import datetime, timezone

from app.services import db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(session_id: str, username: str, client_ip: str, user_agent: str) -> None:
    placeholder = "%s" if db.is_postgres() else "?"
    now = _now_iso()
    with db.get_connection() as conn:
        conn.execute(
            f"INSERT INTO sessions (session_id, username, created_at, last_seen_at, client_ip, user_agent) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
            (session_id, username, now, now, client_ip, user_agent),
        )


def exists(session_id: str) -> bool:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(f"SELECT 1 FROM sessions WHERE session_id = {placeholder}", (session_id,)).fetchone()
    return row is not None


def touch(session_id: str) -> None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE sessions SET last_seen_at = {placeholder} WHERE session_id = {placeholder}",
            (_now_iso(), session_id),
        )


def revoke(session_id: str) -> None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM sessions WHERE session_id = {placeholder}", (session_id,))
