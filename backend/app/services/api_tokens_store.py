"""API tokens -- the credential an operator creates in the admin UI and
hands to an AI assistant, which then reads (and, if the token says so,
writes) this instance's documentation through the MCP endpoint (see
routers/mcp.py).

WHERE THESE LIVE, and why it is not where everything else lives. Projects,
categories, pages, images and branding are all FILES IN THE CONTENT REPO,
because that repo is the source of truth and the database is only ever a
rebuildable index over it (see content_sync.py). A token is the one piece of
state in this app for which that reasoning inverts: it is a credential, and
the content repo's entire purpose is to be cloned, forked, and read in a
pull request by people who are not the operator. A token committed there
would be published by the very thing that makes the repo useful. So it goes
in the DATABASE, next to `auth` and `sessions` -- the two other tables that
hold real state existing nowhere else, and precisely the tables db.py's
schema rebuild deliberately never drops (see _CONTENT_TABLES there). A
reindex, a new image, a lost-and-recloned content repo: none of them touch a
token.

WHAT IS STORED. Never the token itself, only its SHA-256 hash -- the same
"a hash is safe to store" reasoning users_store.py documents for
the admin's bcrypt hash. The plaintext exists exactly once, in the response
to the create call, and is unrecoverable afterwards: losing it means making
a new token, not looking the old one up.

WHY SHA-256 AND NOT BCRYPT, when the password next door is bcrypt. bcrypt is
slow on purpose, to make guessing a human-chosen password expensive. There
is nothing to guess here: a token is 32 bytes straight out of `secrets`, so
the search space is 2^256 and no amount of hashing speed changes that
answer. What bcrypt WOULD change is that its deliberate slowness would sit
on every single MCP request an assistant makes. Plain SHA-256 over a value
that is already uniformly random is the right trade.

SCOPES. `read` or `write`, and write implies read -- there is no "write but
not read" token, because every write tool here has to look the existing
content up first (which project, which category, which page) and a scope
that forbade that would describe a token that cannot be used.
"""

import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import deque
from datetime import date, datetime, timezone

from app.services import db

# Prefix on every token value. Not decoration: a value that starts with
# `dwt_` is recognizable as a DocuWaves token in a log, a config file or a
# leaked paste, which is what lets a secret scanner (and a person) spot one
# that ended up somewhere it shouldn't. The prefix is part of the value and
# part of what gets hashed.
TOKEN_PREFIX = "dwt_"

# 32 bytes of urandom, URL-safe-base64'd to 43 characters. Well past any
# brute-force argument, and short enough to paste into a config file on one
# line.
_TOKEN_BYTES = 32

READ_SCOPE = "read"
WRITE_SCOPE = "write"
SCOPES = (READ_SCOPE, WRITE_SCOPE)

# More than this many live tokens on one self-hosted instance is a sign
# nobody is revoking anything, not a use case -- and verify() below scans
# every row on every request, which is fine for a handful and pointless
# work for a thousand.
MAX_TOKENS = 50

_NAME_MAX_LENGTH = 60

# How many requests ONE token may make per minute. An assistant working
# through a set of docs reads a page, lists a category, searches, writes --
# a handful of calls per step, in bursts, with the model's own thinking time
# (seconds) in between. 120/min is far above any pace a real assistant sets
# and still stops a runaway loop inside a second of it starting, which is
# the failure this actually guards against: an agent that retries a failing
# tool call forever would otherwise hammer git push in a tight loop.
#
# Per TOKEN, not per IP: an assistant and the operator's own browser
# routinely arrive from the same address (a local agent, a reverse proxy
# that doesn't forward the client IP), and one misbehaving assistant must
# not be able to lock the operator out of their own admin UI.
#
# This is NOT a defence against guessing a token -- 256 bits of entropy is,
# and a rate limit keyed on the presented value gives an attacker a fresh
# bucket per guess anyway. It is a throttle on a client that already
# authenticated (or keeps replaying one wrong value).
_RATE_LIMIT_REQUESTS = 120
_RATE_LIMIT_WINDOW_SECONDS = 60

# In-process, so it resets when the container restarts and is per worker
# process -- the shipped image runs a single uvicorn worker (see the
# Dockerfile's CMD), so that is one bucket per token, which is what the
# number above assumes. A deque of timestamps rather than a counter: a fixed
# window lets twice the limit through across a window boundary, and the
# whole point here is to bound a tight loop.
_rate_lock = threading.Lock()
_rate_buckets: dict[str, deque[float]] = {}

