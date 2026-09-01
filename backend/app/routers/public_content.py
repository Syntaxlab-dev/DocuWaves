"""Read-only content endpoints for the public-facing site -- no
authentication (see auth_guard.py's unconditional /api/public/* exemption),
and every query here filters to published=True: an unpublished page must
never be reachable through this router by slug-guessing, only through the
admin endpoints.

Every content route takes an optional `lang`: the content language being
read, which the frontend takes from the URL's own `/de/...` prefix. It is
normalized here rather than trusted (_language()), so a hand-typed
`?lang=zz` reads the default language instead of returning nothing, and an
instance with no `languages:` configured ignores the parameter entirely and
answers exactly as it did before this existed.

A project's routes also take an optional `version`, from the URL's
`/p/<project>/v2.0/...` segment. Unlike `lang`, an unknown one is a 404
rather than a silent fall back to the default: `/p/x/v9.9/...` is a wrong
URL, and quietly serving current under an address that says 2.0 would be a
worse answer than saying it doesn't exist. A project with no `_versions.yml`
has no versions at all, so any version in its URL is a 404 by the same rule,
and every response for it is the response it always was -- plus one key,
`versions: null`, which is how the frontend knows not to render a switcher."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.services import (
    categories_store,
    content_assets,
    content_versions,
    pages_store,
    projects_store,
    site_branding,
    site_languages,
)

router = APIRouter(prefix="/api/public", tags=["public"])

_LANG_QUERY = Query(default=None, max_length=8, description="Content language; defaults to the site's first one.")
_VERSION_QUERY = Query(
    default=None,
    max_length=40,
    description="Documentation version; defaults to the project's own default version. 404 if unknown.",
)


def _language(lang: str | None) -> str:
    """The language to actually serve: the requested one when this instance
    has it configured, its default otherwise ('' when it has none)."""
    if lang and lang in site_languages.languages():
        return lang
    return site_languages.default_language()


def _version(project_slug: str, version: str | None) -> str:
    """The version to actually serve. '' for an unversioned project, which
    is exactly what its index rows hold, so every query below reduces to the
    one it ran before versions existed."""
    if not version:
        return content_versions.default_version(project_slug)
    if version not in content_versions.version_ids(project_slug):
        raise HTTPException(status_code=404, detail="Version not found.")
    return version


def _versions_payload(project_slug: str, selected: str, available: list[str] | None = None) -> dict | None:
    """What the reader-facing version switcher is built from, or None for an
    unversioned project -- which is what tells the frontend there is no
    switcher, no banner and no version segment for this project.

    `available` is which versions the thing currently being read exists in
    (this page's slug, this category's slug), or None for "all of them", as
    on a project's landing page. It is what lets the switcher stay on the
    same page when the target version has it and fall back to that version's
    home when it doesn't, instead of finding out by 404-ing the reader."""
    document = content_versions.read_versions(project_slug)
    if document is None:
        return None
    return {
        "current_id": content_versions.CURRENT_ID,
        "current_label": document["current_label"],
        "default": document["default"],
        "selected": selected,
        "is_frozen": content_versions.is_frozen(project_slug, selected),
        "frozen": document["versions"],
        "available": available,
    }


@router.get("/projects")
def public_list_projects(lang: str | None = _LANG_QUERY):
    return {"projects": projects_store.list_projects(_language(lang))}


@router.get("/projects/{project_slug}")
def public_get_project(project_slug: str, lang: str | None = _LANG_QUERY, version: str | None = _VERSION_QUERY):
    language = _language(lang)
    project = projects_store.get_project_by_slug(project_slug, language)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    resolved = _version(project_slug, version)
    categories = categories_store.list_categories(project["id"], language, resolved)
    # Only categories that actually have at least one published page are
    # worth showing -- an empty category tile the admin hasn't filled in
    # yet would just be a dead end for a visitor. A category whose pages
    # only exist in the fallback language still counts: those pages are
    # readable, and list_pages() marks them.
    visible = []
    for c in categories:
        pages = pages_store.list_pages(c["id"], published_only=True, language=language)
        if pages:
            visible.append({**c, "page_count": len(pages)})
    return {"project": project, "categories": visible, "versions": _versions_payload(project_slug, resolved)}


