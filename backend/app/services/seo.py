"""Real <head> metadata for the public documentation site, written into the
SPA shell by the SERVER before it ever leaves the process.

Why this module exists: the reader-facing site is a single-page app, so the
server answers every reading URL with the same index.html and React fills it
in from /api/public/*. That is fine for a reader with a browser and useless
for everything else that ever looks at a documentation URL:

- A search engine that does not execute JavaScript (and every crawler's FIRST
  pass, Google's included) sees one shell, so every page of the site has the
  same title and no description at all.
- A link-preview crawler -- Discord, Slack, WhatsApp, Signal, Mastodon --
  runs no JavaScript ever. Someone sharing a link to the installation guide
  got a card saying nothing but the site's name, whichever page they linked.

So the shell is patched on its way out: <title>, description, Open Graph and
Twitter card, canonical, hreflang alternates and JSON-LD, built from the same
stores the page's own API call reads a moment later. The SPA is untouched by
this -- it still sets its own title on navigation (lib/site.tsx's
useDocumentTitle), and everything injected here is simply the correct answer
for the FIRST response, which is the only response a crawler ever makes.

Three rules run through all of it:

- NEVER LEAK A DRAFT. Every lookup here goes through the same published-only
  path the public router uses, so an unpublished page produces exactly the
  site's default metadata -- the same nothing it produces as content today.
- COST. This runs on every single page view, so nothing that isn't needed is
  looked up: /admin injects nothing at all and pays not one query, the home
  page and any unknown URL pay only the already-mtime-cached _site.yml read,
  and only a real /p/... reading URL touches the database -- with the same
  handful of queries the view's own API call is about to make anyway. The
  shell itself is read from disk once and kept in memory, keyed by its
  mtime, and the injection is one string splice.
- ESCAPING. Titles and descriptions are author-controlled text from the
  content repo going into HTML attributes. Everything rendered here goes
  through html.escape(quote=True) -- so a page titled `Say "hi" <b>` cannot
  close an attribute -- and the JSON-LD goes through a JSON encoder plus a
  `<`/`>`/`&` escape, because JSON quoting alone would still let a </script>
  in a title end the script element.

Degrading rather than failing is the contract, exactly as it is for
_site.yml (see site_branding.py): render() catches everything and answers
None, and the caller then serves the untouched shell. Metadata is worth a
lot; it is not worth the public site.
"""

import html
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from app.services import (
    categories_store,
    content_files,
    content_versions,
    pages_store,
    projects_store,
    site_branding,
    site_languages,
)
from app.settings import settings

log = logging.getLogger("docuwaves")

# A meta description longer than this is cut by every search engine that
# shows one, and a link-preview card clips it sooner than that. Trimmed on a
# word boundary (see _clip) -- a description ending mid-word reads like the
# page is broken.
_DESCRIPTION_LIMIT = 160

# How far into a page's Markdown to look for its first line of prose. A page
# that opens with several screens of front matter, badges and a table of
# contents has no summary worth extracting anyway, and this keeps the work
# per request bounded by a constant rather than by the size of the longest
# page in the repo.
_MAX_SCAN_LINES = 400

# A URL segment longer than any real slug is not a slug. Bailing here keeps a
# crafted 4 KB path from reaching a LIKE-free but still pointless query.
_MAX_SEGMENT = 200