# When the bucket dict grows past this, stale entries are swept (see
# rate_limited). Comfortably above MAX_TOKENS, so a normal instance never
# sweeps at all -- it only trips on a caller presenting many distinct
# values, which is the case that could otherwise grow memory forever.
_RATE_BUCKET_SWEEP_AT = 512


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _placeholder() -> str:
    return "%s" if db.is_postgres() else "?"


def hash_token(value: str) -> str:
    """The stored form of a token. Hex rather than raw bytes so the column
    is TEXT on both backends, like every other column in this schema."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(_TOKEN_BYTES)


def looks_like_token(value: str) -> bool:
    """Whether a presented credential is even shaped like one of ours.
    Used only to keep an obviously-not-a-token value out of the database
    scan below; a value that passes this is still fully verified."""
    return value.startswith(TOKEN_PREFIX)


def author_name(token_name: str) -> str:
    """How a commit made through this token is ATTRIBUTED in the content
    repo's history. Handed to git_content_repo.commit_and_push() exactly
    where an admin write hands it the logged-in username, so a write through
    a token needs no separate commit path -- only a different author.

    The name spells out both halves of what happened: an assistant made the
    change, and it was allowed to because of this specific token. `git log`,
    `git log --author='API token'` and `git blame` then all answer "which of
    my tokens wrote this line?" without anyone having to open a diff, and
    the operator can revert exactly that token's commits. The COMMITTER
    stays DocuWaves (see git_content_repo._configure_repo), which is the
    honest description: this instance committed on the assistant's behalf.
    """
    return f"Claude (API token: {token_name})"


# ---- Reading ----


_COLUMNS = "id, name, scope, expires_at, created_at, last_used_at"


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "scope": row[2],
        # "" = never expires. Kept as the empty string rather than NULL so
        # every column in this table reads back as a str, like `auth` and
        # `sessions` next to it.
        "expires_at": row[3],
        "created_at": row[4],
        "last_used_at": row[5],
    }


def list_tokens() -> list[dict]:
    """Every live token, newest first. Deliberately WITHOUT `token_hash`:
    the admin UI has no use for it, and a value that never leaves this
    module can't leak through an endpoint that forgot to strip it."""
    with db.get_connection() as conn:
        rows = conn.execute(f"SELECT {_COLUMNS} FROM api_tokens ORDER BY id DESC").fetchall()
    return [_row_to_dict(r) for r in rows]


def count() -> int:
    with db.get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM api_tokens").fetchone()
    return int(row[0])


def is_expired(expires_at: str, today: date | None = None) -> bool:
    """A token expires at the END of its expiry date: one set to expire on
    2026-09-01 works for all of 2026-09-01. A date rather than a timestamp
    because that is what the operator picks in the UI, and "it stops working
    some time during the day I typed" would be a surprise.

    An unparseable value counts as EXPIRED, not as never-expiring: the only
    way this column holds something else is a hand-edited database, and the
    safe reading of a broken expiry is that the token is done."""
    if not expires_at:
        return False
    try:
        return (today or datetime.now(timezone.utc).date()) > date.fromisoformat(expires_at)
    except ValueError:
        return True


# ---- Verifying ----


def verify(presented: str) -> dict | None:
    """The token record behind a presented value, or None -- which is the
    single answer for "no such token", "revoked" and "expired" alike. The
    caller (auth_guard.py) turns all three into the same 401 an absent
    header gets: telling a caller that the token it holds used to be valid,
    or is valid but expired, tells whoever holds a stolen token exactly how
    to make it work, and gives no legitimate client anything it can act on.

    Every row is scanned and compared with hmac.compare_digest rather than
    looked up with `WHERE token_hash = ?`. The equality lookup would leak
    nothing that matters (the digest of a wrong guess reveals nothing about
    the right one), but "compare a secret-derived value in constant time" is
    a rule worth having no exceptions to, and MAX_TOKENS keeps the scan a
    handful of rows. `last_used_at` is touched on success, so the admin list
    can show a token nobody has used in months as the one to revoke."""
    if not presented or not looks_like_token(presented):
        return None
    digest = hash_token(presented)

    with db.get_connection() as conn:
        rows = conn.execute(f"SELECT {_COLUMNS}, token_hash FROM api_tokens").fetchall()
        match = None
        for row in rows:
            if hmac.compare_digest(str(row[6]), digest):
                match = row
                break
        if match is None:
            return None
        record = _row_to_dict(match)
        if is_expired(record["expires_at"]):
            return None
        now = _now_iso()
        conn.execute(
            f"UPDATE api_tokens SET last_used_at = {_placeholder()} WHERE id = {_placeholder()}",
            (now, record["id"]),
        )
    record["last_used_at"] = now
    return record


