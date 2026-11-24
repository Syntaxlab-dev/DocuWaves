"""Tell another service when documentation changes: a Discord, Slack,
Microsoft Teams or Matrix channel, or any URL that accepts JSON.

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
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

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
        "open": "Seite öffnen",
    },
    "en": {
        "published": "Published",
        "updated": "Updated",
        "unpublished": "Unpublished",
        "review_requested": "Waiting for approval",
        "approved": "Approved",
        "changes_requested": "Changes requested",
        "open": "Open the page",
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

# Adaptive Card colour names for the label line in Teams.
_TEAMS_COLOURS = {
    "published": "Good",
    "updated": "Accent",
    "unpublished": "Default",
    "review_requested": "Accent",
    "approved": "Good",
    "changes_requested": "Attention",
}


def is_enabled() -> bool:
    return bool(settings.webhook_urls)


def notify(
    event: str,
    page: dict,
    project: dict,
    category: dict | None = None,
    review: dict | None = None,
    *,
    actor: str = "",
    submitter: str = "",
    comment: str = "",
) -> None:
    """Queue one event for every configured URL. Returns at once. `review`
    is the review events' own part: {"kind": "new"|"change"} for a request,
    {"decision": "approved"|"changes_requested"} for a decision.

    The same event goes to the e-mail notifications first
    (services/mail_notifications.py), which have their own rules -- private
    projects included, since every recipient is an account that may read
    them. `actor` (who did it), `submitter` (whose submission was decided)
    and `comment` (a reviewer's) are for those messages only: none of them
    is ever put into a webhook's payload."""
    from app.services import mail_notifications

    mail_notifications.notify(event, page, project, review, actor, submitter, comment)
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


_FORMATS = ("discord", "slack", "teams", "matrix", "json")


def _target(url: str) -> tuple[str, str]:
    """(format, the address to send to). The format follows the host, or a
    fragment naming it (`https://hookshot.example.org/webhook/abc#matrix`)
    for a service whose address does not give it away. The fragment is
    taken off: it was never meant for the receiving server."""
    address, _, fragment = url.partition("#")
    if fragment.lower() in _FORMATS:
        return fragment.lower(), address
    parts = urlsplit(address)
    host = (parts.hostname or "").lower()
    if host.endswith("discord.com") or host.endswith("discordapp.com"):
        return "discord", address
    if host == "hooks.slack.com":
        return "slack", address
    # Teams: the old "Incoming Webhook" connectors (*.webhook.office.com) and
    # the Workflows that replace them (Power Automate, on logic.azure.com or
    # *.api.powerplatform.com). Both take the same Adaptive Card message.
    if (
        host.endswith(".webhook.office.com")
        or host.endswith(".logic.azure.com")
        or host.endswith(".api.powerplatform.com")
    ):
        return "teams", address
    if "/_matrix/client/" in parts.path:
        return "matrix", address
    return "json", address


def _kind(url: str) -> str:
    return _target(url)[0]


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
    if _kind(url) == "teams":
        return _teams_body(key, label, page, project, link)
    if _kind(url) == "matrix":
        return _matrix_body(label, page, project, link)
    return data


def _teams_body(key: str, label: str, page: dict, project: dict, link: str) -> dict:
    """A message holding one Adaptive Card, the format both Teams' Workflows
    and its older connectors accept."""
    body = [
        {"type": "TextBlock", "text": label, "weight": "Bolder", "color": _TEAMS_COLOURS[key], "spacing": "None"},
        {"type": "TextBlock", "text": page["title"], "size": "Large", "weight": "Bolder", "wrap": True},
    ]
    if page["summary"]:
        body.append({"type": "TextBlock", "text": page["summary"], "wrap": True})
    body.append({"type": "TextBlock", "text": project["name"], "isSubtle": True, "size": "Small", "wrap": True})
    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
    }
    if link:
        card["actions"] = [{"type": "Action.OpenUrl", "title": _label("open"), "url": link}]
    return {
        "type": "message",
        "attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}
        ],
    }


def _matrix_body(label: str, page: dict, project: dict, link: str) -> dict:
    """An m.notice -- the message type meant for bots, which clients do not
    treat as a person talking -- with an HTML version for clients that show
    it. The same body suits a Hookshot generic webhook, which reads `text`
    and `html`."""
    title, name = page["title"], project["name"]
    plain = f"{label}: {title} ({name})" + (f" {link}" if link else "")
    linked = f'<a href="{_html(link)}">{_html(title)}</a>' if link else _html(title)
    html = f"<b>{_html(label)}:</b> {linked} ({_html(name)})"
    if page["summary"]:
        plain += "\n" + page["summary"]
        html += f"<br>{_html(page['summary'])}"
    return {
        "msgtype": "m.notice",
        "body": plain,
        "format": "org.matrix.custom.html",
        "formatted_body": html,
        "text": plain,
        "html": html,
    }


def _html(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _slack_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---- Delivery ----


def _matrix_request(address: str, headers: dict) -> tuple[str, str]:
    """(method, address) for Matrix's client-server API: a PUT to
    .../send/m.room.message/<transaction id>. The transaction id is made
    once per delivery, so the retry below cannot post the message twice.
    An access token in the query (`?access_token=`, the form a room's
    address is easiest to paste in) moves into the Authorization header,
    where the spec wants it."""
    parts = urlsplit(address)
    query = parse_qsl(parts.query, keep_blank_values=True)
    token = next((v for k, v in query if k == "access_token"), "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        query = [(k, v) for k, v in query if k != "access_token"]
    path = parts.path.rstrip("/")
    if path.endswith("/send/m.room.message"):
        path += "/" + uuid.uuid4().hex
    elif path.endswith("/send"):
        path += "/m.room.message/" + uuid.uuid4().hex
    return "PUT", urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))


def _deliver(url: str, event: str, data: dict) -> None:
    kind, address = _target(url)
    body = json.dumps(build_body(url, event, data), ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "DocuWaves-Webhook"}
    method = "POST"
    if kind == "json":
        headers["X-DocuWaves-Event"] = event
        if settings.webhook_secret:
            headers["X-DocuWaves-Signature"] = "sha256=" + sign(body)
    if kind == "matrix" and "/_matrix/client/" in address:
        method, address = _matrix_request(address, headers)
    for attempt in (1, 2):
        try:
            response = requests.request(method, address, data=body, headers=headers, timeout=_TIMEOUT_SECONDS)
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
    """The host only: the path of a Discord, Slack or Teams webhook IS its
    secret (and a Matrix address may carry a token), and logs get pasted
    into issue threads."""
    return url.split("://", 1)[-1].split("/", 1)[0]
