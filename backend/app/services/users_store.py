"""The accounts that may open the editing UI, and what each of them may do.

This replaces the single-account store this app shipped with. That store's
docstring said multi-user was "not worth pre-building here before anyone has
asked for it", which was right at the time and is why the migration is as
small as it is: one table gained three columns, and the account that already
existed became the first admin.

THREE ROLES, AND WHY EXACTLY THREE

    viewer   reads the admin area: drafts, page history, which translations
             exist. Changes nothing. This is the reviewer -- the person who
             is asked whether a page is correct and who should not be able
             to "just fix" it in passing.
    editor   everything about the documentation: projects, categories,
             pages, images, versions, review notes, preview links.
    admin    the above, plus the instance itself: other accounts, API
             tokens, branding, diagnostics and the export.

The line between editor and admin is not seniority, it is blast radius. An
editor can rewrite every page and that is recoverable from the git history;
an admin can hand out a credential, change what the site claims to be, and
download the whole instance. Those are different mistakes.

NO "DEACTIVATED" STATE. Removing somebody's access is deleting their
account, and their sessions go with it. A disabled-but-present account is a
second way to say no that has to be checked at every gate that already
checks the first one, and on an instance with a handful of accounts it buys
nothing. Nothing is lost by deleting: the content repo attributes commits by
NAME, so everything that person wrote keeps their name on it, forever, with
no row in this table required.

WHAT AN ACCOUNT IS NOT. There is no reader account, and there will not be
one: the documentation is public, and the way to show somebody one
unpublished page is a preview link (see preview_links_store.py). Adding an
account for reading would be inventing a login for a site that does not have
one.

bcrypt hashes are stored as-is -- a bcrypt hash is designed to be safe to
store (one-way, salted, deliberately slow to brute-force).
"""

import bcrypt

from datetime import datetime, timezone

from app.services import db

VIEWER = "viewer"
EDITOR = "editor"
ADMIN = "admin"
ROLES = (VIEWER, EDITOR, ADMIN)

# The role an account gets when nothing says otherwise -- which is the case
# for exactly one account, the one that existed before roles did, and it has
# to be admin or the upgrade locks its owner out of their own instance. It
# is also the DEFAULT of the database column, so the migration needs no
# UPDATE at all: the value is right the moment the column exists.
DEFAULT_ROLE = ADMIN

_USERNAME_MAX_LENGTH = 60
MIN_PASSWORD_LENGTH = 8

# bcrypt hashes at most the first 72 bytes of a password -- the algorithm's
# own limit, not a library choice. bcrypt 4.x truncated silently; 5.0 raises
# instead, which would turn an upgrade into a lockout for anyone whose
# passphrase is longer (their stored hash IS of the first 72 bytes, and
# checkpw() would raise rather than compare). So do explicitly what 4.x did
# implicitly, at the one boundary where a password becomes bytes.
# Truncating the ENCODED bytes rather than the string is what reproduces the
# old behaviour exactly, mid-character or not -- slicing characters instead
# would silently invalidate every non-ASCII password ever set here.
_BCRYPT_MAX_BYTES = 72


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def _hash(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("utf-8")


def _placeholder() -> str:
    return "%s" if db.is_postgres() else "?"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_role(role: str) -> str:
    """A role this app knows, or the least powerful one. Unknown values
    resolve DOWN, never up: a hand-edited row saying `role: superuser` must
    not be read as more than admin, and a typo must not silently grant
    anything."""
    return role if role in ROLES else VIEWER


def may_write(role: str) -> bool:
    return role in (EDITOR, ADMIN)


def is_admin(role: str) -> bool:
    return role == ADMIN


# ---- Reading ----

_COLUMNS = "username, role, created_at, last_login_at"


def _row_to_dict(row) -> dict:
    return {
        "username": row[0],
        "role": normalize_role(row[1]),
        "created_at": row[2],
        "last_login_at": row[3],
    }


def is_configured() -> bool:
    with db.get_connection() as conn:
        return conn.execute("SELECT 1 FROM auth LIMIT 1").fetchone() is not None


def get_user(username: str) -> dict | None:
    """One account WITHOUT its password hash -- the shape every caller but
    verify_credentials() wants, and the one that cannot leak a hash through
    an endpoint that forgot to strip it."""
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM auth WHERE username = {_placeholder()}", (username,)
        ).fetchone()
    return None if row is None else _row_to_dict(row)


