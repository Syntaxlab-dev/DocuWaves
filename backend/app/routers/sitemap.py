# GET and HEAD: FastAPI's @get registers only GET, unlike a plain Starlette
# route, so HEAD answered 405 everywhere. Crawlers HEAD a sitemap before
# fetching it and uptime monitors default to HEAD, and a 405 reads as a
# broken endpoint rather than a healthy one.
"""The two files a crawler looks for before it looks at anything else:
/sitemap.xml and /robots.txt.

Both sit at the site ROOT rather than under /api/public/*, because that is
the only place either is ever fetched from -- a sitemap at another address
is a sitemap nothing reads. They are registered before main.py's catch-all
SPA route, so `/sitemap.xml` answers with XML instead of the app shell (and
without them it would 404 outright: main.py's scanner-path rule already
refuses to hand HTML to anything asking for a `.xml`).

What the sitemap contains, and why:

- The DEFAULT version of each project only. Every other version is either
  canonicalized onto the default one or marked noindex (see services/seo.py)
  -- listing them here would be inviting a crawler to index exactly the
  pages that were just told not to be indexed.
- Every published page, plus the pages a reader navigates through to reach
  them: the home page, each project's landing page, and each category that
  has something published in it. Those are real, indexable pages that
  readers land on and link to; a sitemap that omitted them would leave the
  site's own structure to be discovered by luck.
- Nothing unpublished. The one query this is built on filters on
  published (pages_store.published_variants), so a draft cannot appear here
  by any path -- this file is public, and a leaked slug is a leaked page.
- One URL per configured language, because on a multilingual instance every
  one of those addresses serves the page (with a fallback notice when there
  is no translation yet, never a 404), and each carries the `lastmod` of the
  file that language is actually served from.

Cost. This is a public URL that anything may request at any time, so it is
built for a big instance rather than for the demo one: one query per project
(not per category, not per page), ONE git invocation for every date in the
document (git_content_repo.last_modified_map), and the response is streamed
so a large site is never assembled in memory as one string.
"""

from xml.sax.saxutils import escape

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

from app.services import content_versions, git_content_repo, pages_store, projects_store, seo, site_languages

router = APIRouter(tags=["public"])

# The sitemap protocol's own ceiling per file. A site this big should be
# split across a sitemap index, which is a feature for the instance that
# ever gets there -- stopping at the limit keeps the document VALID in the
# meantime, where writing 60,000 URLs into it would not be.
_MAX_URLS = 50_000

# Both files are cheap to regenerate and change only when content does. An
# hour keeps a crawler that refetches the sitemap on every crawl from
# rebuilding it each time, and is short enough that a page published this
# morning is in it by lunch.
_CACHE = "public, max-age=3600"


def _url_element(loc: str, lastmod: str) -> str:
    """One <url>. `loc` is escaped even though every URL built by seo.py is
    already percent-encoded: this is the file's only writer, and an escape
    that is unnecessary today is the one nobody adds when a raw string
    starts arriving here tomorrow.

    `lastmod` is a plain YYYY-MM-DD -- a valid W3C date, and deliberately
    not the timestamp git holds: the public site never says more than the
    date a page changed (see pages_store.last_updated), and a sitemap
    carrying the exact minute of a commit would say it anyway."""
    date = f"    <lastmod>{lastmod}</lastmod>\n" if lastmod else ""
    return f"  <url>\n    <loc>{escape(loc)}</loc>\n{date}  </url>\n"


def _languages() -> list[str]:
    """The languages to emit each URL in. `[""]` -- one unprefixed URL per
    page -- on an instance that configured none, which is the whole document
    such an instance had before any of this existed."""
    return site_languages.languages() or [""]


