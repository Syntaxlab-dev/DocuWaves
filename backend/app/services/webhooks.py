"""Tell another service when documentation changes: a Discord or Slack
channel, or any URL that accepts JSON.

WHERE IT IS CONFIGURED: environment variables (WEBHOOK_URLS, WEBHOOK_EVENTS,
WEBHOOK_SECRET), for the same reason the chat key is -- a webhook URL is a
credential (whoever has a Discord webhook URL can post to that channel), and
everything edited in the admin UI is written to _site.yml in a repository
built to be cloned.

WHAT TRIGGERS IT: a page's state CHANGING, never a save as such. The editor
calls "publish" after every save whether or not anything about the published
state changed; announcing each of those would post to a channel every time
someone fixes a typo. So:

- published    a page went from draft to published   (on by default)
- updated      a published page's title or text changed
- unpublished  a published page went back to draft, or was deleted
- review_requested  a page (or changes to a live page) was submitted for
                    approval (services/page_review.py)
- review_decided    a submission was approved or sent back

The two review events are for a team's own channel and are off unless
WEBHOOK_EVENTS names them. They carry no text from the page -- what waits
for approval is by definition not published yet -- only its title, whether
it is a new page or a change, the decision, and the admin address.

WHAT IT MUST NEVER DO: slow a save down or fail it. Delivery runs on a small
background pool with a short timeout and one retry; a dead endpoint is a log
line, not an error the author sees.

WHAT IS SENT: the page's title, project, language, version, a short summary
of its opening prose, and its public URL when PUBLIC_BASE_URL is set (there
is no request to take the address from here). Nothing about who made the
change -- the public site never says that either (see PublicPage).
"""
import hashlib
import hmac
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from app.settings import settings

log = logging.getLogger("docuwaves")

EVENTS = ("published", "updated", "unpublished", "review_requested", "review_decided")
_REVIEW_EVENTS = ("review_requested", "review_decided")
_TIMEOUT_SECONDS = 5
_RETRY_DELAY_SECONDS = 2
_SUMMARY_CHARS = 280

# Two workers: deliveries are rare and small, and a stuck endpoint should not
# be able to start an unbounded number of threads.
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="webhook")

_LABELS = {
    "de": {
        "published": "Neu veröffentlicht",
        "updated": "Aktualisiert",
        "unpublished": "Zurückgezogen",
        "review_requested": "Wartet auf Freigabe",
        "approved": "Freigegeben",
        "changes_requested": "Änderungen angefordert",
    },
    "en": {
        "published": "Published",
        "updated": "Updated",
        "unpublished": "Unpublished",
        "review_requested": "Waiting for approval",
        "approved": "Approved",
        "changes_requested": "Changes requested",
    },
}
_DISCORD_COLOURS = {
    "published": 0x16A34A,
    "updated": 0x4F6DF5,
    "unpublished": 0x6B7280,
    "review_requested": 0x0EA5E9,
    "approved": 0x16A34A,
    "changes_requested": 0xDC2626,
}


def is_enabled() -> bool:
    return bool(settings.webhook_urls)


def notify(
    event: str, page: dict, project: dict, category: dict | None = None, review: dict | None = None
) -> None:
    """Queue one event for every configured URL. Returns at once. `review`
    is the review events' own part: {"kind": "new"|"change"} for a request,
    {"decision": "approved"|"changes_requested"} for a decision."""
    if event not in EVENTS or event not in settings.webhook_events or not settings.webhook_urls:
        return
    # Never about a private project: the channel's members are unknown
    # (services/visibility.py).
    if project.get("private"):
        return
    data = _event_data(event, page, project, category)
    if event in _REVIEW_EVENTS:
        # Not published, so not announced: no summary, and the public URL
        # only when the page is live (it is, for a change to a live page).
        data["page"]["summary"] = ""
        if not page.get("published"):
            data["page"]["url"] = ""
        data["review"] = dict(review or {})
        data["admin_url"] = f"{settings.public_base_url}/admin" if settings.public_base_url else ""
    for url in settings.webhook_urls:
        _pool.submit(_deliver, url, event, data)


