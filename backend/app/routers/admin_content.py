"""CRUD for projects/categories/pages -- admin-only (guarded centrally by
AuthGuardMiddleware, this router doesn't sit under /api/public/ or
/api/auth/ so every route here already requires a valid session).

Every mutating endpoint requires the content repo to be configured (see
_require_content_repo()) -- checked BEFORE any file is written, so an
unconfigured instance never leaves an orphan file on disk that never made
it into a commit. GitContentError from a write's git_content_repo call
(push rejected/conflicted after the file was already written+committed
locally) surfaces as 409, everything else content-repo-related as 400.

Writes always target the project's WRITABLE documentation version -- the
project directory itself while it has no versions, `current/` once it has
(see services/content_versions.py). A frozen version is read-only here: the
stores raise FrozenVersionError before touching a file, and main.py turns
that into a 403 with the reason spelled out, so a write can't reach a frozen
version through any route, including one the UI never offers."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services import (
    categories_store,
    content_assets,
    content_files,
    content_sync,
    content_versions,
    git_content_repo,
    pages_store,
    projects_store,
    site_branding,
    site_languages,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _author(request: Request) -> str:
    return request.session.get("username") or "admin"


def _clean_i18n(mapping: dict[str, str] | None) -> dict[str, str]:
    """A per-language name field as it arrived from the admin form, filtered
    to the languages this instance actually has configured -- the form can't
    offer any others, so anything else is hand-crafted and would put a
    language into the content repo that no reader here can select. Empty on
    a single-language instance, whatever was posted, which is what keeps
    every file it writes a plain `name: My Project` string."""
    configured = site_languages.languages()
    if not mapping or not configured:
        return {}
    return {code: value.strip() for code, value in mapping.items() if code in configured and value and value.strip()}


def _page_language(language: str | None) -> str:
    """The language a page write applies to. Blank means the default, which
    is what "new page" means on any instance and the only value a
    single-language one ever has; an unconfigured code is a mistake worth
    saying out loud rather than silently writing into the default
    language's file."""
    if not language:
        return site_languages.default_language()
    if language not in site_languages.languages():
        raise HTTPException(status_code=400, detail=f"'{language}' is not one of this site's configured languages.")
    return language


def _project_by_slug(project_slug: str) -> dict:
    """A project by its slug, or 404. Used by every route keyed by slug
    rather than by id -- versions and image assets, both of which are
    directories in the content repo with no database row of their own."""
    project = projects_store.get_project_by_slug(project_slug)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _admin_version(project_slug: str, version: str | None) -> str:
    """The version an admin READ applies to. Blank means "the one being
    edited", which is the project directory itself while it is unversioned;
    an unknown one is a 404 rather than a quiet fall back, exactly as on the
    public side."""
    if not version:
        return content_versions.writable_version(project_slug)
    if version not in content_versions.version_ids(project_slug):
        raise HTTPException(status_code=404, detail="Version not found.")
    return version


def _writable_version(project_slug: str) -> str:
    """Where admin writes for this project go: '' while it is unversioned,
    `current` once it has versions. Everything the admin UI creates lands
    there; frozen versions are refused by the stores themselves."""
    return content_versions.writable_version(project_slug)


def _require_content_repo() -> None:
    if not git_content_repo.is_configured():
        raise HTTPException(
            status_code=400,
            detail="No content repo is configured (CONTENT_REPO_URL is not set) -- see the README for setup.",
        )


# The slug rule itself lives in content_files.unique_slug(), because the MCP
# endpoint creates pages and categories too and a page an assistant writes
# has to land on the same URL a page written here would. Aliased rather than
# spelled out at each call site so this router reads exactly as it did.
_unique_slug = content_files.unique_slug


