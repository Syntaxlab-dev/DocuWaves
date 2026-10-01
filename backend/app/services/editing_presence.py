"""Who has a page open in the editor right now.

The editor already refuses a save made on top of text that changed in the
meantime (pages_store.update_page, expected_revision) -- that catches the
collision when it happens. This is the earlier warning: "Michel is editing
this page, with unsaved changes" as soon as somebody else opens it, before
two people have spent half an hour on the same paragraph.

HOW: each open editor (one browser TAB, identified by a random id the tab
makes up) sends a heartbeat every ~20 seconds saying which page it has open
and whether it holds unsaved changes. An entry not refreshed for a minute is
gone -- a closed laptop, a crashed browser -- and closing the editor removes
it at once. Nothing is written to disk and nothing is a LOCK: anybody can
still open and save the page; this only tells them somebody else is there.

IN MEMORY, deliberately, like the login throttle and the rate limits next to
it: one server process (see the Dockerfile), and the information is worth
nothing a minute later. A restart forgets it; the next heartbeat (within
~20 s) brings every open editor back.

A page is keyed by what identifies it across reindexes -- project slug,
version, page slug, language -- not by its row id, which a full reindex
reassigns.
"""
import re
import threading
import time

TTL_SECONDS = 60
_MAX_ENTRIES = 2000
_TAB_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

_lock = threading.Lock()
# (page key, tab id) -> entry
_entries: dict[tuple[str, str], dict] = {}


def page_key(project_slug: str, page: dict) -> str:
    return f"{project_slug}\x1f{page.get('version', '')}\x1f{page.get('slug', '')}\x1f{page.get('language', '')}"


def valid_tab(tab: str) -> bool:
    return bool(_TAB_RE.match(tab or ""))


def _prune(now: float) -> None:
    for k in [k for k, e in _entries.items() if now - e["last_seen"] > TTL_SECONDS]:
        del _entries[k]


def heartbeat(key: str, tab: str, username: str, dirty: bool) -> None:
    now = time.time()
    with _lock:
        _prune(now)
        entry = _entries.get((key, tab))
        if entry is None:
            if len(_entries) >= _MAX_ENTRIES:
                return  # a flood of made-up tabs must not grow this forever
            entry = {"username": username, "since": now}
            _entries[(key, tab)] = entry
        entry["last_seen"] = now
        entry["dirty"] = bool(dirty)
        entry["username"] = username


def leave(key: str, tab: str) -> None:
    with _lock:
        _entries.pop((key, tab), None)


def others(key: str, tab: str, username: str) -> list[dict]:
    """Everybody else on this page, longest-present first. `same_account`
    marks the caller's own account in ANOTHER tab -- worth saying too, since
    the second tab's save would overwrite the first's just the same."""
    now = time.time()
    with _lock:
        _prune(now)
        found = [
            {
                "username": e["username"],
                "since": int(e["since"]),
                "seconds": int(now - e["since"]),
                "dirty": e["dirty"],
                "same_account": e["username"] == username,
            }
            for (k, t), e in _entries.items()
            if k == key and t != tab
        ]
    return sorted(found, key=lambda e: e["since"])


def on_pages(keys: dict[int, str]) -> dict[int, list[dict]]:
    """For a list of pages ({page id: key}): who is editing which, for the
    page list's pencil marks."""
    now = time.time()
    by_key: dict[str, list[dict]] = {}
    with _lock:
        _prune(now)
        for (k, _t), e in _entries.items():
            by_key.setdefault(k, []).append({"username": e["username"], "dirty": e["dirty"]})
    return {page_id: by_key[k] for page_id, k in keys.items() if k in by_key}


def reset() -> None:
    """Tests only."""
    with _lock:
        _entries.clear()
