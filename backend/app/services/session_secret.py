"""Persists the SessionMiddleware signing key across restarts -- without
this, every container restart would invalidate every existing session
cookie, logging every browser out. Generated once on first run, stored
next to the SQLite database (or the auth data more generally) rather than
baked into an env var, so it never ends up in a docker-compose.yml/.env
that might get shared or committed."""

import os
import secrets
from pathlib import Path

_SECRET_PATH = Path(os.environ.get("SESSION_SECRET_PATH", "/data/.session_secret"))


def get_or_create_secret() -> str:
    if _SECRET_PATH.exists():
        return _SECRET_PATH.read_text(encoding="utf-8").strip()
    _SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_urlsafe(48)
    _SECRET_PATH.write_text(secret, encoding="utf-8")
    os.chmod(_SECRET_PATH, 0o600)
    return secret