def _git_error_response(exc: git_content_repo.GitContentError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


# ---- Content repo status ----


@router.get(
    "/content-repo/status",
    summary="Content repo connection status",
    description="Whether a content repo is configured, currently reachable, and its last synced commit -- "
    "for the admin UI's connection banner. Never raises: a connection problem is shown here, not thrown.",
)
def admin_content_repo_status():
    # Plus whatever the last index run had to skip. A page that simply never
    # appears is the hardest kind of problem to chase in a file-backed CMS --
    # the file is right there in the repo -- so the reason belongs somewhere
    # the operator already looks.
    return {**git_content_repo.status(), "conflicts": content_sync.conflicts()}


@router.post(
    "/content-repo/sync",
    summary="Pull the content repo and reindex",
    description="Fetches the latest commits from the content repo's remote (e.g. a community pull request "
    "that just got merged) and rebuilds the projects/categories/pages database index from what's now on "
    "disk. Safe to call any time; also runs automatically on a timer, see CONTENT_REPO_SYNC_INTERVAL_SECONDS.",
)
def admin_content_repo_sync():
    _require_content_repo()
    try:
        git_content_repo.sync_pull()
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    content_sync.full_sync()
    return {"ok": True}


# ---- Projects ----


class ProjectIn(BaseModel):
    name: str
    icon: str = ""
    color: str = ""
    description: str = ""
    # The optional cover, as a path relative to `_project.yml` itself --
    # `assets/cover.png`, or `current/assets/cover.png` once the project is
    # versioned. Stored verbatim and never checked here, exactly as branding
    # stores `logo:`: a path that names nothing simply resolves to no URL on
    # the way back out (content_assets.project_cover_url), so a stale one
    # costs a missing cover rather than a rejected save. "" clears it, which
    # removes the key from the file.
    image: str = ""
    # Per-language values for the two human-readable fields, sent only by a
    # multilingual instance's form (see _clean_i18n). `name` stays the
    # default language's value and is what the slug is derived from.
    name_i18n: dict[str, str] = {}
    description_i18n: dict[str, str] = {}


@router.get("/projects")
def admin_list_projects():
    return {"projects": projects_store.list_projects()}


@router.post("/projects")
def admin_create_project(body: ProjectIn, request: Request):
    _require_content_repo()
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    slug = _unique_slug(name, projects_store.slug_taken)
    try:
        project = projects_store.create_project(
            name, slug, body.icon.strip(), body.color.strip(), body.description.strip(), _author(request),
            _clean_i18n(body.name_i18n), _clean_i18n(body.description_i18n), body.image.strip(),
        )
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"id": project["id"], "slug": project["slug"]}


@router.put("/projects/{project_id}")
def admin_update_project(project_id: int, body: ProjectIn, request: Request):
    _require_content_repo()
    project = projects_store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    slug = project["slug"] if name == project["name"] else _unique_slug(name, projects_store.slug_taken, exclude_id=project_id)
    try:
        updated = projects_store.update_project(
            project_id, name, slug, body.icon.strip(), body.color.strip(), body.description.strip(), _author(request),
            _clean_i18n(body.name_i18n), _clean_i18n(body.description_i18n), body.image.strip(),
        )
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    # `id` too: renaming moves the file, and the reindex that follows keys
    # rows by slug -- so the row this call started from is gone and the
    # caller's id is stale. The page endpoint already answers this way; a
    # caller that keeps using the old id here silently addresses nothing.
    return {"ok": True, "id": updated["id"] if updated else project_id, "slug": updated["slug"] if updated else slug}


