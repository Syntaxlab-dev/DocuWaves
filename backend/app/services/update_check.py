"""Is there a newer DocuWaves than this one?

An instance nobody looks after keeps running the version it was installed
with, security fixes included. So the admin area says so when a newer
release exists -- once a day this asks GitHub which release is the latest,
and compares.

What leaves the server is one anonymous GET to GitHub's public API for this
repository's latest release: no instance address, no counts, no version in
the URL. `UPDATE_CHECK=off` turns it off completely, and an instance
without internet access simply never shows the notice.

Only a release build can be compared. "latest" (a build of main) and "dev"
(a checkout run by hand) have no number, so they are never told to update.
"""

import logging
import re
import threading
import time

import requests

from app import version
from app.settings import settings

log = logging.getLogger("docuwaves")

RELEASES_URL = "https://api.github.com/repos/Syntaxlab-dev/DocuWaves/releases/latest"
_TTL_SECONDS = 24 * 3600
# After a failed check, try again sooner than a day but not on every page load.
_RETRY_SECONDS = 3600
_TIMEOUT_SECONDS = 5

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "ttl": 0, "release": None}


def _parse(tag: str) -> tuple[int, ...] | None:
    """"v1.2.0" or "1.2.0" -> (1, 2, 0). Pre-releases ("1.2.0-rc1") are not
    offered as updates, so they don't parse."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (tag or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def _fetch() -> dict | None:
    try:
        response = requests.get(
            RELEASES_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "DocuWaves update check"},
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        log.info("Update check: could not ask GitHub for the latest release (%s)", exc)
        return None
    tag = str(data.get("tag_name") or "")
    if not _parse(tag):
        return None
    return {"tag": tag, "url": str(data.get("html_url") or ""), "published_at": str(data.get("published_at") or "")}


def _latest_release() -> dict | None:
    with _lock:
        if time.monotonic() - _cache["at"] < _cache["ttl"]:
            return _cache["release"]
        release = _fetch()
        _cache.update(at=time.monotonic(), ttl=_TTL_SECONDS if release else _RETRY_SECONDS, release=release)
        return release


def status() -> dict:
    """What the admin area shows. `newer` is the only field it acts on."""
    current = version.VERSION
    result = {"enabled": settings.update_check_enabled, "current": current, "latest": None, "url": None, "newer": False}
    if not settings.update_check_enabled or _parse(current) is None:
        return result
    release = _latest_release()
    if not release:
        return result
    result.update(
        latest=release["tag"].lstrip("v"),
        url=release["url"],
        newer=_parse(release["tag"]) > _parse(current),
    )
    return result
