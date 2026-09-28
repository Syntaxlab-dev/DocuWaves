"""Who is calling, as far as this app can tell behind a reverse proxy.

Used for counting -- the rate limits on sign-in, the chat and page feedback --
and for the "signed in from" line of a session. Never stored beyond that.

WHICH ADDRESS, AND WHY: the RIGHTMOST entry of X-Forwarded-For. Every ordinary
reverse proxy either appends the address it received the request from to that
header (nginx's $proxy_add_x_forwarded_for, Traefik) or replaces the header
outright (Caddy), so the last entry is the one the proxy itself vouches for.
The FIRST entry is whatever the caller chose to send: trusting it hands an
attacker a fresh rate-limit bucket for every request they make.

It also deliberately avoids request.client.host whenever that header is
present: the image runs uvicorn with --forwarded-allow-ips=* (see Dockerfile),
and in that mode uvicorn rewrites request.client to the LEFTMOST -- caller
controlled -- entry.

Behind more than one proxy (e.g. Cloudflare in front of nginx) the rightmost
entry is the outer proxy's own address and every reader would share one
bucket. CLIENT_IP_HEADER names the header that outer proxy puts the real
address in (CF-Connecting-IP, X-Real-IP, ...); it is read instead.
"""
from fastapi import Request

from app.settings import settings


def client_address(request: Request) -> str:
    if settings.client_ip_header:
        configured = request.headers.get(settings.client_ip_header, "").strip()
        if configured:
            return configured.split(",")[-1].strip()

    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        nearest = forwarded.split(",")[-1].strip()
        if nearest:
            return nearest

    return request.client.host if request.client else ""