def _event_data(event: str, page: dict, project: dict, category: dict | None) -> dict:
    from app.services import prose, snippets  # local: only needed here

    body = snippets.resolve(
        page.get("markdown_content", ""), project.get("slug", ""), page.get("version", ""), page.get("language", "")
    )
    return {
        "event": event,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "page": {
            "title": page.get("title", ""),
            "slug": page.get("slug", ""),
            "language": page.get("language", ""),
            "version": page.get("version", ""),
            "summary": prose.first_paragraph(body, _SUMMARY_CHARS),
            "url": page_url(page, project),
        },
        "project": {"name": project.get("name", ""), "slug": project.get("slug", "")},
        "category": {"name": category.get("name", ""), "slug": category.get("slug", "")} if category else None,
    }


def page_url(page: dict, project: dict) -> str:
    """The page's public address, or "" when PUBLIC_BASE_URL is not set --
    the same shape the site itself uses: language prefix on a multilingual
    instance, version segment only for a non-default version."""
    if not settings.public_base_url:
        return ""
    from app.services import content_versions, site_languages

    version = page.get("version", "") or ""
    default = content_versions.default_version(project.get("slug", ""))
    segments = ["p", project.get("slug", "")]
    if version and version != default:
        segments.append(version)
    segments += ["pages", page.get("slug", "")]
    lang = page.get("language", "") or site_languages.default_language()
    prefix = f"/{lang}" if site_languages.is_multilingual() else ""
    return settings.public_base_url + prefix + "".join(f"/{quote(s, safe='')}" for s in segments if s)


# ---- Formats ----


def _kind(url: str) -> str:
    host = url.split("://", 1)[-1].split("/", 1)[0].lower()
    if host.endswith("discord.com") or host.endswith("discordapp.com"):
        return "discord"
    if host == "hooks.slack.com":
        return "slack"
    return "json"


def _label_key(event: str, data: dict) -> str:
    """What the message says happened: a decision is named by its outcome."""
    if event == "review_decided":
        return data.get("review", {}).get("decision") or "approved"
    return event


def _label(key: str) -> str:
    from app.services import site_languages

    lang = "de" if site_languages.default_language().startswith("de") else "en"
    return _LABELS[lang][key]


def build_body(url: str, event: str, data: dict) -> dict:
    page, project = data["page"], data["project"]
    key = _label_key(event, data)
    label = _label(key)
    link = page["url"] or data.get("admin_url", "")
    if _kind(url) == "discord":
        embed = {
            "title": page["title"][:256],
            "description": page["summary"][:2000],
            "color": _DISCORD_COLOURS[key],
            "footer": {"text": project["name"][:2048]},
        }
        if link:
            embed["url"] = link
        # allowed_mentions empty: a page title containing "@everyone" must not
        # ping a whole server.
        return {"content": f"**{label}**", "embeds": [embed], "allowed_mentions": {"parse": []}}
    if _kind(url) == "slack":
        title = f"<{link}|{_slack_escape(page['title'])}>" if link else _slack_escape(page["title"])
        return {"text": f"*{label}:* {title} ({_slack_escape(project['name'])})"}
    return data


def _slack_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---- Delivery ----


def _deliver(url: str, event: str, data: dict) -> None:
    body = json.dumps(build_body(url, event, data), ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "DocuWaves-Webhook"}
    if _kind(url) == "json":
        headers["X-DocuWaves-Event"] = event
        if settings.webhook_secret:
            headers["X-DocuWaves-Signature"] = "sha256=" + sign(body)
    for attempt in (1, 2):
        try:
            response = requests.post(url, data=body, headers=headers, timeout=_TIMEOUT_SECONDS)
            if response.status_code < 500:
                if response.status_code >= 400:
                    log.warning("Webhook %s answered %s for %s", _redacted(url), response.status_code, event)
                return
        except requests.RequestException as exc:
            if attempt == 2:
                log.warning("Webhook %s failed for %s: %s", _redacted(url), event, type(exc).__name__)
                return
        if attempt == 1:
            time.sleep(_RETRY_DELAY_SECONDS)
    log.warning("Webhook %s kept failing for %s", _redacted(url), event)


def sign(body: bytes) -> str:
    """HMAC-SHA256 of the exact bytes sent, hex. A receiver recomputes it
    with the shared WEBHOOK_SECRET to know the message is really from here."""
    return hmac.new(settings.webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _redacted(url: str) -> str:
    """The host only: the path of a Discord or Slack webhook IS its secret,
    and logs get pasted into issue threads."""
    return url.split("://", 1)[-1].split("/", 1)[0]
