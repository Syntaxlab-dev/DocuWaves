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


def revoke_for_user(username: str) -> int:
    """Signs one account out everywhere, and says how many sessions that
    was.

    Called when an account is DELETED and when its role is lowered. The
    middleware already re-reads the role on every request, so this is not
    what makes the change take effect -- it is what makes it visible: the
    person is returned to the login screen instead of clicking around an
    admin UI whose every button has quietly started answering 403."""
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        cursor = conn.execute(f"DELETE FROM sessions WHERE username = {placeholder}", (username,))
        return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0


def sessions_for(username: str) -> list[dict]:
    """One account's live sessions, newest first -- what the account list
    shows as "signed in on 2 devices", so an admin removing somebody can see
    that it took."""
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT created_at, last_seen_at FROM sessions WHERE username = {placeholder} "
            f"ORDER BY last_seen_at DESC",
            (username,),
        ).fetchall()
    return [{"created_at": row[0], "last_seen_at": row[1]} for row in rows]


def revoke(session_id: str) -> None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM sessions WHERE session_id = {placeholder}", (session_id,))
