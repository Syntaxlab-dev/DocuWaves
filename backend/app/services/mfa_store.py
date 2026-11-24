"""Two-factor sign-in: security keys, an authenticator app, recovery codes.

THREE KINDS OF SECOND FACTOR, any mix of them per account:

    security keys   WebAuthn/FIDO2 -- a YubiKey or any other FIDO2 key, and
                    also the passkeys built into phones and laptops (Touch ID,
                    Windows Hello, Android). Several per account, each with a
                    name, so a spare key in a drawer is a supported setup and
                    losing one key is not losing the account.
    authenticator   TOTP (RFC 6238): the six-digit codes from any
                    authenticator app. One per account.
    recovery codes  Ten single-use codes, shown once, for the day the key is
                    lost and the phone is dead. Only hashes are stored.

Once an account has a security key or a confirmed authenticator app, a
correct password is no longer enough: routers/auth.py's login asks for the
second factor before it starts a session. Recovery codes alone never switch
2FA on -- they are the way back in, not a factor of their own.

WHAT 2FA DOES NOT COVER, deliberately:

  * Single sign-on. A login through the identity provider never asks for a
    second factor here, because the provider is where that belongs: an
    organisation that wants 2FA for its people turns it on there, once, for
    every application. Asking again here would be a second prompt for the
    same person on every sign-in.
  * API tokens. A token is already a credential that was created by a signed
    in account and can be revoked; it has no interactive moment to ask in.

The TOTP implementation is the RFC's ~20 lines rather than a dependency: an
HMAC, a dynamic truncation, a window of one step either side for clocks that
drift, and `last_step` so an observed code cannot be replayed within its
thirty seconds.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime, timezone
from urllib.parse import quote

from app.services import db

TOTP_DIGITS = 6
TOTP_PERIOD = 30
# One step either side: a phone whose clock is up to 30 seconds off, or a
# code typed in the last second of its window, still works.
TOTP_WINDOW = 1

RECOVERY_CODE_COUNT = 10
_KEY_NAME_MAX = 60


def _placeholder() -> str:
    return "%s" if db.is_postgres() else "?"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Overview ----


def status(username: str) -> dict:
    """What the account settings page shows, and what login asks for."""
    keys = list_keys(username)
    totp = totp_enabled(username)
    return {
        "enabled": bool(keys) or totp,
        "keys": keys,
        "totp": totp,
        "recovery_codes_left": recovery_codes_left(username),
    }


def enabled(username: str) -> bool:
    return bool(list_keys(username)) or totp_enabled(username)


def methods(username: str) -> list[str]:
    """The second factors this account can be asked for, in the order the
    login screen offers them: a key first, because it is the stronger one."""
    found = []
    if list_keys(username):
        found.append("webauthn")
    if totp_enabled(username):
        found.append("totp")
    if found and recovery_codes_left(username):
        found.append("recovery")
    return found


def delete_all(username: str) -> None:
    """Everything this account had: when the account is deleted, and when an
    admin resets the 2FA of somebody who lost every factor."""
    placeholder = _placeholder()
    with db.get_connection() as conn:
        for table in ("mfa_keys", "mfa_totp", "mfa_recovery_codes"):
            conn.execute(f"DELETE FROM {table} WHERE username = {placeholder}", (username,))


# ---- Security keys (WebAuthn) ----


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _key_row(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "created_at": row[2],
        "last_used_at": row[3],
    }


def list_keys(username: str) -> list[dict]:
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, name, created_at, last_used_at FROM mfa_keys WHERE username = {_placeholder()} ORDER BY id",
            (username,),
        ).fetchall()
    return [_key_row(row) for row in rows]


def key_credentials(username: str) -> list[dict]:
    """The stored halves the WebAuthn ceremonies need -- never sent to a
    browser beyond the credential ids."""
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, credential_id, public_key, sign_count, transports FROM mfa_keys "
            f"WHERE username = {_placeholder()} ORDER BY id",
            (username,),
        ).fetchall()
    return [
        {
            "id": row[0],
            "credential_id": b64url_decode(row[1]),
            "public_key": b64url_decode(row[2]),
            "sign_count": int(row[3]),
            "transports": [t for t in (row[4] or "").split(",") if t],
        }
        for row in rows
    ]


def credential_in_use(credential_id: bytes) -> bool:
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT 1 FROM mfa_keys WHERE credential_id = {_placeholder()}", (b64url(credential_id),)
        ).fetchone()
    return row is not None


def add_key(
    username: str, name: str, credential_id: bytes, public_key: bytes, sign_count: int, transports: list[str]
) -> None:
    placeholder = _placeholder()
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO mfa_keys (username, name, credential_id, public_key, sign_count, transports, created_at) "
            f"VALUES ({', '.join([placeholder] * 7)})",
            (
                username,
                (name.strip() or "Security key")[:_KEY_NAME_MAX],
                b64url(credential_id),
                b64url(public_key),
                int(sign_count),
                ",".join(transports),
                _now_iso(),
            ),
        )


def key_used(key_id: int, sign_count: int) -> None:
    placeholder = _placeholder()
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE mfa_keys SET sign_count = {placeholder}, last_used_at = {placeholder} WHERE id = {placeholder}",
            (int(sign_count), _now_iso(), key_id),
        )


def delete_key(username: str, key_id: int) -> bool:
    placeholder = _placeholder()
    with db.get_connection() as conn:
        cursor = conn.execute(
            f"DELETE FROM mfa_keys WHERE id = {placeholder} AND username = {placeholder}", (key_id, username)
        )
        return bool(cursor.rowcount and cursor.rowcount > 0)


# ---- Authenticator app (TOTP, RFC 6238) ----


def _hotp(secret: bytes, counter: int) -> str:
    digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**TOTP_DIGITS).zfill(TOTP_DIGITS)


def _secret_bytes(secret: str) -> bytes:
    return base64.b32decode(secret + "=" * (-len(secret) % 8))


def totp_code(secret: str, at: float | None = None) -> str:
    """The code an authenticator shows at a moment -- for tests, and the one
    place the RFC's arithmetic lives."""
    return _hotp(_secret_bytes(secret), int((time.time() if at is None else at) // TOTP_PERIOD))


def _matching_step(secret: str, code: str, at: float) -> int | None:
    code = "".join(c for c in code if c.isdigit())
    if len(code) != TOTP_DIGITS:
        return None
    now_step = int(at // TOTP_PERIOD)
    key = _secret_bytes(secret)
    for step in range(now_step - TOTP_WINDOW, now_step + TOTP_WINDOW + 1):
        if hmac.compare_digest(_hotp(key, step), code):
            return step
    return None


def _totp_row(username: str):
    with db.get_connection() as conn:
        return conn.execute(
            f"SELECT secret, confirmed, last_step FROM mfa_totp WHERE username = {_placeholder()}", (username,)
        ).fetchone()


def totp_enabled(username: str) -> bool:
    row = _totp_row(username)
    return bool(row and row[1])


def start_totp(username: str) -> str:
    """A new, unconfirmed secret. It replaces an earlier unconfirmed one (the
    QR code that was scanned last is the one that counts) but never a
    confirmed one: switching apps means turning the old one off first."""
    secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
    placeholder = _placeholder()
    with db.get_connection() as conn:
        conn.execute(
            f"DELETE FROM mfa_totp WHERE username = {placeholder} AND confirmed = 0", (username,)
        )
        conn.execute(
            f"INSERT INTO mfa_totp (username, secret, confirmed, last_step, created_at) "
            f"VALUES ({placeholder}, {placeholder}, 0, 0, {placeholder})",
            (username, secret, _now_iso()),
        )
    return secret


def otpauth_uri(secret: str, username: str, issuer: str) -> str:
    """What the QR code says. The label is `issuer:username`, which is how
    every authenticator app groups and names the entry."""
    label = quote(f"{issuer}:{username}", safe="")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer, safe='')}"
        f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD}"
    )


