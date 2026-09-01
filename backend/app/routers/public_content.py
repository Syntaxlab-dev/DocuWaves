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
answers exactly as it did before this existed."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.services import (
    categories_store,
    content_assets,
    pages_store,
    projects_store,
    site_branding,
    site_languages,
)

router = APIRouter(prefix="/api/public", tags=["public"])

_LANG_QUERY = Query(default=None, max_length=8, description="Content language; defaults to the site's first one.")


def _language(lang: str | None) -> str:
    """The language to actually serve: the requested one when this instance
    has it configured, its default otherwise ('' when it has none)."""
    if lang and lang in site_languages.languages():
        return lang
    return site_languages.default_language()


@router.get("/projects")
def public_list_projects(lang: str | None = _LANG_QUERY):
    return {"projects": projects_store.list_projects(_language(lang))}


@router.get("/projects/{project_slug}")
def public_get_project(project_slug: str, lang: str | None = _LANG_QUERY):
    language = _language(lang)
    project = projects_store.get_project_by_slug(project_slug, language)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    categories = categories_store.list_categories(project["id"], language)
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
    return {"project": project, "categories": visible}


@router.get(
    "/projects/{project_slug}/nav",
    summary="A project's whole published structure in one response",
    description="Ordered categories, each with its ordered published pages -- what the docs sidebar, the "
    "previous/next links and the category listing are all built from. One query for the categories and one "
    "for all of the project's pages, however many categories there are -- this is on the path of every "
    "single page view.",
)
def public_get_project_nav(project_slug: str, lang: str | None = _LANG_QUERY):
    language = _language(lang)
    project = projects_store.get_project_by_slug(project_slug, language)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    pages_by_category: dict[int, list[dict]] = {}
    # One entry per page, never one per translation: `language` says which
    # one this entry actually is and `fallback` whether that is the reader's
    # own -- the sidebar lists such a page normally (it is readable) and
    # marks it, rather than hiding it or pretending it is translated.
    for page in pages_store.list_project_pages(project["id"], published_only=True, language=language):
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
    return {
        "project": project,
        "categories": [
            {**c, "pages": pages_by_category.get(c["id"], [])}
            for c in categories_store.list_categories(project["id"], language)
        ],
    }


@router.get("/projects/{project_slug}/categories/{category_slug}")
def public_get_category(project_slug: str, category_slug: str, lang: str | None = _LANG_QUERY):
    language = _language(lang)
    project = projects_store.get_project_by_slug(project_slug, language)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    category = categories_store.get_category_by_slug(project["id"], category_slug, language)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    pages = pages_store.list_pages(category["id"], published_only=True, language=language)
    return {
        "project": project,
        "category": category,
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
def public_get_page(project_slug: str, page_slug: str, lang: str | None = _LANG_QUERY):
    language = _language(lang)
    project = projects_store.get_project_by_slug(project_slug, language)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    # published_only, not a published check on the result: an unfinished
    # draft in the reader's own language must not shadow the published
    # version they could be reading instead (see resolve_page).
    page = pages_store.resolve_page(project["id"], page_slug, language, published_only=True)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    category = categories_store.get_category(page["category_id"], language)
    return {"project": project, "category": category, "page": page}


@router.get("/search")
def public_search(q: str = Query(..., min_length=1, max_length=200), lang: str | None = _LANG_QUERY):
    return {"results": pages_store.search(q, language=_language(lang))}


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
    "page arrives here as `assets/x.png`.",
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