# ---- The public base URL ----
#
# Everything absolute below (canonical, og:url, the sitemap) is only as
# correct as this is, and getting it wrong is not hypothetical in this
# codebase: the OIDC redirect_uri was generated as http:// against a proxy
# terminating TLS, which a strict provider rejects outright (see the
# Dockerfile's --proxy-headers note). A canonical tag pointing at
# http://172.18.0.4:8000 fails more quietly and does more damage -- it tells
# every search engine that the real address of the page is one nobody can
# reach.
#
# Three sources, most trustworthy first:
#
# 1. PUBLIC_BASE_URL, if the operator set it. Nothing can beat being told.
# 2. X-Forwarded-Proto / X-Forwarded-Host, read here rather than relied upon
#    through request.base_url. uvicorn's --proxy-headers (which the image
#    already runs with) applies X-Forwarded-Proto but NOT X-Forwarded-Host,
#    so a proxy that rewrites Host to the internal name would otherwise
#    produce internal URLs; and reading the scheme here as well means an
#    operator running uvicorn without the flag still gets https.
# 3. The request's own scheme and Host header, which is exactly what the app
#    did before and is right for a direct hit on a LAN.
#
# Trusting a forwarded header is a decision the deployment already made:
# --forwarded-allow-ips=* is in the image's CMD, so anything that reaches
# this app is already trusted to name the client and the scheme. The host is
# still validated (below) so that a header holding a quote or a newline
# cannot travel into a URL.

_HOST_RE = re.compile(r"^(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])(?::\d{1,5})?$")


def _forwarded(request, name: str) -> str:
    """The client-most value of a possibly comma-joined X-Forwarded-* header
    ("https, http" when two proxies both appended). The first entry is the
    one nearest the reader, which is the public one."""
    raw = request.headers.get(name, "")
    return raw.split(",")[0].strip()


def public_base_url(request) -> str:
    """`https://docs.example.com` -- scheme and host, no trailing slash."""
    if settings.public_base_url:
        return settings.public_base_url

    scheme = _forwarded(request, "x-forwarded-proto") or request.url.scheme
    if scheme not in ("http", "https"):
        scheme = request.url.scheme
    host = _forwarded(request, "x-forwarded-host") or request.headers.get("host", "") or request.url.netloc
    if not _HOST_RE.match(host):
        host = request.url.netloc
    return f"{scheme}://{host}"


# ---- Which URL is this? ----
#
# A server-side mirror of frontend/src/App.tsx's route table. It has to match
# it exactly in both directions: a reading URL this doesn't recognize would
# be served the site's default metadata with a noindex on it (a real page
# dropped from search), and a URL this recognizes that the app does not would
# claim a page exists where the reader sees a 404.


@dataclass(frozen=True)
class Route:
    """`kind` is one of:

    admin     -- /admin*, which gets no metadata at all and costs nothing.
    home      -- the project list, prefixed or not.
    project / category / page -- the three reading views.
    other     -- /search, and anything matching no route (the app renders its
                 own 404 there). Site defaults plus noindex.
    """

    kind: str
    lang: str = ""
    project: str = ""
    version: str = ""
    category: str = ""
    page: str = ""


_ADMIN = Route("admin")
_OTHER = Route("other")

# The two fixed segments that sit where a version id would. They are refused
# as version ids on the way in (content_versions._RESERVED_IDS) precisely so
# that this can be told apart without ambiguity, the same way react-router
# ranks a literal segment above a dynamic one.
_FIXED_AFTER_PROJECT = ("c", "pages")


def parse_route(full_path: str) -> Route:
    segments = [s for s in full_path.split("/") if s]
    if any(len(s) > _MAX_SEGMENT for s in segments):
        return _OTHER
    if segments and segments[0] == "admin":
        return _ADMIN

    lang = ""
    # Only a CONFIGURED code counts as a prefix, and only on a multilingual
    # instance -- exactly lib/lang.tsx's own rule. `/de/p/x` on an instance
    # that has no `de` is a wrong URL (App.tsx's LanguageGate answers 404),
    # so it falls through to `other` here rather than being read as German.
    if segments and site_languages.is_multilingual() and segments[0] in site_languages.languages():
        lang = segments[0]
        segments = segments[1:]

    if not segments:
        return Route("home", lang)
    if segments[0] != "p" or len(segments) < 2:
        return Route("other", lang)

    project = segments[1]
    rest = segments[2:]
    version = ""
    if rest and rest[0] not in _FIXED_AFTER_PROJECT:
        version = rest[0]
        rest = rest[1:]

    if not rest:
        return Route("project", lang, project, version)
    if len(rest) == 2 and rest[0] == "c":
        return Route("category", lang, project, version, category=rest[1])
    if len(rest) == 2 and rest[0] == "pages":
        return Route("page", lang, project, version, page=rest[1])
    return Route("other", lang)


