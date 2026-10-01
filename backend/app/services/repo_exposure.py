"""Is the content repository readable by anybody?

A private project hides pages on the WEBSITE (services/visibility.py). Its
files sit in the content repo like every other page, so if that repository
is public -- a GitHub repo somebody forgot to make private, say -- the
"private" docs are one `git clone` away. That is the single easiest way to
get private projects wrong, and nothing on the website would show it.

So this asks the remote exactly what a stranger could: `git ls-remote`
WITHOUT any credentials. If the remote lists its branches, it is public. If
it wants a login (or says the repository does not exist, which is how
GitHub and GitLab answer a stranger about a private repo), it is private. If
the question cannot be answered -- no network, a host that does not speak
https -- it is "unknown", and the admin UI says that rather than guessing.

The token never takes part: the URL is stripped of credentials first, git
is told not to prompt and not to use any credential helper, and an
scp-style SSH address (git@host:owner/repo) is asked over https, which is
what a stranger would try.

Answers are cached for an hour: a repository does not flip visibility often,
and the status bar asks on every admin page load.
"""
import os
import re
import subprocess
import threading
import time
from urllib.parse import urlsplit, urlunsplit

from app.settings import settings

PUBLIC = "public"
PRIVATE = "private"
UNKNOWN = "unknown"

_CACHE_SECONDS = 3600
_TIMEOUT_SECONDS = 12
_SCP_RE = re.compile(r"^(?:[\w.-]+@)?([\w.-]+):(?!//)(.+)$")

_lock = threading.Lock()
_cache: dict[str, tuple[float, str]] = {}

_AUTH_MARKERS = (
    "authentication failed",
    "could not read username",
    "terminal prompts disabled",
    "repository not found",
    "not found",
    "403",
    "401",
    "access denied",
    "permission denied",
    "authorization",
)


def anonymous_url(url: str) -> str:
    """The address a stranger would use: https, no user, no token."""
    url = (url or "").strip()
    if not url:
        return ""
    scp = _SCP_RE.match(url)
    if scp and "://" not in url:
        return f"https://{scp.group(1)}/{scp.group(2)}"
    parts = urlsplit(url)
    if parts.scheme in ("ssh", "git+ssh"):
        host = parts.hostname or ""
        return f"https://{host}{parts.path}" if host else ""
    if parts.scheme not in ("http", "https"):
        return ""
    host = parts.hostname or ""
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def display_location(url: str) -> str:
    """host/owner/repo for the status bar -- never a credential."""
    anon = anonymous_url(url)
    if not anon:
        return ""
    parts = urlsplit(anon)
    path = parts.path[:-4] if parts.path.endswith(".git") else parts.path
    return f"{parts.hostname}{path}"


def classify(returncode: int, stderr: str) -> str:
    if returncode == 0:
        return PUBLIC
    text = (stderr or "").lower()
    if any(marker in text for marker in _AUTH_MARKERS):
        return PRIVATE
    return UNKNOWN


def _probe(url: str) -> str:
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/false",
        "SSH_ASKPASS": "/bin/false",
        "GCM_INTERACTIVE": "never",
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": "/nonexistent",
    }
    try:
        result = subprocess.run(
            ["git", "-c", "credential.helper=", "ls-remote", "--heads", "--", url],
            capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, env=env, stdin=subprocess.DEVNULL,
        )
    except (subprocess.TimeoutExpired, OSError):
        return UNKNOWN
    return classify(result.returncode, result.stderr)


def check(refresh: bool = False) -> dict:
    """{"remote": host/path or "", "visibility": public|private|unknown|None}.
    visibility is None on a local-only instance -- nothing to expose."""
    configured = settings.content_repo_url
    url = anonymous_url(configured)
    if not configured:
        return {"remote": "", "visibility": None}
    if not url:
        return {"remote": display_location(configured), "visibility": UNKNOWN}
    with _lock:
        cached = _cache.get(url)
        if cached and not refresh and time.monotonic() - cached[0] < _CACHE_SECONDS:
            return {"remote": display_location(configured), "visibility": cached[1]}
    answer = _probe(url)
    with _lock:
        _cache[url] = (time.monotonic(), answer)
    return {"remote": display_location(configured), "visibility": answer}


def is_public() -> bool:
    return check()["visibility"] == PUBLIC
