"""A `/metrics` endpoint in Prometheus's text format.

Off unless METRICS_TOKEN is set: the numbers say how big the documentation
is and how busy the instance is, which is nobody's business but the
operator's. With the token set, Prometheus scrapes with

    authorization:
      credentials: <METRICS_TOKEN>

(`Authorization: Bearer <token>`); anything else gets a 404, the same answer
as an instance that has metrics off, so a scanner learns nothing.

What is counted:

- requests, by method and status code, and their total duration -- counted
  in this process since it started, so a restart starts them at 0, which
  Prometheus's rate() expects;
- the content: projects, pages by state, accounts by role;
- the work that waits: scheduled publications, open search gaps, reader
  feedback;
- when the content index was last rebuilt.

Written by hand rather than with prometheus_client: a dozen lines of text
are not worth a dependency, and nothing here needs more than counters and
gauges. Labels are kept to what has a small, fixed set of values -- never a
path or a page -- so a busy site cannot blow up the series count.
"""
import hmac
import threading
import time
from datetime import datetime

from app import version
from app.services import content_sync, db
from app.settings import settings

_lock = threading.Lock()
_requests: dict[tuple[str, str], int] = {}
_duration_sum = 0.0
_duration_count = 0
_STARTED = time.time()
_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}


def enabled() -> bool:
    return bool(settings.metrics_token)


def allowed(authorization: str) -> bool:
    if not enabled():
        return False
    scheme, _, value = (authorization or "").partition(" ")
    if scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(value.strip().encode(), settings.metrics_token.encode())


def record(method: str, status: int, seconds: float) -> None:
    global _duration_sum, _duration_count
    key = (method if method in _METHODS else "OTHER", str(status))
    with _lock:
        _requests[key] = _requests.get(key, 0) + 1
        _duration_sum += seconds
        _duration_count += 1


class RequestCounter:
    """ASGI middleware: counts every HTTP request with its status and time.
    Plain ASGI rather than BaseHTTPMiddleware, so it adds no task per request
    and never touches a streamed body."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not enabled():
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500

        async def sending(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, sending)
        finally:
            if scope.get("path") != "/metrics":
                record(scope.get("method", ""), status, time.perf_counter() - started)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    return "{" + ",".join(f'{k}="{_escape(str(v))}"' for k, v in labels.items()) + "}"


class _Out:
    def __init__(self):
        self.lines: list[str] = []

    def metric(self, name: str, kind: str, help_text: str, samples: list[tuple[dict, float]]) -> None:
        self.lines.append(f"# HELP {name} {help_text}")
        self.lines.append(f"# TYPE {name} {kind}")
        for labels, value in samples:
            number = int(value) if float(value).is_integer() else value
            self.lines.append(f"{name}{_labels(labels)} {number}")


def _count(conn, sql: str) -> list[tuple]:
    return [tuple(row) for row in conn.execute(sql).fetchall()]


def render() -> str:
    out = _Out()
    out.metric("docuwaves_info", "gauge", "The running DocuWaves version.", [({"version": version.VERSION}, 1)])
    out.metric("docuwaves_start_time_seconds", "gauge", "When this process started (Unix time).", [({}, round(_STARTED, 3))])

    with _lock:
        requests = sorted(_requests.items())
        duration_sum, duration_count = _duration_sum, _duration_count
    out.metric(
        "docuwaves_http_requests_total", "counter", "HTTP requests answered, by method and status code.",
        [({"method": m, "status": s}, n) for (m, s), n in requests],
    )
    out.metric(
        "docuwaves_http_request_duration_seconds", "summary", "Time spent answering HTTP requests.", [],
    )
    out.lines.append(f"docuwaves_http_request_duration_seconds_sum {round(duration_sum, 6)}")
    out.lines.append(f"docuwaves_http_request_duration_seconds_count {duration_count}")

    with db.get_connection() as conn:
        projects = _count(conn, "SELECT COUNT(*) FROM projects")[0][0]
        pages = dict(_count(conn, "SELECT published, COUNT(*) FROM pages GROUP BY published"))
        roles = _count(conn, "SELECT role, COUNT(*) FROM auth GROUP BY role ORDER BY role")
        scheduled = _count(conn, "SELECT COUNT(*) FROM scheduled_publish")[0][0]
        gaps = _count(conn, "SELECT COUNT(*) FROM search_gaps")[0][0]
        feedback = dict(_count(conn, "SELECT helpful, COUNT(*) FROM page_feedback GROUP BY helpful"))
    out.metric("docuwaves_projects", "gauge", "Documentation projects.", [({}, projects)])
    out.metric(
        "docuwaves_pages", "gauge", "Pages (each language and version counted), by state.",
        [({"state": "published"}, pages.get(1, 0)), ({"state": "draft"}, pages.get(0, 0))],
    )
    out.metric("docuwaves_accounts", "gauge", "Accounts, by role.", [({"role": r}, n) for r, n in roles])
    out.metric("docuwaves_scheduled_publications", "gauge", "Drafts waiting for their publication time.", [({}, scheduled)])
    out.metric("docuwaves_search_gaps", "gauge", "Searches that found nothing, as distinct queries.", [({}, gaps)])
    out.metric(
        "docuwaves_page_feedback_total", "counter", "Answers to 'Was this helpful?'.",
        [({"helpful": "yes"}, feedback.get(1, 0)), ({"helpful": "no"}, feedback.get(0, 0))],
    )

    last = content_sync.last_sync()
    if last:
        try:
            stamp = datetime.fromisoformat(last).timestamp()
        except ValueError:
            stamp = 0.0
        out.metric(
            "docuwaves_content_index_last_rebuild_seconds", "gauge",
            "When the content index was last rebuilt from the repository (Unix time).", [({}, round(stamp, 3))],
        )
    return "\n".join(out.lines) + "\n"
