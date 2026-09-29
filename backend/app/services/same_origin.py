"""Is a state-changing request coming from this site's own pages?

The admin session is a cookie, and a browser sends cookies with requests that
OTHER sites trigger too. SameSite=Lax already stops most of that, but not
all: a request from a sibling subdomain counts as "same site" (docs.example.com
and example.com are one site to the browser), and a POST with no body -- such
as publishing a page -- needs nothing but a form on the other page.

Browsers send an Origin header with every POST, PUT, PATCH and DELETE, so
comparing it with this site's own host is a reliable check. A request with
neither Origin nor Referer comes from something that is not a browser
(curl, a script, the MCP client) and carries no ambient cookie worth
stealing, so it is let through; those callers authenticate on their own.
"""
from urllib.parse import urlsplit

from fastapi import Request

from app.settings import settings


def is_same_origin(request: Request) -> bool:
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return True
    if source.strip().lower() == "null":
        # Sandboxed frames and some redirects: never this site's own page.
        return False
    source_host = urlsplit(source).netloc.lower()

    allowed = {request.headers.get("host", "").lower()}
    forwarded_host = request.headers.get("x-forwarded-host", "")
    if forwarded_host:
        allowed.add(forwarded_host.split(",")[-1].strip().lower())
    if settings.public_base_url:
        allowed.add(urlsplit(settings.public_base_url).netloc.lower())
    allowed.discard("")
    return source_host in allowed
