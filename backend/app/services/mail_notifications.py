"""E-mail to the people who work on the documentation, when something they
care about happens. Each account chooses for itself, under Account, from
three kinds:

    review_requested   a page (or a change to a live page) waits for
                       approval -- to every account that can open the admin
                       area, except whoever submitted it
    review_decided     your submission was approved or sent back -- to the
                       person who submitted it
    changed            a page was published, changed while live, or taken
                       off the site -- to every account that wants it,
                       except whoever made the change

Nothing is sent unless the instance has an SMTP server (services/mailer.py)
and the account has an address and has ticked the box: no account is
signed up for anything by default.

WHAT A MESSAGE SAYS. The page's title, its project, what happened, who did
it (these are colleagues, who see that in the activity feed anyway), the
reviewer's comment for a page sent back, and links: the public page when it
is live and PUBLIC_BASE_URL is set, the admin area otherwise. Never the
page's text: a mailbox is a copy nobody can take back, and a draft that is
not approved yet is exactly what should not have one.

Webhooks (services/webhooks.py) are the other way out for the same events,
and are called from the same places -- that function hands each event here.
"""
import logging

from app.services import mailer, users_store
from app.settings import settings

log = logging.getLogger("docuwaves")

KINDS = ("review_requested", "review_decided", "changed")
_CHANGE_EVENTS = ("published", "updated", "unpublished")

_TEXT = {
    "de": {
        "review_requested": "Wartet auf Freigabe",
        "approved": "Freigegeben",
        "changes_requested": "Änderungen angefordert",
        "published": "Neu veröffentlicht",
        "updated": "Aktualisiert",
        "unpublished": "Zurückgezogen",
        "by": "von",
        "project": "Projekt",
        "comment": "Kommentar",
        "open": "Öffnen",
        "footer": "Diese Benachrichtigung kannst du in DocuWaves unter „Konto“ abbestellen.",
    },
    "en": {
        "review_requested": "Waiting for approval",
        "approved": "Approved",
        "changes_requested": "Changes requested",
        "published": "Published",
        "updated": "Updated",
        "unpublished": "Unpublished",
        "by": "by",
        "project": "Project",
        "comment": "Comment",
        "open": "Open",
        "footer": "You can turn this notification off in DocuWaves under Account.",
    },
}


def _lang() -> str:
    from app.services import site_languages

    return "de" if site_languages.default_language().startswith("de") else "en"


def _link(event: str, page: dict, project: dict) -> str:
    from app.services import webhooks

    if page.get("published") and event != "unpublished":
        url = webhooks.page_url(page, project)
        if url:
            return url
    return f"{settings.public_base_url}/admin" if settings.public_base_url else ""


def compose(key: str, event: str, page: dict, project: dict, actor: str, comment: str = "") -> tuple[str, str]:
    """(subject, text) of one notification."""
    t = _TEXT[_lang()]
    title = page.get("title", "")
    subject = f"{t[key]}: {title} ({project.get('name', '')})"
    lines = [f"{t[key]}: {title}", f"{t['project']}: {project.get('name', '')}"]
    if actor:
        lines[0] += f" ({t['by']} {actor})"
    if comment:
        lines += ["", f"{t['comment']}:", comment]
    link = _link(event, page, project)
    if link:
        lines += ["", f"{t['open']}: {link}"]
    lines += ["", "-- ", t["footer"]]
    return subject, "\n".join(lines) + "\n"


def recipients(kind: str, exclude: str = "") -> list[dict]:
    """Accounts that asked for this kind and have an address. Only accounts
    that can open the admin area: a reader account's business is reading
    the site, not drafts waiting for approval."""
    return [
        account
        for account in users_store.notification_accounts()
        if kind in account["notify"]
        and account["email"]
        and account["username"] != exclude
        and users_store.may_open_admin(account["role"])
    ]


def notify(
    event: str,
    page: dict,
    project: dict,
    review: dict | None = None,
    actor: str = "",
    submitter: str = "",
    comment: str = "",
) -> None:
    """One event, as webhooks.notify received it. Never raises: a broken
    notification must not fail the save that caused it."""
    if not mailer.is_enabled():
        return
    try:
        _notify(event, page, project, review or {}, actor, submitter, comment)
    except Exception:  # noqa: BLE001
        log.exception("E-mail notification for %s failed", event)


def _notify(event: str, page: dict, project: dict, review: dict, actor: str, submitter: str, comment: str) -> None:
    if event == "review_requested":
        subject, text = compose("review_requested", event, page, project, actor)
        for account in recipients("review_requested", exclude=actor):
            mailer.send(account["email"], subject, text)
    elif event == "review_decided":
        if not submitter or submitter == actor:
            return
        key = review.get("decision") or "approved"
        subject, text = compose(key, event, page, project, actor, comment)
        for account in recipients("review_decided"):
            if account["username"] == submitter:
                mailer.send(account["email"], subject, text)
    elif event in _CHANGE_EVENTS:
        subject, text = compose(event, event, page, project, actor)
        for account in recipients("changed", exclude=actor):
            mailer.send(account["email"], subject, text)