def pending_totp_secret(username: str) -> str | None:
    row = _totp_row(username)
    return row[0] if row and not row[1] else None


def _set_step(username: str, step: int, confirm: bool) -> None:
    placeholder = _placeholder()
    with db.get_connection() as conn:
        conn.execute(
            f"UPDATE mfa_totp SET last_step = {placeholder}"
            + (", confirmed = 1" if confirm else "")
            + f" WHERE username = {placeholder}",
            (step, username),
        )


def confirm_totp(username: str, code: str, at: float | None = None) -> bool:
    """Turns the pending secret on once the app has shown a correct code --
    proof it was scanned, so 2FA never switches on with a secret nobody has."""
    row = _totp_row(username)
    if not row or row[1]:
        return False
    step = _matching_step(row[0], code, time.time() if at is None else at)
    if step is None:
        return False
    _set_step(username, step, confirm=True)
    return True


def verify_totp(username: str, code: str, at: float | None = None) -> bool:
    """A correct code from a step NEWER than the last one used -- a code seen
    over somebody's shoulder cannot be typed in again within its window."""
    row = _totp_row(username)
    if not row or not row[1]:
        return False
    step = _matching_step(row[0], code, time.time() if at is None else at)
    if step is None or step <= int(row[2]):
        return False
    _set_step(username, step, confirm=False)
    return True


def disable_totp(username: str) -> None:
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM mfa_totp WHERE username = {_placeholder()}", (username,))


# ---- Recovery codes ----


def _normalize_code(code: str) -> str:
    return "".join(c for c in code.lower() if c.isalnum())


def _hash_code(code: str) -> str:
    # SHA-256, not bcrypt: a code is 50 random bits from secrets, not a
    # password somebody chose, so there is no dictionary to slow down.
    return hashlib.sha256(_normalize_code(code).encode("ascii")).hexdigest()


def _new_code() -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i
    raw = "".join(secrets.choice(alphabet) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


def regenerate_recovery_codes(username: str) -> list[str]:
    """Ten fresh codes; every earlier one stops working. The plain codes are
    returned exactly once, to be shown to the person -- only hashes stay."""
    codes = [_new_code() for _ in range(RECOVERY_CODE_COUNT)]
    placeholder = _placeholder()
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM mfa_recovery_codes WHERE username = {placeholder}", (username,))
        for code in codes:
            conn.execute(
                f"INSERT INTO mfa_recovery_codes (username, code_hash, used_at) VALUES ({placeholder}, {placeholder}, '')",
                (username, _hash_code(code)),
            )
    return codes


def recovery_codes_left(username: str) -> int:
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) FROM mfa_recovery_codes WHERE username = {_placeholder()} AND used_at = ''",
            (username,),
        ).fetchone()
    return int(row[0])


def has_recovery_codes(username: str) -> bool:
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT 1 FROM mfa_recovery_codes WHERE username = {_placeholder()} LIMIT 1", (username,)
        ).fetchone()
    return row is not None


def use_recovery_code(username: str, code: str) -> bool:
    """True once per code. The UPDATE's own `used_at = ''` condition is what
    makes it single-use even when two sign-ins race with the same code."""
    if not _normalize_code(code):
        return False
    placeholder = _placeholder()
    with db.get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE mfa_recovery_codes SET used_at = {placeholder} "
            f"WHERE username = {placeholder} AND code_hash = {placeholder} AND used_at = ''",
            (_now_iso(), username, _hash_code(code)),
        )
        return bool(cursor.rowcount and cursor.rowcount > 0)