def list_users() -> list[dict]:
    with db.get_connection() as conn:
        rows = conn.execute(f"SELECT {_COLUMNS} FROM auth ORDER BY username").fetchall()
    return [_row_to_dict(row) for row in rows]


def admin_count() -> int:
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) FROM auth WHERE role = {_placeholder()}", (ADMIN,)
        ).fetchone()
    return int(row[0])


def is_last_admin(username: str) -> bool:
    """True when removing this account's admin rights (by deleting it, or by
    giving it another role) would leave the instance with nobody who can
    manage it. Every such change is refused -- an instance whose last admin
    demoted themselves has no way back that does not involve editing the
    database by hand."""
    user = get_user(username)
    return user is not None and user["role"] == ADMIN and admin_count() <= 1


# ---- Writing ----


def normalize_username(username: str) -> str:
    return username.strip()[:_USERNAME_MAX_LENGTH]


def create_first_admin(username: str, password: str) -> None:
    """First-run only: the account that opens a brand-new instance. Callers
    must have checked is_configured() first -- see routers/auth.py's /setup
    and the OIDC bootstrap."""
    create_user(normalize_username(username), password, ADMIN)


def create_user(username: str, password: str, role: str) -> dict | None:
    """A new account, or None when the name is already taken.

    Checked-then-inserted rather than relying on the UNIQUE constraint,
    because "that name is taken" is a sentence for a person and an
    IntegrityError is not."""
    username = normalize_username(username)
    if not username or get_user(username) is not None:
        return None
    placeholder = _placeholder()
    with db.get_connection() as conn:
        conn.execute(
            f"INSERT INTO auth (username, password_hash, role, created_at, last_login_at) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, '')",
            (username, _hash(password), normalize_role(role), _now_iso()),
        )
    return get_user(username)


def set_password(username: str, new_password: str) -> None:
    placeholder = _placeholder()
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE auth SET password_hash = {placeholder} WHERE username = {placeholder}",
            (_hash(new_password), username),
        )


def set_role(username: str, role: str) -> bool:
    """False when this would take away the last admin -- see is_last_admin.
    The check and the write are one function so no caller can do one without
    the other."""
    if role != ADMIN and is_last_admin(username):
        return False
    placeholder = _placeholder()
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE auth SET role = {placeholder} WHERE username = {placeholder}",
            (normalize_role(role), username),
        )
    return True


def delete_user(username: str) -> bool:
    """False when this account is the last admin. Everything that person
    wrote keeps their name on it: the content repo attributes commits by
    name, and no row here is needed for that to stay true."""
    if is_last_admin(username):
        return False
    placeholder = _placeholder()
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM auth WHERE username = {placeholder}", (username,))
    return True


def touch_login(username: str) -> None:
    placeholder = _placeholder()
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE auth SET last_login_at = {placeholder} WHERE username = {placeholder}",
            (_now_iso(), username),
        )


# ---- Verifying ----


def verify_credentials(username: str, password: str) -> bool:
    """One answer for "no such account" and "wrong password" -- and the
    bcrypt comparison is skipped for the first, which is the one place this
    function could otherwise be timed to enumerate account names. That is a
    small leak and this is a cheap fix, but it is not free: without a real
    hash there is nothing to compare, so a dummy verification is run instead
    to keep both paths taking about the same time."""
    placeholder = _placeholder()
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT password_hash FROM auth WHERE username = {placeholder}", (username,)
        ).fetchone()
    try:
        if row is None:
            bcrypt.checkpw(_password_bytes(password), _DUMMY_HASH)
            return False
        return bcrypt.checkpw(_password_bytes(password), row[0].encode("utf-8"))
    except ValueError:
        return False


# A real bcrypt hash of a value nobody knows, so the no-such-account branch
# above costs the same bcrypt round the found-account branch does. Computed
# once at import; the password is discarded.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-password", bcrypt.gensalt())