# ---- What to say about it ----


@dataclass
class Meta:
    site_name: str
    title: str
    description: str = ""
    canonical: str = ""
    image: str = ""
    og_type: str = "website"
    # The language of the CONTENT this response carries, for og:locale and
    # JSON-LD's inLanguage. Not always the URL's: a page with no translation
    # yet is served in the best language there is (pages_store.resolve_page),
    # and saying otherwise would label German text as English.
    language: str = ""
    # The language of the DOCUMENT as a whole -- <html lang> -- which is the
    # reader's, the one the URL asked for. It is what the header, the
    # navigation, the fallback notice and every button around the text are
    # written in, and lib/lang.tsx keeps it at exactly this value as the
    # reader navigates. Where the page's own text differs, that text carries
    # its own lang (PublicPage.tsx marks the body and the notice), which is
    # the right shape for "an English page containing a German article" and
    # keeps the server's first answer and the client's later ones identical.
    document_language: str = ""
    noindex: bool = False
    # (hreflang, absolute URL), including the x-default entry. Empty on a
    # single-language instance and on any page whose canonical points
    # somewhere else -- see _page_meta.
    alternates: list[tuple[str, str]] = field(default_factory=list)
    structured: list[dict] = field(default_factory=list)


def _language(lang: str) -> str:
    """The language actually served for a URL prefix -- the requested one
    when this instance has it, its default otherwise. Deliberately the same
    two lines as routers/public_content.py's `_language`, because the
    metadata has to describe the response the reader is about to get, not a
    second opinion about it."""
    if lang and lang in site_languages.languages():
        return lang
    return site_languages.default_language()


def _path(lang: str, *segments: str) -> str:
    """A public path with this instance's language prefix on the front and
    every segment percent-encoded. Slugs are slugified ASCII, but a category
    directory added by hand in the content repo is whatever someone named
    it, and that name must not be able to widen the path it lands in."""
    parts = [quote(s, safe="") for s in segments if s]
    prefix = f"/{lang}" if lang and site_languages.is_multilingual() else ""
    return prefix + "".join(f"/{p}" for p in parts)


def _absolute(base: str, url: str | None) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return base + url


def home_url(base: str, lang: str) -> str:
    """The site's front page. `https://host/` on a single-language instance,
    `https://host/de` on a multilingual one -- which is where an unprefixed
    URL lands there (lib/lang.tsx redirects to the default language), so it
    is the address that should be advertised rather than the one that
    bounces."""
    return base + _path(lang) if site_languages.is_multilingual() else base + "/"


def _version_segment(version: str, default: str) -> str:
    """Empty for the default version -- the addresses a project had before it
    was versioned are the addresses its default version keeps, which is the
    same rule lib/version.tsx's versionSegment() applies in the browser. Two
    URLs for one page would otherwise compete in search, and the one without
    the segment is the one every existing link points at."""
    return version if version and version != default else ""


def _alternates(base: str, tail: list[str]) -> list[tuple[str, str]]:
    """One entry per configured language plus x-default. Every one of these
    URLs is live: a language a page has no translation in still serves it,
    with a notice, rather than 404-ing (see pages_store.resolve_page), so
    every alternate points at a real page in the language it claims."""
    if not site_languages.is_multilingual():
        return []
    entries = [(code, base + _path(code, *tail)) for code in site_languages.languages()]
    entries.append(("x-default", base + _path(site_languages.default_language(), *tail)))
    return entries


