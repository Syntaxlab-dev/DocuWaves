"""The single admin account that guards DocuWaves' editing UI. v1
deliberately supports exactly one account (no roles, no multi-user --
CachePanel took several feature rounds to grow into that, not worth
pre-building here before anyone has asked for it) and exactly one
authentication path per login attempt: password OR OIDC, both landing in
this same one-row table.

bcrypt hash is stored as-is (no extra encryption layer): a bcrypt hash is
already designed to be safe to store/expose (one-way, salted, deliberately
slow to brute-force), same reasoning CachePanel's own equivalent store
documents.
"""

import bcrypt

from app.services import db


def is_configured() -> bool:
    with db.get_connection() as conn:
        row = conn.execute("SELECT 1 FROM auth LIMIT 1").fetchone()
    return row is not None


def get_user(username: str) -> dict | None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT username, password_hash FROM auth WHERE username = {placeholder}", (username,)
        ).fetchone()
    if row is None:
        return None
    return {"username": row[0], "password_hash": row[1]}


def set_credentials(username: str, password: str) -> None:
    """First-run only: creates the single admin account. Callers must
    ensure this is only invoked when no account exists yet (see
    routers/auth.py's /setup and the OIDC bootstrap path)."""
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM auth")  # v1 is single-account: a fresh setup always replaces any prior state
        conn.execute(
            f"INSERT INTO auth (username, password_hash) VALUES ({placeholder}, {placeholder})",
            (username, password_hash),
        )


def set_password(username: str, new_password: str) -> None:
    password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE auth SET password_hash = {placeholder} WHERE username = {placeholder}",
            (password_hash, username),
        )


def verify_credentials(username: str, password: str) -> bool:
    user = get_user(username)
    if user is None:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8"))
    except ValueError:
        return False
