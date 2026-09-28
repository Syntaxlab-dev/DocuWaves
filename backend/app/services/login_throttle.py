"""Brakes on password guessing, for sign-in and for changing a password.

Counts FAILED attempts only, in memory, in a sliding window -- a bucket of
timestamps per address and per username, never a log of who tried what.

Two counters, because they stop two different attacks:

- Per address: one machine trying many passwords. The tighter limit.
- Per username: many machines taking turns at one account, each staying
  under the per-address limit. Looser on purpose -- anyone can fail a login
  for someone else's username, so this counter is also a way to lock that
  person out. The limit is set high enough that doing so takes effort, and
  it only ever delays: nothing is locked for longer than the window.

The check happens BEFORE the password is verified, so a blocked caller costs
the server nothing -- bcrypt is deliberately slow, and an unthrottled login
endpoint is also a way to keep every worker thread busy hashing.
"""
import threading
import time
from collections import deque

WINDOW_SECONDS = 15 * 60
MAX_FAILURES_PER_ADDRESS = 10
MAX_FAILURES_PER_USERNAME = 30

# Stale buckets are swept once there are this many, rather than on every
# call: an instance sees a handful of addresses, an attack sees thousands.
_SWEEP_AT = 1024

_lock = threading.Lock()
_by_address: dict[str, deque[float]] = {}
_by_username: dict[str, deque[float]] = {}


def _key(username: str) -> str:
    return username.strip().lower()


def _prune(bucket: deque[float], cutoff: float) -> None:
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def _sweep(store: dict[str, deque[float]], cutoff: float) -> None:
    if len(store) <= _SWEEP_AT:
        return
    for stale in [key for key, bucket in store.items() if not bucket or bucket[-1] < cutoff]:
        del store[stale]


def retry_after(address: str, username: str) -> int:
    """0 = go ahead. Otherwise the number of seconds until enough counted
    failures have aged out of the window for the next attempt to be allowed."""
    now = time.monotonic()
    cutoff = now - WINDOW_SECONDS
    waits = []
    with _lock:
        for store, key, limit in (
            (_by_address, address, MAX_FAILURES_PER_ADDRESS),
            (_by_username, _key(username), MAX_FAILURES_PER_USERNAME),
        ):
            bucket = store.get(key) if key else None
            if not bucket:
                continue
            _prune(bucket, cutoff)
            if len(bucket) >= limit:
                # The attempt becomes possible once the oldest failure that
                # still keeps the count at the limit has left the window.
                oldest_blocking = bucket[len(bucket) - limit]
                waits.append(int(oldest_blocking + WINDOW_SECONDS - now) + 1)
    return max(waits, default=0)


def record_failure(address: str, username: str) -> None:
    now = time.monotonic()
    cutoff = now - WINDOW_SECONDS
    with _lock:
        _sweep(_by_address, cutoff)
        _sweep(_by_username, cutoff)
        if address:
            _by_address.setdefault(address, deque()).append(now)
        if _key(username):
            _by_username.setdefault(_key(username), deque()).append(now)


def record_success(username: str) -> None:
    """A correct password clears that account's own count, so its owner is
    not kept waiting by failures that were not theirs. The ADDRESS count
    stays: otherwise anyone with one valid account could reset their own
    limit between guesses at other accounts."""
    with _lock:
        _by_username.pop(_key(username), None)


def reset() -> None:
    """Tests only: forget every counted failure."""
    with _lock:
        _by_address.clear()
        _by_username.clear()
