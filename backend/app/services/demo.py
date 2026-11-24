"""Demo mode (DEMO_MODE=1): a public instance anybody may sign in to and try
everything an author does, reset every night (deploy/demo/).

What a stranger with the admin password could misuse is switched off: the
account itself (password, two-factor, accounts, API tokens -- one visitor
must not lock out the next), e-mail (the instance would be a relay to any
address typed in) and the import from a Git URL (it makes the server open
connections to addresses a visitor chooses). Everything else -- writing,
publishing, importing a ZIP, branding, versions -- works, because that is
what a demo is for, and the nightly reset takes it away again.

The demo's login is shown on the sign-in page (DEMO_USERNAME and
DEMO_PASSWORD): it is not a secret, it is the point.
"""
import re

from app.settings import settings

MESSAGE = "Not available in the demo: it resets every night and is shared by everyone who tries it."

_BLOCKED = [
    re.compile(p)
    for p in (
        r"^/api/auth/password$",
        r"^/api/auth/notifications(/.*)?$",
        r"^/api/auth/mfa/(keys|totp|recovery)(/.*)?$",
        r"^/api/admin/users(/.*)?$",
        r"^/api/admin/tokens(/.*)?$",
        r"^/api/admin/import/git(/.*)?$",
        r"^/api/sync/.*$",
    )
]


def is_enabled() -> bool:
    return settings.demo_mode


def blocked(method: str, path: str) -> bool:
    """Whether demo mode refuses this request. Reading is never refused."""
    if not settings.demo_mode or method in ("GET", "HEAD", "OPTIONS"):
        return False
    return any(p.match(path) for p in _BLOCKED)


def public_status() -> dict:
    if not settings.demo_mode:
        return {"enabled": False}
    return {"enabled": True, "username": settings.demo_username, "password": settings.demo_password}
