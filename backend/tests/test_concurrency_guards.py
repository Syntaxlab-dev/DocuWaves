"""Guards against writes stepping on each other.

- SQLite runs in WAL mode with a busy timeout, so a second writer waits
  instead of failing with "database is locked" after its commit.
- Only one reindex runs at a time.
- A session's last-seen time is written at most once a minute, not on
  every admin request.
"""
import threading
import time

from app.services import content_sync, db, session_registry_store
from app.settings import settings


def test_sqlite_connections_use_wal_and_wait_for_locks(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "index.db"))
    with db.get_connection() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert mode.lower() == "wal"
    assert timeout >= 5000


def test_only_one_reindex_runs_at_a_time(monkeypatch):
    running = 0
    overlapped = False
    guard = threading.Lock()

    def slow_sync():
        nonlocal running, overlapped
        with guard:
            running += 1
            overlapped = overlapped or running > 1
        time.sleep(0.05)
        with guard:
            running -= 1

    monkeypatch.setattr(content_sync, "_full_sync", slow_sync)
    threads = [threading.Thread(target=content_sync.full_sync) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert overlapped is False


def test_session_last_seen_is_written_at_most_once_a_minute(monkeypatch):
    writes = []

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params):
            writes.append(params)

    monkeypatch.setattr(session_registry_store.db, "get_connection", lambda: FakeConn())
    monkeypatch.setattr(session_registry_store, "_last_touch", {})
    for _ in range(5):
        session_registry_store.touch("session-a")
    session_registry_store.touch("session-b")
    assert len(writes) == 2

    real = session_registry_store.time.monotonic
    monkeypatch.setattr(session_registry_store.time, "monotonic",
                        lambda: real() + session_registry_store._TOUCH_INTERVAL_SECONDS + 1)
    session_registry_store.touch("session-a")
    assert len(writes) == 3