@router.get(
    "/projects/{project_slug}/nav",
    summary="A project's whole published structure in one response",
    description="Ordered categories, each with its ordered published pages -- what the docs sidebar, the "
    "previous/next links and the category listing are all built from. One query for the categories and one "
    "for all of the project's pages, however many categories there are -- this is on the path of every "
    "single page view.",
)
def public_get_project_nav(project_slug: str, lang: str | None = _LANG_QUERY, version: str | None = _VERSION_QUERY):
    language = _language(lang)
    project = projects_store.get_project_by_slug(project_slug, language)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    resolved = _version(project_slug, version)
    versions = _versions_payload(project_slug, resolved)

    pages_by_category: dict[int, list[dict]] = {}
    # One entry per page, never one per translation: `language` says which
    # one this entry actually is and `fallback` whether that is the reader's
    # own -- the sidebar lists such a page normally (it is readable) and
    # marks it, rather than hiding it or pretending it is translated.
    for page in pages_store.list_project_pages(project["id"], published_only=True, language=language, version=resolved):
        pages_by_category.setdefault(page["category_id"], []).append(
            {
                "id": page["id"],
                "title": page["title"],
                "slug": page["slug"],
                "sort_order": page["sort_order"],
                "language": page["language"],
                "fallback": page["fallback"],
            }
        )

    # A category with nothing published in it stays here with an empty page
    # list, rather than being dropped the way public_get_project drops it
    # from its tiles. The sidebar is the reader's map of the whole project,
    # so "this section exists but is empty" has to be something its renderer
    # can see and decide about -- a response that already removed the
    # category silently takes that decision away from every consumer.
    # Which versions each category exists in, so the switcher can decide
    # between staying on the category the reader is on and falling back to
    # the version's home -- one query for the whole project, and only for a
    # project that HAS versions: an unversioned project's nav response is
    # exactly the response it always was, key for key.
    availability = categories_store.category_versions(project["id"]) if versions else {}
    return {
        "project": project,
        "categories": [
            {
                **c,
                "pages": pages_by_category.get(c["id"], []),
                **({"available_versions": availability.get(c["slug"], [])} if versions else {}),
            }
            for c in categories_store.list_categories(project["id"], language, resolved)
        ],
        "versions": versions,
    }


@router.get("/projects/{project_slug}/categories/{category_slug}")
def public_get_category(
    project_slug: str, category_slug: str, lang: str | None = _LANG_QUERY, version: str | None = _VERSION_QUERY
):
    language = _language(lang)
    project = projects_store.get_project_by_slug(project_slug, language)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    resolved = _version(project_slug, version)
    category = categories_store.get_category_by_slug(project["id"], category_slug, language, resolved)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    pages = pages_store.list_pages(category["id"], published_only=True, language=language)
    return {
        "project": project,
        "category": category,
        "versions": _versions_payload(
            project_slug, resolved, categories_store.category_versions(project["id"]).get(category_slug, [])
        ),
        "pages": [
            {"id": p["id"], "title": p["title"], "slug": p["slug"], "language": p["language"], "fallback": p["fallback"]}
            for p in pages
        ],
    }


@router.get(
    "/projects/{project_slug}/pages/{page_slug}",
    summary="One published page, in the requested content language",
    description="Answers with the requested language's version when there is one, and with the best other one "
    "there is as a FALLBACK when there isn't (the site's default language first) -- 200 either way, with "
    "`page.fallback` true and `page.language` naming what was actually served, so the reader gets the page "
    "plus an honest notice instead of a 404 over a translation nobody has written yet.",
)
def public_get_page(
    project_slug: str, page_slug: str, lang: str | None = _LANG_QUERY, version: str | None = _VERSION_QUERY
):
    language = _language(lang)
    project = projects_store.get_project_by_slug(project_slug, language)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    resolved = _version(project_slug, version)
    # published_only, not a published check on the result: an unfinished
    # draft in the reader's own language must not shadow the published
    # version they could be reading instead (see resolve_page).
    page = pages_store.resolve_page(project["id"], page_slug, language, published_only=True, version=resolved)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    category = categories_store.get_category(page["category_id"], language)
    return {
        "project": project,
        "category": category,
        "page": page,
        # Only the versions this page is actually PUBLISHED in count as
        # somewhere the switcher may send a reader -- a draft of it in
        # another version is not a page they can read.
        "versions": _versions_payload(
            project_slug, resolved, pages_store.page_versions(project["id"], page_slug, published_only=True)
        ),
    }