def _defaults(base: str, lang: str, branding: dict, noindex: bool) -> Meta:
    """The site's own metadata and nothing else -- what the home page says
    about itself, and the ONLY thing an unknown URL, the search page or a URL
    naming a draft is allowed to say. No page title, no page description, no
    canonical: from out here those pages do not exist."""
    name = site_languages.pick(branding["name"], branding["name_i18n"], lang)
    return Meta(
        site_name=name,
        title=name,
        description=site_languages.pick(branding["tagline"], branding["tagline_i18n"], lang),
        image=_absolute(base, branding["logo_url"]),
        language=lang,
        document_language=lang,
        noindex=noindex,
    )


def _breadcrumbs(trail: list[tuple[str, str]]) -> dict:
    """project -> category -> page, with the site itself at the front.

    Built from the version the reader is ACTUALLY in, not from the canonical
    -- including the last entry, which is this page at the address that was
    asked for. A trail is a description of where a page sits, and a frozen
    version's page sits in that version: pointing its crumbs at the current
    version would name a category that release may not even have had."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": index, "name": name, "item": url}
            for index, (name, url) in enumerate(trail, start=1)
        ],
    }


def _home_meta(base: str, lang: str, branding: dict) -> Meta:
    meta = _defaults(base, lang, branding, noindex=False)
    meta.canonical = home_url(base, lang)
    meta.alternates = _alternates(base, [])
    meta.structured = [
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": meta.site_name,
            "url": meta.canonical,
            # Only when there is one. An empty description is left out
            # entirely rather than emitted as "" -- structured data that
            # says nothing should say nothing.
            **({"description": meta.description} if meta.description else {}),
        }
    ]
    return meta


def _project_context(route: Route, lang: str) -> tuple[dict, str, str] | None:
    """(project row, version to serve, the project's default version), or
    None when this URL is a 404 -- an unknown project, or a version the
    project doesn't have. Both mirror routers/public_content.py exactly: an
    unknown version is a 404 there, never a silent fall back to current."""
    project = projects_store.get_project_by_slug(route.project, lang)
    if project is None:
        return None
    default = content_versions.default_version(route.project)
    if route.version and route.version not in content_versions.version_ids(route.project):
        return None
    return project, (route.version or default), default


def _project_meta(base: str, route: Route, lang: str, branding: dict) -> Meta | None:
    context = _project_context(route, lang)
    if context is None:
        return None
    project, version, default = context

    meta = _defaults(base, lang, branding, noindex=False)
    meta.title = project["name"]
    meta.description = project["description"] or meta.description
    meta.image = _absolute(base, project["image_url"]) or meta.image
    # A frozen version's landing page is the same list of sections one
    # release earlier: near-duplicate content, pointed at the default
    # version's landing page, which always exists (a project exists in every
    # one of its versions), so this case never needs a noindex.
    here = _version_segment(version, default)
    tail = ["p", project["slug"]]
    meta.canonical = base + _path(lang, *tail)
    meta.alternates = [] if here else _alternates(base, tail)
    meta.structured = [
        _breadcrumbs(
            [(meta.site_name, home_url(base, lang)), (project["name"], base + _path(lang, "p", project["slug"], here))]
        )
    ]
    return meta


def _category_meta(base: str, route: Route, lang: str, branding: dict) -> Meta | None:
    context = _project_context(route, lang)
    if context is None:
        return None
    project, version, default = context
    category = categories_store.get_category_by_slug(project["id"], route.category, lang, version)
    if category is None:
        return None
    # A category with nothing published in it is a 404 on the public site --
    # PublicCategory.tsx renders NotFound for exactly this, because the
    # category exists in the content repo but holds nothing a visitor may
    # read. The metadata has to agree with the page.
    pages = pages_store.list_pages(category["id"], published_only=True, language=lang)
    if not pages:
        return None

    meta = _defaults(base, lang, branding, noindex=False)
    meta.title = category["name"]
    # A category has no description field of its own, and inventing a
    # sentence for it would be writing documentation. What it does have is
    # its contents, which is also what the page itself shows -- so the
    # description is the list of pages, in the order the reader sees them.
    meta.description = _clip(" · ".join(p["title"] for p in pages), _DESCRIPTION_LIMIT)
    meta.image = _absolute(base, category["image_url"]) or _absolute(base, project["image_url"]) or meta.image

    canonical_version = version
    if version != default and default in categories_store.category_versions(project["id"]).get(route.category, []):
        canonical_version = default
    here = _version_segment(version, default)
    tail = ["p", project["slug"], _version_segment(canonical_version, default), "c", category["slug"]]
    meta.canonical = base + _path(lang, *tail)
    # noindex only when this frozen category has no equivalent to point at
    # -- see _page_meta, where the same rule is spelled out in full.
    meta.noindex = canonical_version != default
    if canonical_version == version:
        meta.alternates = _alternates(base, tail)
    meta.structured = [
        _breadcrumbs(
            [
                (meta.site_name, home_url(base, lang)),
                (project["name"], base + _path(lang, "p", project["slug"], here)),
                (category["name"], base + _path(lang, "p", project["slug"], here, "c", category["slug"])),
            ],
        )
    ]
    return meta


def _page_meta(base: str, route: Route, lang: str, branding: dict) -> Meta | None:
    context = _project_context(route, lang)
    if context is None:
        return None
    project, version, default = context
    # published_only, exactly as the public router reads it: a draft is not a
    # page out here, so it produces no title and no description -- only the
    # site's defaults, which is the same nothing it produces as content.
    page = pages_store.resolve_page(project["id"], route.page, lang, published_only=True, version=version)
    if page is None:
        return None
    category = categories_store.get_category(page["category_id"], lang)
    if category is None:
        return None

    meta = _defaults(base, lang, branding, noindex=False)
    meta.title = page["title"]
    meta.og_type = "article"
    meta.description = _summarize(page["markdown_content"]) or meta.description
    # The language actually SERVED, which is not always the one in the URL:
    # a page with no translation yet is served in the best language there is
    # (with a notice on the page saying so). og:locale and inLanguage
    # describe the text that was sent, so a German URL serving the English
    # original says "en" -- claiming German for English text is the one
    # answer that is simply false. `document_language` stays the reader's;
    # see the Meta fields for the difference.
    meta.language = page["language"]
    meta.image = _absolute(base, category["image_url"]) or _absolute(base, project["image_url"]) or meta.image

    # ---- Old versions must not compete with the current one ----
    #
    # A frozen version's page is a near-duplicate of the current one: same
    # title, same topic, mostly the same words. Left alone, the two compete,
    # and the one search engines pick is decided by age and inbound links --
    # which is exactly how someone searching for the install guide lands on
    # the one for a release from two years ago.
    #
    # So a frozen page points its canonical at the DEFAULT version's copy of
    # the same page when that page is published there: same content, one
    # address, and every signal the old URL earned is credited to the page a
    # reader actually wants. Where there is no such page (a section that no
    # longer exists), there is nothing to point at, so it is marked
    # noindex,follow instead -- out of the index, still crawled, its links
    # still followed.
    #
    # Never both. A canonical pointing elsewhere AND a noindex is the one
    # combination that misfires: the noindex can be taken as applying to the
    # canonical target, which would remove the CURRENT page from search.
    # Frozen docs stay readable and reachable either way -- they are just not
    # what a search result should be.
    canonical_version = version
    if version != default and default in pages_store.page_versions(project["id"], route.page, published_only=True):
        canonical_version = default
    here = _version_segment(version, default)
    tail = ["p", project["slug"], _version_segment(canonical_version, default), "pages", page["slug"]]
    meta.canonical = base + _path(lang, *tail)
    meta.noindex = canonical_version != default
    # hreflang only on a page that is its own canonical. Every alternate has
    # to be self-canonical for the set to mean anything; a frozen page that
    # points elsewhere is described by the alternates the page it points at
    # emits.
    if canonical_version == version:
        meta.alternates = _alternates(base, tail)

    updated = pages_store.last_updated(project["slug"], category["slug"], page)[:10]
    article = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": page["title"],
        "url": meta.canonical,
        "isPartOf": {"@type": "WebSite", "name": meta.site_name, "url": home_url(base, lang)},
    }
    if meta.description:
        article["description"] = meta.description
    if meta.language:
        article["inLanguage"] = meta.language
    # dateModified only, and only from the content repo's log -- the same
    # source and the same YYYY-MM-DD cut the page's own "last updated" line
    # uses (pages_store.last_updated explains why the row's updated_at is
    # not that source, and why the exact minute of a commit stays private).
    # No datePublished and no author: a file's first commit is not the day
    # the page was written, and the content repo's author names are not
    # public. Structured data that guesses is worse than structured data
    # that is quiet.
    if updated:
        article["dateModified"] = updated
    if meta.image:
        article["image"] = meta.image

    meta.structured = [
        article,
        _breadcrumbs(
            [
                (meta.site_name, home_url(base, lang)),
                (project["name"], base + _path(lang, "p", project["slug"], here)),
                (category["name"], base + _path(lang, "p", project["slug"], here, "c", category["slug"])),
                (page["title"], base + _path(lang, "p", project["slug"], here, "pages", page["slug"])),
            ],
        ),
    ]
    return meta


_BUILDERS = {"project": _project_meta, "category": _category_meta, "page": _page_meta}


def build_meta(route: Route, base: str) -> Meta:
    branding = site_branding.read_branding()
    lang = _language(route.lang)
    if route.kind == "home":
        return _home_meta(base, lang, branding)
    builder = _BUILDERS.get(route.kind)
    if builder is not None:
        meta = builder(base, route, lang, branding)
        if meta is not None:
            return meta
    # `other` (the search page, an unknown URL), and every reading URL whose
    # slug resolves to nothing a visitor may read -- a draft, a deleted page,
    # a typo. All four render the app's own 404 or a page not worth
    # indexing, and all four say only what the site says about itself.
    return _defaults(base, lang, branding, noindex=True)


# ---- Turning a page's Markdown into a description ----


_FENCE_RE = re.compile(r"^\s{0,3}(?:```|~~~)")
_SKIP_RE = re.compile(
    r"^\s{0,3}(?:"
    r"#"  # heading
    r"|\|"  # table row
    r"|(?:[-*_]\s*){3,}$"  # thematic break
    r"|<"  # raw HTML, an HTML comment, a badge block
    r"|!\["  # an image (or a row of shield badges) on its own line
    r"|={2,}$"  # a setext underline that outran its heading
    r")"
)
_LIST_MARKER_RE = re.compile(r"^\s{0,3}(?:[-*+]\s+|\d+[.)]\s+|>\s?)+")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TAG_RE = re.compile(r"<[^>]{0,200}>")
_NOISE_RE = re.compile(r"[`*~]+")
_SPACE_RE = re.compile(r"\s+")


def _clip(text: str, limit: int) -> str:
    """Cut to `limit` on a word boundary, with an ellipsis. A single word
    longer than the limit is cut where it is -- better a hard cut than a
    description that is empty."""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[: limit + 1]
    cut = head.rsplit(" ", 1)[0] if " " in head else text[:limit]
    return cut.rstrip(" ,;:.-–—") + "…"


def _summarize(markdown: str) -> str:
    """A page's first paragraph of actual PROSE, as a plain sentence.

    "Prose" is defined by what it is not: not the title, not a heading, not
    inside a fenced code block (or a mermaid diagram, which is one), not a
    table, not a horizontal rule, not a row of badge images, not raw HTML.
    Those are what documentation pages open with, and any of them as a
    description would describe nothing.

    Blockquotes and list items DO count, with their markers stripped: plenty
    of good pages open with a callout or a list, and the first item of one
    still says more about the page than the site's tagline does."""
    lines: list[str] = []
    in_fence = False
    for index, raw in enumerate(markdown.splitlines()):
        if index >= _MAX_SCAN_LINES:
            break
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = raw.strip()
        if not line:
            # A blank line ends the paragraph once one has started, and is
            # simply skipped before that.
            if lines:
                break
            continue
        if _SKIP_RE.match(line):
            if lines:
                break
            continue
        lines.append(_LIST_MARKER_RE.sub("", line))

    if not lines:
        return ""
    text = " ".join(lines)
    text = _IMAGE_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)  # link text, without the URL
    text = _TAG_RE.sub("", text)
    # Backticks, ** and ~~ removed; `_` deliberately left alone, because it
    # is far more often part of an identifier (snake_case, a CLI flag) than
    # an emphasis marker, and eating it would corrupt the very words a
    # technical description exists to carry.
    text = _NOISE_RE.sub("", text)
    return _clip(_SPACE_RE.sub(" ", text), _DESCRIPTION_LIMIT)