def _project_entries(base: str, project: dict, dates: dict[str, str], languages: list[str]):
    """Every URL for one project, newest-relevant-date first computed for
    the whole project before anything is emitted.

    A category's date is the newest of its pages' and a project's is the
    newest of all of them, because that is what those two pages ARE: a list
    of what is under them, which changes exactly when one of those things
    does. Buffering one project's rows to work that out is what keeps this
    streamable -- memory is bounded by the biggest single project, not by
    the site.

    `languages` is passed in rather than read here: it is the same list for
    the whole document, and asking for it once per URL was measurably the
    most expensive single thing this generator did on a large instance."""
    slug = project["slug"]
    version = content_versions.default_version(slug)
    rows = pages_store.published_variants(project["id"], version)
    if not rows:
        # No published pages means no project tile on the home page and no
        # category worth listing -- the project exists in the repo but has
        # nothing a visitor may read yet.
        return

    # (category slug, page slug) -> the languages it is published in, in the
    # order the query returned them (navigation order).
    pages: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        pages.setdefault((row["category_slug"], row["slug"]), []).append(row["language"])

    # Per page AND per language, because `/de/...` and `/en/...` are not
    # always the same file: a page with no German translation is served in
    # English at its German address, so the German URL's date is the English
    # file's -- the date of what a reader at that URL actually gets. The
    # resolution is pages_store's own (served_language), not a second guess
    # at it here.
    page_dates: dict[tuple[str, str], dict[str, str]] = {}
    for (category_slug, page_slug), published_in in pages.items():
        per_language = {}
        for language in languages:
            served = pages_store.served_language(published_in, language)
            path = seo.page_file(slug, category_slug, page_slug, served, version)
            per_language[language] = dates.get(path, "")[:10]
        page_dates[(category_slug, page_slug)] = per_language

    category_dates: dict[str, str] = {}
    for (category_slug, _), per_language in page_dates.items():
        category_dates[category_slug] = max(category_dates.get(category_slug, ""), *per_language.values())
    project_date = max(category_dates.values(), default="")

    for language in languages:
        yield seo.section_url(base, language, slug, version, version), project_date
    for category_slug, date in category_dates.items():
        for language in languages:
            yield seo.section_url(base, language, slug, version, version, category_slug), date
    for (category_slug, page_slug), per_language in page_dates.items():
        for language, date in per_language.items():
            yield seo.page_url(base, language, slug, version, version, page_slug), date


def _entries(base: str):
    # The home page carries no lastmod: it is the project list, and "when
    # did the list of projects last change" is not something anything here
    # knows. A date guessed from somewhere else would be worse than the
    # element simply not being there, which the protocol allows.
    languages = _languages()
    for language in languages:
        yield seo.home_url(base, language), ""
    # One git call for every date in the document, before the first project
    # is touched. Empty on an instance with no content repo configured, in
    # which case the sitemap is a correct document with no lastmod in it.
    dates = git_content_repo.last_modified_map()
    # published_only, matching the public project list: a project with
    # nothing published has no page a crawler could reach, and listing its
    # landing URL would offer a search engine an empty page.
    for project in projects_store.list_projects(published_only=True):
        yield from _project_entries(base, project, dates, languages)


def _document(base: str):
    yield '<?xml version="1.0" encoding="UTF-8"?>\n'
    yield '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for index, (loc, lastmod) in enumerate(_entries(base)):
        if index >= _MAX_URLS:
            break
        yield _url_element(loc, lastmod)
    yield "</urlset>\n"


@router.api_route(
    "/sitemap.xml",
    methods=["GET", "HEAD"],
    summary="Every published page, for search engines",
    description="The default version of every project, in every configured content language, with the date "
    "each page's file last changed in the content repo. Drafts never appear. An instance with no content (or "
    "no content repo connected at all) answers with a valid document holding just the home page.",
    response_class=StreamingResponse,
)
def sitemap(request: Request) -> StreamingResponse:
    base = seo.public_base_url(request)
    return StreamingResponse(
        _document(base),
        media_type="application/xml",
        headers={"Cache-Control": _CACHE},
    )


# `Disallow: /api/` rather than `/api`: the trailing slash keeps it to the
# API and leaves any future path that merely starts with those letters alone.
#
# The search page and the app's 404 are deliberately NOT disallowed here.
# They carry `noindex` in their own <head> (see services/seo.py), and a
# crawler has to be allowed to FETCH a page to see that it says noindex --
# blocking it here would leave those URLs indexable-by-hearsay, which is the
# opposite of what blocking them looks like it does.
# /preview is a draft behind a link somebody shared with a named person. The
# app already answers those URLs with a noindex (seo.parse_route reads them
# as `other`), so this line is the second of two independent statements
# rather than the only one -- and it is the one a crawler reads before it
# ever fetches the page.
_ROBOTS = """User-agent: *
Allow: /
Disallow: /admin
Disallow: /preview
Disallow: /api/

Sitemap: {base}/sitemap.xml
"""


@router.api_route(
    "/robots.txt",
    methods=["GET", "HEAD"],
    summary="Crawl rules for the public site",
    description="Allows the documentation, keeps crawlers out of the admin area and the API, and points at "
    "/sitemap.xml at this instance's real public address.",
    response_class=PlainTextResponse,
)
def robots(request: Request) -> PlainTextResponse:
    return PlainTextResponse(
        _ROBOTS.format(base=seo.public_base_url(request)),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": _CACHE},
    )