def may_write(record: dict) -> bool:
    """Write implies read, so this is the only scope question worth asking:
    a `read` token may do everything a `write` token may, minus the writes."""
    return record.get("scope") == WRITE_SCOPE


def rate_limited(presented: str) -> bool:
    """True = this token has already made _RATE_LIMIT_REQUESTS requests in
    the last minute and this one should be refused.

    Keyed on the HASH of the presented value, never the value itself: this
    dict is in memory and would otherwise be a place a token sits in
    plaintext for as long as the process lives."""
    if not presented:
        return False
    key = hash_token(presented)
    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    with _rate_lock:
        if len(_rate_buckets) > _RATE_BUCKET_SWEEP_AT:
            # Every distinct value ever presented gets a key here, valid or
            # not, so someone throwing random bearer strings at the endpoint
            # would otherwise grow this dict without bound. Sweeping only
            # when it gets big keeps the common path a single dict lookup.
            for stale in [k for k, b in _rate_buckets.items() if not b or b[-1] < cutoff]:
                del _rate_buckets[stale]
        bucket = _rate_buckets.setdefault(key, deque())
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= _RATE_LIMIT_REQUESTS:
            return True
        bucket.append(now)
    return False


def rate_limit_description() -> str:
    """The limit as a sentence, for the 429 body -- so a client is told the
    actual number rather than left to discover it by hitting it again."""
    return f"{_RATE_LIMIT_REQUESTS} requests per {_RATE_LIMIT_WINDOW_SECONDS} seconds per token"


# ---- Writing ----


def normalize_name(raw: str) -> str:
    """A token's name is only ever shown to a human and put in a commit
    author, so it is trimmed and length-capped rather than slugified --
    "Claude, notes bot" should stay readable. Control characters and
    newlines are stripped because this string ends up inside a git author
    line, where a newline would corrupt the commit object."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", (raw or "")).strip()[:_NAME_MAX_LENGTH].strip()


def rejection_reason(name: str, scope: str, expires_at: str) -> str | None:
    """None = this token can be created. Each check says what is wrong,
    since the only fix is for the operator to change the form."""
    if not name:
        return "A name is required -- it is how you will recognize this token later (for example 'notes-bot')."
    if scope not in SCOPES:
        return f"Scope must be '{READ_SCOPE}' or '{WRITE_SCOPE}'."
    if expires_at:
        try:
            expiry = date.fromisoformat(expires_at)
        except ValueError:
            return f"'{expires_at}' isn't a date. Use YYYY-MM-DD, or leave it empty for a token that never expires."
        if expiry < datetime.now(timezone.utc).date():
            return "That expiry date is in the past -- the token would be dead the moment it was created."
    if count() >= MAX_TOKENS:
        return f"This instance already has {MAX_TOKENS} API tokens, which is the limit. Revoke one you no longer use."
    return None


def create(name: str, scope: str, expires_at: str) -> tuple[dict, str]:
    """Returns (the record for the list, the plaintext token). The plaintext
    is returned to the caller and NOT stored anywhere -- this is the one and
    only moment it exists, which is why the admin UI shows it as a one-time
    reveal rather than a value you can come back for."""
    token = generate_token()
    placeholder = _placeholder()
    created_at = _now_iso()
    with db.get_connection() as conn:
        params = (name, hash_token(token), scope, expires_at, created_at, "")
        columns = "name, token_hash, scope, expires_at, created_at, last_used_at"
        values = ", ".join([placeholder] * 6)
        if db.is_postgres():
            row = conn.execute(
                f"INSERT INTO api_tokens ({columns}) VALUES ({values}) RETURNING id", params
            ).fetchone()
            token_id = row[0]
        else:
            token_id = conn.execute(f"INSERT INTO api_tokens ({columns}) VALUES ({values})", params).lastrowid
    return (
        {
            "id": token_id,
            "name": name,
            "scope": scope,
            "expires_at": expires_at,
            "created_at": created_at,
            "last_used_at": "",
        },
        token,
    )


def revoke(token_id: int) -> bool:
    """Deletes the row -- there is no `revoked` flag, because a revoked
    token has nothing left worth keeping: its value is unrecoverable, and
    the only two facts about it (what it was called, when it was last used)
    are exactly the two the operator just looked at before deciding to
    revoke it. False = no such token."""
    placeholder = _placeholder()
    with db.get_connection() as conn:
        row = conn.execute(f"SELECT 1 FROM api_tokens WHERE id = {placeholder}", (token_id,)).fetchone()
        if row is None:
            return False
        conn.execute(f"DELETE FROM api_tokens WHERE id = {placeholder}", (token_id,))
    return True