# ---- Rendering ----


def _attr(value: str) -> str:
    """Author-controlled text on its way into an HTML attribute or element.
    quote=True is the whole point: it escapes " and ' as well as & < >, so a
    page titled `Say "hi"` cannot close the attribute it sits in."""
    return html.escape(value, quote=True)


def _tag(name: str, key: str, value: str) -> str:
    return f'<meta {name}="{_attr(key)}" content="{_attr(value)}" />'


def _json_ld(document: dict) -> str:
    """A JSON-LD block. JSON quoting alone is NOT enough inside a <script>:
    the HTML parser looks for `</script` before the JSON parser sees
    anything, so a page titled `</script><img onerror=...>` would end the
    element and inject markup. `<`, `>` and `&` are therefore re-encoded as
    JSON \\u escapes -- still exactly the same string to any JSON reader, and
    no longer markup to an HTML one. html.escape() must NOT be used here:
    &quot; inside JSON is a literal &quot;, not a quote."""
    text = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'<script type="application/ld+json">{text}</script>'


def render_head(meta: Meta) -> str:
    """The block of tags, one per line, ready to splice in before </head>."""
    title = f"{meta.title} · {meta.site_name}" if meta.title != meta.site_name else meta.site_name
    lines = [
        "<!-- Rendered server-side by DocuWaves (backend/app/services/seo.py) so that search",
        "     engines and link-preview crawlers, which run no JavaScript, see this page and",
        "     not just the app shell. The SPA keeps setting its own title as the reader navigates. -->",
        f"<title>{_attr(title)}</title>",
    ]
    if meta.description:
        lines.append(_tag("name", "description", meta.description))
    if meta.noindex:
        # follow, not none: an old version's pages are still the right way
        # into the rest of that version, and a 404 or a search page still
        # links back into the site.
        lines.append(_tag("name", "robots", "noindex, follow"))
    if meta.canonical:
        lines.append(f'<link rel="canonical" href="{_attr(meta.canonical)}" />')
    for code, url in meta.alternates:
        lines.append(f'<link rel="alternate" hreflang="{_attr(code)}" href="{_attr(url)}" />')

    lines.append(_tag("property", "og:type", meta.og_type))
    lines.append(_tag("property", "og:site_name", meta.site_name))
    lines.append(_tag("property", "og:title", title))
    if meta.description:
        lines.append(_tag("property", "og:description", meta.description))
    if meta.canonical:
        lines.append(_tag("property", "og:url", meta.canonical))
    if meta.image:
        lines.append(_tag("property", "og:image", meta.image))
    if meta.language:
        lines.append(_tag("property", "og:locale", meta.language))

    # summary_large_image only when there IS an image -- the card type is a
    # promise about what follows, and the plain summary card is what a site
    # with no logo should get.
    lines.append(_tag("name", "twitter:card", "summary_large_image" if meta.image else "summary"))
    lines.append(_tag("name", "twitter:title", title))
    if meta.description:
        lines.append(_tag("name", "twitter:description", meta.description))
    if meta.image:
        lines.append(_tag("name", "twitter:image", meta.image))

    lines.extend(_json_ld(document) for document in meta.structured)
    return "".join(f"    {line}\n" for line in lines)