@router.get(
    "/search",
    summary="Full-text search across published pages",
    description="Scoped to ONE documentation version per project: the one being read when `project` and "
    "`version` name it (the reader is inside a version, so that is the set of docs their results have to come "
    "from), otherwise each project's own default version -- never the same page once per release. `project` "
    "is a project slug; both are ignored for an unversioned project, whose pages are the only pages it has.",
)
def public_search(
    q: str = Query(..., min_length=1, max_length=200),
    lang: str | None = _LANG_QUERY,
    project: str | None = Query(default=None, max_length=200, description="Project slug to scope the search to."),
    version: str | None = _VERSION_QUERY,
):
    project_id: int | None = None
    resolved: str | None = None
    if project:
        row = projects_store.get_project_by_slug(project)
        # A stale or wrong project/version narrows to nothing rather than
        # silently widening back out to a global search: the reader asked
        # for one project's docs.
        if row is None:
            return {"results": []}
        project_id = row["id"]
        resolved = _version(project, version)
    return {"results": pages_store.search(q, language=_language(lang), project_id=project_id, version=resolved)}


@router.get(
    "/site",
    summary="This instance's branding",
    description="Name, tagline, logo/favicon URLs, accent colour and footer, read from content/_site.yml in "
    "the content repo (see the README's 'Site branding'). Every field is filled in with a default, so a "
    "missing, empty or malformed _site.yml answers exactly like an unbranded instance rather than failing.",
)
def public_get_site():
    return site_branding.read_branding()


@router.get(
    "/assets/{project_slug}/{asset_path:path}",
    summary="Serve an image from a project's content directory",
    description="Images live in the content repo next to the Markdown that uses them (see the README's "
    "'Content repo structure'). `asset_path` is relative to the project's own directory -- the frontend "
    "resolves a page's relative Markdown src against the page's directory first, so `../assets/x.png` on a "
    "page arrives here as `assets/x.png`. A project's or category's cover image (`image_url` on those "
    "objects) is served from here too, resolved the same way and by the same code.",
)
def public_get_asset(project_slug: str, asset_path: str):
    """Unlike every other route in this router there's no published= filter,
    and that's deliberate: assets aren't secret, only PAGES are. Gating an
    image on whether some page happens to reference it from a draft would
    mean an author couldn't see their own image in the editor preview, while
    protecting nothing -- the file is already in the content repo, which is
    the thing anyone with repo access can read anyway."""
    path = content_assets.resolve_asset(project_slug, asset_path)
    if path is None:
        # One 404 for missing / wrong type / outside the project / no such
        # project -- a 403 on the traversal cases would confirm what's there.
        raise HTTPException(status_code=404, detail="Asset not found.")
    return _asset_response(path)


@router.get(
    "/site/assets/{asset_path:path}",
    summary="Serve a branding image (logo, dark logo, favicon)",
    description="The instance's own images, from content/_site/ in the content repo. Same containment, "
    "allowed-type and SVG rules as a project's images -- literally the same resolver and the same response "
    "builder, with `_site` in the place of a project slug.",
)
def public_get_site_asset(asset_path: str):
    path = site_branding.resolve_site_asset(asset_path)
    if path is None:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return _asset_response(path)


def _asset_response(path: Path) -> FileResponse:
    """The one place an image from the content repo becomes a response --
    shared by the project and branding endpoints above so a `_site/` image
    can't end up with weaker headers than a page's image (or the other way
    round) after someone edits one of the two."""
    content_type = content_assets.content_type_for(path)
    headers = {
        "X-Content-Type-Options": "nosniff",
        # Not `immutable`: an author can replace an image under the same
        # filename in the next commit, and a visitor holding a year-long
        # cached copy would never see the corrected screenshot.
        "Cache-Control": "public, max-age=300",
    }
    if content_type == "image/svg+xml":
        # SVG is XML that can carry <script>/event handlers, and it's served
        # from this app's own origin. Uploads are screened for exactly that
        # (content_assets.rejection_reason), but a file committed straight
        # into the content repo by hand never passed through the uploader --
        # this header is what makes such a file inert regardless.
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"

    return FileResponse(path, media_type=content_type, headers=headers)