@router.post("/projects/{project_id}/move")
def admin_move_project(project_id: int, direction: int, request: Request):
    _require_content_repo()
    if direction not in (-1, 1):
        raise HTTPException(status_code=400, detail="direction must be -1 or 1.")
    try:
        projects_store.reorder_project(project_id, direction, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


@router.delete("/projects/{project_id}")
def admin_delete_project(project_id: int, request: Request):
    _require_content_repo()
    if projects_store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    try:
        projects_store.delete_project(project_id, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


# ---- Categories ----


class CategoryIn(BaseModel):
    name: str
    icon: str = ""
    # The optional cover, as a path relative to `_category.yml` itself --
    # `../assets/x.png`, the same one `..` a page's Markdown uses. Same
    # store-verbatim/resolve-on-read contract as ProjectIn.image above.
    image: str = ""
    name_i18n: dict[str, str] = {}


@router.get(
    "/projects/{project_id}/categories",
    summary="A project's categories, in one documentation version",
    description="Defaults to the version the editor writes to (`current`, or the project itself while it has "
    "no versions). Pass `version` to browse a frozen one -- read-only, see POST /versions.",
)
def admin_list_categories(project_id: int, version: str | None = None):
    project = projects_store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    resolved = _admin_version(project["slug"], version)
    return {"categories": categories_store.list_categories(project_id, "", resolved)}


@router.post("/projects/{project_id}/categories")
def admin_create_category(project_id: int, body: CategoryIn, request: Request):
    _require_content_repo()
    if projects_store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    project = projects_store.get_project(project_id)
    slug = _unique_slug(name, categories_store.slug_taken, project_id, _writable_version(project["slug"]))
    try:
        category = categories_store.create_category(
            project_id, name, slug, body.icon.strip(), _author(request), _clean_i18n(body.name_i18n),
            image=body.image.strip(),
        )
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"id": category["id"], "slug": category["slug"]}


@router.put("/categories/{category_id}")
def admin_update_category(category_id: int, body: CategoryIn, request: Request):
    _require_content_repo()
    category = categories_store.get_category(category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    slug = (
        category["slug"]
        if name == category["name"]
        else _unique_slug(
            name, categories_store.slug_taken, category["project_id"], category["version"], exclude_id=category_id
        )
    )
    try:
        updated = categories_store.update_category(
            category_id, name, slug, body.icon.strip(), _author(request), _clean_i18n(body.name_i18n),
            body.image.strip(),
        )
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    # `id` too: renaming moves the file, and the reindex that follows keys
    # rows by slug -- so the row this call started from is gone and the
    # caller's id is stale. The page endpoint already answers this way; a
    # caller that keeps using the old id here silently addresses nothing.
    return {"ok": True, "id": updated["id"] if updated else category_id, "slug": updated["slug"] if updated else slug}


@router.post("/categories/{category_id}/move")
def admin_move_category(category_id: int, direction: int, request: Request):
    _require_content_repo()
    if direction not in (-1, 1):
        raise HTTPException(status_code=400, detail="direction must be -1 or 1.")
    category = categories_store.get_category(category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    try:
        categories_store.reorder_category(category["project_id"], category_id, direction, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


@router.delete("/categories/{category_id}")
def admin_delete_category(category_id: int, request: Request):
    _require_content_repo()
    if categories_store.get_category(category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    try:
        categories_store.delete_category(category_id, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


# ---- Pages ----


class PageIn(BaseModel):
    title: str
    markdown_content: str = ""
    category_id: int
    # Which language this page IS. Blank = the site's default, which is
    # every page on a single-language instance.
    language: str = ""
    # Set only when creating a TRANSLATION of an existing page: the slug the
    # translation has to land on, because a page's translations share one
    # slug (that is what keeps a reader on the same page when they switch
    # language). Blank means "a new page", and the slug is derived from the
    # title as it always was.
    slug: str = ""


@router.get(
    "/categories/{category_id}/pages",
    summary="A category's pages, one entry per language",
    description="Unlike the public endpoints, this lists every translation as its own entry (each with its "
    "own id, `language` and published state) rather than collapsing them to one per page -- the admin UI's "
    "whole job here is showing which languages a page does and does not exist in yet.",
)
def admin_list_pages(category_id: int):
    return {"pages": pages_store.list_all_pages(category_id)}


@router.get("/pages/{page_id}")
def admin_get_page(page_id: int):
    page = pages_store.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    # Which languages the page exists in at all, so the editor's tab strip
    # can show the missing ones as something to create rather than leaving
    # the author to find out by clicking. Within this page's own VERSION:
    # the same slug in another version is another file, whose translations
    # say nothing about this one's.
    return {
        **page,
        "languages": pages_store.page_languages(page["project_id"], page["slug"], page["version"]),
    }


@router.get(
    "/projects/{project_slug}/pages/by-slug/{page_slug}",
    summary="One page by slug, in one language, plus every language it exists in",
    description="What the editor's language tabs are built from. `page` is null when this language has no "
    "version yet -- which is not an error but the normal state of a translation nobody has written: the "
    "editor opens empty on that tab, and saving it creates `<slug>.<lang>.md` under this same slug. Keyed by "
    "slug rather than by a page id, because a page's translations share the slug and have different ids.",
)
def admin_find_page(project_slug: str, page_slug: str, language: str = "", version: str | None = None):
    project = projects_store.get_project_by_slug(project_slug)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    resolved = _admin_version(project_slug, version)
    languages = pages_store.page_languages(project["id"], page_slug, resolved)
    if not languages:
        raise HTTPException(status_code=404, detail="Page not found.")
    page = pages_store.get_page_by_slug(project["id"], page_slug, _page_language(language), resolved)
    # `frozen` so the editor can open a frozen version's page read-only and
    # say why, instead of offering a Save button that the API then refuses.
    return {"page": page, "languages": languages, "frozen": content_versions.is_frozen(project_slug, resolved)}


@router.post("/pages")
def admin_create_page(body: PageIn, request: Request):
    _require_content_repo()
    category = categories_store.get_category(body.category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")
    language = _page_language(body.language)

    # The page is created in the CATEGORY's version, which is the only place
    # its file can go; the store refuses a frozen one before writing.
    version = category["version"]
    if body.slug.strip():
        # Translating an existing page: keep ITS slug, never mint a new one
        # from the translated title.
        slug = body.slug.strip()
        if pages_store.get_page_by_slug(category["project_id"], slug, language, version) is not None:
            raise HTTPException(status_code=409, detail="That page already exists in this language.")
        if not pages_store.slug_taken(category["project_id"], version, slug):
            raise HTTPException(status_code=404, detail="There is no page with that slug to translate.")
    else:
        slug = _unique_slug(title, pages_store.slug_taken, category["project_id"], version)

    try:
        page = pages_store.create_page(
            category["project_id"], body.category_id, title, slug, body.markdown_content, _author(request), language
        )
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    if page is None:
        # The file was written and committed but doesn't read back as a row
        # of its own -- something about the write disagreed with the way the
        # index reads the directory. Say so, rather than raising a bare
        # TypeError on page["id"] and answering an opaque 500.
        raise HTTPException(status_code=500, detail="The page was saved but could not be read back -- check the server log.")
    return {"id": page["id"], "slug": page["slug"], "language": page["language"]}


@router.put("/pages/{page_id}")
def admin_update_page(page_id: int, body: PageIn, request: Request):
    _require_content_repo()
    page = pages_store.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    category = categories_store.get_category(body.category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")
    # Only the DEFAULT language's title steers the slug. A page's slug is
    # shared by all of its translations, so deriving it from whichever
    # translation happens to be open would let renaming the English title
    # move the German file too -- and the URL a reader bookmarked with it.
    renamable = page["language"] == site_languages.default_language()
    slug = (
        page["slug"]
        if title == page["title"] or not renamable
        else _unique_slug(title, pages_store.slug_taken, page["project_id"], page["version"], exclude_id=page_id)
    )
    try:
        updated = pages_store.update_page(page_id, title, slug, body.markdown_content, body.category_id, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    # `id` as well as `slug`: renaming a page moves its file, and the reindex
    # that follows matches rows by (version, slug, language) -- so the row
    # this call started from is gone and the page now has a NEW id. A caller
    # that kept using the old one (the editor did, for the publish call it
    # makes right after saving) got a 404 on a save that had in fact
    # succeeded, and lost whatever it was trying to set.
    return {"ok": True, "id": updated["id"] if updated else page_id, "slug": updated["slug"] if updated else slug}


@router.post("/pages/{page_id}/publish")
def admin_publish_page(page_id: int, published: bool, request: Request):
    _require_content_repo()
    if pages_store.get_page(page_id) is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    try:
        pages_store.set_published(page_id, published, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


@router.post("/pages/{page_id}/move")
def admin_move_page(page_id: int, direction: int, request: Request):
    _require_content_repo()
    if direction not in (-1, 1):
        raise HTTPException(status_code=400, detail="direction must be -1 or 1.")
    page = pages_store.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    try:
        pages_store.reorder_page(page["category_id"], page_id, direction, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


@router.delete("/pages/{page_id}")
def admin_delete_page(page_id: int, request: Request):
    _require_content_repo()
    if pages_store.get_page(page_id) is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    try:
        pages_store.delete_page(page_id, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


# ---- Page history ----
#
# Every page is a file in a git repository and every save is a commit, so the
# full history -- who changed what, when, and why -- already exists; these
# three routes are what make it reachable from inside the app.
#
# ADMIN-ONLY, and that is a decision rather than an accident of where the file
# sits: the content repo is private, and commit messages and author names are
# its internal record. The public site shows a date and nothing else (see
# routers/public_content.py's `last_updated`), so nothing here leaks through
# it.
#
# Two reads and one write. The write is an ordinary write -- same frozen-version
# refusal, same commit-and-push path, same reindex as saving a page in the
# editor -- and it only ever ADDS a commit.


@router.get(
    "/pages/{page_id}/history",
    summary="A page's commits in the content repo, newest first",
    description="The history of THIS page in THIS language: a page's translations are separate files with "
    "separate histories, and `path` names the file so the panel showing them can say which. Follows renames "
    "-- a page rename moves its file, and the history spans the move (the commit that did it carries "
    "`renamed_from`). An empty `commits` list is a normal answer for an instance with no content repo, a "
    "repo with no commits, or a page whose file has never been committed.",
)
def admin_page_history(page_id: int, limit: int = 25):
    history = pages_store.page_history(page_id, limit)
    if history is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    return history


@router.get(
    "/pages/{page_id}/history/{sha}",
    summary="One version of a page, with the diff that produced it",
    description="The title and Markdown this page held at that commit, plus a unified diff of what the commit "
    "changed in this file. `sha` has to be one from this page's own history -- anything else is a 404, which "
    "is also what keeps a hand-crafted sha from reading some other file in the repo. On the commit that "
    "CREATED the file (`status` is \"A\") there is no predecessor to compare against and the diff is the whole "
    "file as additions.",
)
def admin_page_version(page_id: int, sha: str):
    version = pages_store.page_at_commit(page_id, sha)
    if version is None:
        raise HTTPException(status_code=404, detail="No such version of this page.")
    return version


@router.post(
    "/pages/{page_id}/restore/{sha}",
    summary="Restore an older version of a page",
    description="Writes the title and Markdown of that commit back as a NEW commit on top of the history. "
    "Nothing is rewritten, reverted or deleted -- the version being replaced stays in the log, and undoing a "
    "restore is the same call again on the commit above it. The page's position, its published state and its "
    "address (slug) are left exactly as they are; see services/pages_store.restore_page for why each. A frozen "
    "documentation version refuses this like any other write, with the frozen message.",
)
def admin_restore_page(page_id: int, sha: str, request: Request):
    _require_content_repo()
    page = pages_store.get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    try:
        restored = pages_store.restore_page(page_id, sha, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    if restored is None:
        raise HTTPException(status_code=404, detail="No such version of this page.")
    # `id` and `slug` like every other page write answers with, so the editor
    # can reload the page it just changed without assuming anything survived.
    return {"ok": True, "id": restored["id"], "slug": restored["slug"], "sha": sha}


# ---- Documentation versions ----
#
# Keyed by project SLUG, like the asset routes: a version is a directory in
# the content repo, and its own id is that directory's name -- there is no
# database row for a version, only for the categories and pages inside it.
#
# Freezing is the only write that CREATES a version, and it is deliberately
# the only one that can restructure a project: on a project's first freeze it
# also moves the existing content down into `current/`. Both happen in one
# commit (see content_versions.freeze), so the repo's history never has a
# state where the content is in neither shape.


class VersionIn(BaseModel):
    # The directory name and URL segment, e.g. "v2.0". Normalized (not
    # slugified -- that would eat the dot) and validated server-side; the
    # form shows what it will become before anything happens.
    id: str
    # What the switcher calls it, e.g. "2.0".
    label: str


def _versions_response(project_slug: str) -> dict:
    document = content_versions.read_versions(project_slug)
    return {
        "versioned": document is not None,
        "current_id": content_versions.CURRENT_ID,
        "current_label": document["current_label"] if document else content_versions.DEFAULT_CURRENT_LABEL,
        "default": document["default"] if document else "",
        "writable": content_versions.writable_version(project_slug),
        "versions": document["versions"] if document else [],
        # What a FIRST freeze would move into current/ -- shown in the
        # confirmation, because that freeze is the one that restructures the
        # project's directory and the user should see it named beforehand.
        "would_move": content_versions.would_move(project_slug),
    }


@router.get(
    "/projects/{project_slug}/versions",
    summary="A project's documentation versions",
    description="`versioned` is false for a project that has never frozen one -- its content sits directly in "
    "the project directory and it has no version in its URLs at all. `would_move` is what a first freeze would "
    "move into current/, for the confirmation to name before anything happens.",
)
def admin_list_versions(project_slug: str):
    _project_by_slug(project_slug)
    return _versions_response(project_slug)


@router.post(
    "/projects/{project_slug}/versions",
    summary="Freeze the current docs as a new version",
    description="Copies the working version to content/<project>/<id>/ byte for byte and records it in "
    "_versions.yml. On the project's FIRST freeze it first moves the project's categories and assets/ into "
    "current/ -- all in one commit, and without rewriting a single page's Markdown (a page stays exactly one "
    "directory above assets/, so its ../assets/ links still resolve). The new version is read-only from then on.",
)
def admin_freeze_version(project_slug: str, body: VersionIn, request: Request):
    _require_content_repo()
    project = _project_by_slug(project_slug)
    version_id = content_versions.normalize_id(body.id)
    label = body.label.strip()
    reason = content_versions.rejection_reason(project_slug, version_id, label, body.id)
    if reason is not None:
        raise HTTPException(status_code=400, detail=reason)

    first_freeze = not content_versions.is_versioned(project_slug)
    paths = content_versions.freeze(project_slug, version_id, label)
    message = f"Freeze version {label} ({version_id}) of {project['name']}"
    if first_freeze:
        # Spelled out in the commit, because this is the commit that moved
        # every file in the project and someone reading `git log` later
        # deserves to know why without opening the diff.
        message += (
            f"\n\nFirst frozen version of this project: its categories and assets/ moved into current/, "
            f"and current/ was copied to {version_id}/. Page sources are unchanged -- a page still sits one "
            f"directory above assets/, so its ../assets/ links still resolve."
        )
    try:
        git_content_repo.commit_and_push(paths, message, _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    content_sync.full_sync()
    return {"id": version_id, "label": label, "first_freeze": first_freeze, **_versions_response(project_slug)}


@router.delete(
    "/projects/{project_slug}/versions/{version_id}",
    summary="Delete a frozen version",
    description="Removes content/<project>/<version>/ and its _versions.yml entry in one commit. The working "
    "version can never be deleted this way -- it is the project's content, not a snapshot of it.",
)
def admin_delete_version(project_slug: str, version_id: str, request: Request):
    _require_content_repo()
    project = _project_by_slug(project_slug)
    if version_id == content_versions.CURRENT_ID:
        raise HTTPException(
            status_code=400,
            detail="The current version can't be deleted -- it is the project's content, not a frozen snapshot.",
        )
    document = content_versions.read_versions(project_slug)
    entry = next((v for v in document["versions"] if v["id"] == version_id), None) if document else None
    if entry is None:
        raise HTTPException(status_code=404, detail="Version not found.")

    paths = content_versions.delete_version(project_slug, version_id)
    try:
        git_content_repo.commit_and_push(
            paths, f"Remove version {entry['label']} ({version_id}) of {project['name']}", _author(request)
        )
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    content_sync.full_sync()
    return _versions_response(project_slug)


# ---- Image assets ----
#
# Keyed by project SLUG, not by the numeric id every route above uses: an
# asset has no database row of its own (it's a plain file, not something the
# search index has any use for), so the slug -- which IS its directory name
# on disk and the path segment in its public URL -- is the only identifier
# these three endpoints need to look anything up.


def _asset_project(project_slug: str) -> dict:
    return _project_by_slug(project_slug)


def _asset_info(project_slug: str, filename: str, size: int, version: str) -> dict:
    # markdown_path() carries no version: a page sits exactly one directory
    # above its own version's assets/ folder, so `../assets/x.png` is right
    # in both shapes -- which is precisely why freezing a version never has
    # to rewrite a page. It is also exactly what a `_category.yml`'s cover
    # `image:` needs, for the same reason: that file sits one directory
    # above assets/ too.
    #
    # The other two DO need the version spelled out, and take it from the
    # caller rather than assuming the writable one: `project_path` is what a
    # `_project.yml`'s cover `image:` needs (that file stays at the project
    # level when a project is versioned, so assets/ is one directory further
    # down from there), and `url` is addressed from outside the repo's
    # directory structure altogether.
    return {
        "filename": filename,
        "size": size,
        "markdown_path": content_assets.markdown_path(filename),
        "project_path": content_assets.project_relative_path(filename, version),
        "url": content_assets.public_url(project_slug, filename, version),
    }


async def _read_capped_body(request: Request) -> bytes | None:
    """None = the upload went past the size limit. Read chunk by chunk and
    bail at the limit rather than `await request.body()`, which would buffer
    a deliberately huge upload in full before anything got the chance to
    reject it."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > content_assets.MAX_ASSET_BYTES:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


async def _read_validated_image(request: Request, filename: str) -> bytes:
    """Body bytes of an image upload, size-capped and content-checked, or the
    right HTTPException. Shared by the project uploader and the branding
    uploader further down so a logo goes through the identical extension +
    magic-number + SVG-script screening a page's screenshot does."""
    data = await _read_capped_body(request)
    if data is None:
        raise HTTPException(
            status_code=413,
            detail=f"That image is larger than the {content_assets.MAX_ASSET_BYTES // (1024 * 1024)} MB limit.",
        )
    reason = content_assets.rejection_reason(filename, data)
    if reason is not None:
        raise HTTPException(status_code=400, detail=reason)
    return data


@router.get(
    "/projects/{project_slug}/assets",
    summary="List a project's images",
    description="Everything under content/<project-slug>/assets/, with the relative path to paste into a page.",
)
def admin_list_assets(project_slug: str, version: str | None = None):
    # A read, so it follows the version being LOOKED at, like every other
    # admin read -- listing the writable version's images while the editor
    # shows a frozen one would offer images that page cannot reference.
    _asset_project(project_slug)
    resolved = _admin_version(project_slug, version)
    return {
        "assets": [
            _asset_info(project_slug, a["filename"], a["size"], resolved)
            for a in content_assets.list_assets(project_slug, resolved)
        ]
    }


@router.post(
    "/projects/{project_slug}/assets",
    summary="Upload an image into a project",
    description="The request BODY is the raw image bytes (not a multipart form -- parsing multipart would mean "
    "adding python-multipart to requirements.txt, and a single-file upload doesn't need it); `filename` is a "
    "query parameter. The stem is slugified and the real extension kept; an existing name gets -2, -3, ... "
    "rather than being overwritten. Max 10 MB, and the bytes themselves are checked against the extension.",
)
async def admin_upload_asset(project_slug: str, filename: str, request: Request, version: str | None = None):
    _require_content_repo()
    project = _asset_project(project_slug)

    # Resolved and checked like every other admin write, rather than always
    # forced to the writable version: an upload aimed at a frozen version
    # used to answer 200 and quietly put the file in `current`, so the
    # caller was told a file exists somewhere it doesn't. Frozen means
    # frozen here too -- ensure_writable raises FrozenVersionError, which
    # main.py turns into the same 403 every other frozen write gets.
    resolved = _admin_version(project_slug, version)
    content_versions.ensure_writable(project_slug, resolved)

    data = await _read_validated_image(request, filename)

    stored_name = content_assets.unique_filename(project_slug, filename, resolved)
    path = content_assets.write_asset(project_slug, stored_name, data, resolved)
    try:
        git_content_repo.commit_and_push([path], f"Add image: {stored_name} ({project['name']})", _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return _asset_info(project_slug, stored_name, len(data), resolved)


@router.delete(
    "/projects/{project_slug}/assets/{filename}",
    summary="Delete a project's image",
    description="Removes the file and commits the deletion. Pages still referencing it are left alone -- the "
    "image just stops rendering, which is visible in the editor preview, rather than the delete silently "
    "rewriting someone's Markdown.",
)
def admin_delete_asset(project_slug: str, filename: str, request: Request, version: str | None = None):
    _require_content_repo()
    project = _asset_project(project_slug)
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        # A bare filename inside the project's own assets/ folder is the only
        # thing this endpoint ever addresses; anything path-shaped is a
        # traversal attempt, not a typo worth guessing at.
        raise HTTPException(status_code=400, detail="A filename can't contain a path separator.")

    resolved = _admin_version(project_slug, version)
    content_versions.ensure_writable(project_slug, resolved)
    paths = content_assets.delete_asset(project_slug, filename, resolved)
    if not paths:
        raise HTTPException(status_code=404, detail="Asset not found.")
    try:
        git_content_repo.commit_and_push(paths, f"Remove image: {filename} ({project['name']})", _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"ok": True}


# ---- Site branding ----
#
# Instance-level, so nothing here is keyed by a project at all: it edits
# content/_site.yml and content/_site/ at the top of the content repo (see
# services/site_branding.py for why branding lives in the repo rather than in
# a database row). Writes commit and push exactly like every other admin
# write above; there is no content_sync.full_sync() call because branding has
# no database index to rebuild -- the file IS the state, read on each request.


class FooterLinkIn(BaseModel):
    label: str = ""
    url: str = ""


class SiteBrandingIn(BaseModel):
    name: str = ""
    tagline: str = ""
    # Same per-language shape the project/category forms post (see
    # _clean_i18n). `languages:` itself is NOT accepted here -- it decides
    # how every page file in the repo is named, so it is edited in the file,
    # and site_branding.write_branding() re-emits it from there.
    name_i18n: dict[str, str] = {}
    tagline_i18n: dict[str, str] = {}
    footer_text_i18n: dict[str, str] = {}
    # Filenames inside _site/, put there by the upload endpoint below -- an
    # unknown or path-shaped name simply resolves to no URL when read back
    # (site_branding._asset_field), it can never point outside the folder.
    logo: str = ""
    logo_dark: str = ""
    favicon: str = ""
    accent: str = ""
    footer_text: str = ""
    footer_links: list[FooterLinkIn] = []


@router.get(
    "/site",
    summary="This instance's branding, for the admin form",
    description="The same resolved values GET /api/public/site returns, including the raw configured "
    "filenames so the form can show which logo/favicon is currently selected.",
)
def admin_get_site():
    return site_branding.read_branding()


@router.put(
    "/site",
    summary="Save this instance's branding",
    description="Writes content/_site.yml, then commits and pushes it. Values are normalized on the way in "
    "with the same validators reading uses: a colour that isn't #rgb/#rrggbb and a footer link that isn't "
    "http(s)/mailto/site-relative are dropped rather than stored. Returns the branding as it now reads back.",
)
def admin_update_site(body: SiteBrandingIn, request: Request):
    _require_content_repo()
    paths = site_branding.write_branding(body.model_dump())
    try:
        git_content_repo.commit_and_push(paths, "Update site branding", _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return site_branding.read_branding()


@router.post(
    "/site/assets",
    summary="Upload a branding image (logo, dark logo or favicon)",
    description="Raw image bytes as the request BODY, `filename` as a query parameter -- same contract, same "
    "size limit and same content validation as a project's image upload. Stored in content/_site/ under a "
    "slugified, never-overwriting name and committed. Saving the branding form afterwards is what points "
    "_site.yml at the new file.",
)
async def admin_upload_site_asset(filename: str, request: Request):
    _require_content_repo()
    data = await _read_validated_image(request, filename)

    stored_name = site_branding.unique_asset_filename(filename)
    path = site_branding.write_site_asset(stored_name, data)
    try:
        git_content_repo.commit_and_push([path], f"Add branding image: {stored_name}", _author(request))
    except git_content_repo.GitContentError as exc:
        raise _git_error_response(exc) from exc
    return {"filename": stored_name, "size": len(data), "url": site_branding.asset_url(stored_name)}