# ---- Patching the shell ----

_TITLE_RE = re.compile(r"[ \t]*<title>.*?</title>\n?", re.IGNORECASE | re.DOTALL)
_HTML_LANG_RE = re.compile(r'(<html\b[^>]*?\blang=")[^"]*(")', re.IGNORECASE)

# index.html, with its placeholder <title> already removed, keyed by the
# file's mtime+size. It is read once per deploy rather than once per request
# -- the same identity-plus-mtime cache key site_languages and
# content_versions use for their own files, so a rebuilt bundle is picked up
# without a restart.
_shell: tuple[tuple, str] | None = None


def _index_shell(index: Path) -> str | None:
    global _shell
    try:
        stat = index.stat()
    except OSError:
        return None
    key = (stat.st_mtime_ns, stat.st_size)
    if _shell is not None and _shell[0] == key:
        return _shell[1]
    try:
        text = index.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if "</head>" not in text:
        return None
    # The bundle's own <title> is a placeholder (see frontend/index.html).
    # Removed rather than left in place: two <title> elements are legal HTML
    # and every consumer takes the FIRST, which would be the placeholder.
    text = _TITLE_RE.sub("", text, count=1)
    _shell = (key, text)
    return text


def render_index(index: Path, full_path: str, request) -> str | None:
    """index.html with this URL's metadata in its head, or None for "serve
    the file untouched" -- which is the answer for the admin area (no
    metadata, and no lookup to build any), for a bundle this can't read, and
    for anything at all that goes wrong on the way."""
    try:
        route = parse_route(full_path)
        if route.kind == "admin":
            return None
        shell = _index_shell(index)
        if shell is None:
            return None
        meta = build_meta(route, public_base_url(request))
        block = render_head(meta)
        cut = shell.index("</head>")
        patched = shell[:cut].rstrip(" \t") + block + "  " + shell[cut:]
        if meta.document_language:
            # The document's own language, which a screen reader and a
            # translation prompt both act on -- and which the built shell
            # hardcodes as "en". lib/lang.tsx sets exactly this same value on
            # every client-side navigation, so the first response and every
            # one after it agree.
            patched = _HTML_LANG_RE.sub(rf"\g<1>{meta.document_language}\g<2>", patched, count=1)
        return patched
    except Exception:
        # Deliberately broad, and deliberately quiet about it after the log
        # line: metadata is an improvement to a page, never a precondition
        # for serving it. Whatever went wrong -- an unreadable bundle, a
        # database that answered oddly -- the reader still gets the site.
        log.exception("Could not render metadata for %r; serving the plain app shell", full_path)
        return None


# ---- Shared with the sitemap ----


def page_url(base: str, lang: str, project_slug: str, version: str, default: str, page_slug: str) -> str:
    """The canonical address of one page, built by exactly the rules the
    metadata above uses -- so a URL in the sitemap is the URL the page names
    as its canonical, which is the one thing a sitemap must never get wrong."""
    return base + _path(lang, "p", project_slug, _version_segment(version, default), "pages", page_slug)


def section_url(base: str, lang: str, project_slug: str, version: str, default: str, category_slug: str = "") -> str:
    tail = ["p", project_slug, _version_segment(version, default)]
    if category_slug:
        tail += ["c", category_slug]
    return base + _path(lang, *tail)


def page_file(project_slug: str, category_slug: str, page_slug: str, language: str, version: str) -> str:
    """The repo-relative path of the file a URL is served from -- what the
    sitemap's lastmod is looked up by. Here rather than in the sitemap router
    so that "which file backs this URL" is answered in the same module that
    decides what the URL is."""
    return content_files.page_repo_path(project_slug, category_slug, page_slug, language, version)
