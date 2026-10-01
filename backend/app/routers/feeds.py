"""RSS feeds of the changelog: /feed.xml for the whole site and
/p/<project>/feed.xml for one project, `?lang=` for a language other than
the default one.

Root paths rather than /api/public/*, for the same reason as the sitemap:
a feed URL is something people paste into a reader, and it should read like
the site it belongs to. Registered before main.py's catch-all SPA route.

RSS 2.0 rather than Atom: it is what every reader, every "subscribe" button
and every chat integration (Slack's /feed, Discord bots, Mattermost)
understands without asking. The items are the changelog's own (services/
changelog.py) -- published pages only, never an author or commit message.
"""
from email.utils import format_datetime
from datetime import datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from app.services import changelog, content_versions, projects_store, seo, site_branding, site_languages

router = APIRouter(tags=["public"])

_ITEMS = 30
_CACHE = "public, max-age=900"

_LABELS = {
    "de": {"new": "Neu", "updated": "Aktualisiert", "title": "Neu & aktualisiert"},
    "en": {"new": "New", "updated": "Updated", "title": "New & updated"},
}


def _language(lang: str | None) -> str:
    if lang and lang in site_languages.languages():
        return lang
    return site_languages.default_language()


def _labels(language: str) -> dict:
    return _LABELS["de" if (language or "").startswith("de") else "en"]


def _rfc822(timestamp: str) -> str:
    try:
        return format_datetime(datetime.fromisoformat(timestamp))
    except ValueError:
        return ""


def feed_xml(base: str, language: str, project: dict | None) -> str:
    branding = site_branding.read_branding()
    site_name = site_languages.pick(branding["name"], branding.get("name_i18n") or {}, language)
    labels = _labels(language)
    lang_prefix = language if site_languages.is_multilingual() else ""
    if project:
        default = content_versions.default_version(project["slug"])
        title = f"{project['name']} – {labels['title']}"
        home = seo.section_url(base, lang_prefix, project["slug"], default, default)
    else:
        title = f"{site_name} – {labels['title']}"
        home = seo.home_url(base, lang_prefix)

    items = []
    for entry in changelog.entries(language, project["slug"] if project else "", limit=_ITEMS):
        default = content_versions.default_version(entry["project_slug"])
        link = seo.page_url(base, lang_prefix, entry["project_slug"], default, default, entry["page_slug"])
        # The guid changes with the date, so an update is a NEW item to a feed
        # reader -- the same guid would be taken as "already read".
        guid = f"{link}#{entry['kind']}-{entry['date']}"
        items.append(
            "    <item>\n"
            f"      <title>{escape(labels[entry['kind']])}: {escape(entry['title'])}</title>\n"
            f"      <link>{escape(link)}</link>\n"
            f'      <guid isPermaLink="false">{escape(guid)}</guid>\n'
            f"      <pubDate>{_rfc822(entry['timestamp'])}</pubDate>\n"
            f"      <category>{escape(entry['project_name'])} / {escape(entry['category_name'])}</category>\n"
            f"      <description>{escape(entry['summary'])}</description>\n"
            "    </item>\n"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        "  <channel>\n"
        f"    <title>{escape(title)}</title>\n"
        f"    <link>{escape(home)}</link>\n"
        f"    <description>{escape(title)}</description>\n"
        + (f"    <language>{escape(language)}</language>\n" if language else "")
        + "".join(items)
        + "  </channel>\n</rss>\n"
    )


def _response(body: str) -> Response:
    return Response(body, media_type="application/rss+xml; charset=utf-8", headers={"Cache-Control": _CACHE})


@router.api_route("/feed.xml", methods=["GET", "HEAD"], summary="RSS feed: new and updated pages, whole site")
def site_feed(request: Request, lang: str | None = Query(default=None, max_length=20)):
    return _response(feed_xml(seo.public_base_url(request), _language(lang), None))


@router.api_route(
    "/p/{project_slug}/feed.xml", methods=["GET", "HEAD"], summary="RSS feed: new and updated pages, one project"
)
def project_feed(project_slug: str, request: Request, lang: str | None = Query(default=None, max_length=20)):
    language = _language(lang)
    project = projects_store.get_project_by_slug(project_slug, language)
    # A private project has no feed: feed readers never sign in, and what is
    # in a feed reader stays there (services/visibility.py).
    if project is None or project.get("private"):
        raise HTTPException(status_code=404, detail="Project not found.")
    return _response(feed_xml(seo.public_base_url(request), language, project))
