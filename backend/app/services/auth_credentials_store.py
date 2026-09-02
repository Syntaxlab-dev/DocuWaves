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

# bcrypt hashes at most the first 72 bytes of a password -- that is the
# algorithm's own limit, not a library choice, and it has always been true
# here. bcrypt 4.x applied it silently: it truncated anything longer and
# carried on. bcrypt 5.0 refuses instead, raising
# ValueError("password cannot be longer than 72 bytes") from BOTH hashpw()
# and checkpw() at 73 bytes and up.
#
# Left alone, that turns an upgrade into a lockout. An operator who set a
# passphrase longer than 72 bytes under 4.x has a hash of its first 72
# bytes; after the upgrade checkpw() raises on their unchanged password,
# verify_credentials() catches ValueError and returns False, and the login
# answers "Incorrect username or password" forever -- with no way in and
# nothing in the log to explain it. set_password()/set_credentials() have
# no such catch, so setting a long passphrase would surface as a 500.
#
# So do explicitly what 4.x did implicitly, at the one boundary where a
# password becomes bytes. Truncating the ENCODED bytes (not the string) is
# what reproduces the old behaviour exactly: 4.x truncated the utf-8 bytes
# it was handed, so byte-truncation -- even mid-character for a multi-byte
# passphrase -- is what keeps every hash written by 4.x verifying. Slicing
# characters instead would silently invalidate non-ASCII passwords.
_BCRYPT_MAX_BYTES = 72


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


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
    password_hash = bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("utf-8")
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM auth")  # v1 is single-account: a fresh setup always replaces any prior state
        conn.execute(
            f"INSERT INTO auth (username, password_hash) VALUES ({placeholder}, {placeholder})",
            (username, password_hash),
        )


def set_password(username: str, new_password: str) -> None:
    password_hash = bcrypt.hashpw(_password_bytes(new_password), bcrypt.gensalt()).decode("utf-8")
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
        return bcrypt.checkpw(_password_bytes(password), user["password_hash"].encode("utf-8"))
    except ValueError:
        return False
