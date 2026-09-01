"""Categories group pages within one project -- the "tile" navigation level
between a project's landing page and its individual pages. Slugs are unique
per project AND documentation version (not globally), enforced by the DB's
own UNIQUE(project_id, version, slug) constraint -- matching the
filesystem's own directory-naming uniqueness inside one version's folder.

Reads unchanged (DB index, kept current by content_sync.py); writes go
through content_files.py + git_content_repo.py, see projects_store.py's own
docstring for the full reasoning, identical here.

The version dimension: every read takes the version being served ('' for an
unversioned project, which is exactly what its rows hold), and every write
targets the project's WRITABLE version and refuses a frozen one (see
content_versions.ensure_writable). A frozen version is a snapshot of what
the docs said at a release -- renaming a category in it would silently
rewrite that release, so it is a file edit in the content repo instead,
reviewable like any other contribution."""

from app.services import (
    content_assets,
    content_files,
    content_sync,
    content_versions,
    db,
    git_content_repo,
    projects_store,
    site_languages,
)

# Qualified, and joined to `projects` for one reason: a category's cover is a
# path INSIDE its project's directory, so turning it into a URL needs the
# project's slug -- which is that directory's name. One join costs nothing
# next to a second query per listing, and it keeps the cover a property of
# the category rather than something every caller has to pass in (three
# read functions, each with its own callers in two routers and the MCP
# tools, would all have to grow a project_slug argument otherwise).
_COLUMNS = "c.id, c.project_id, c.name, c.name_i18n, c.slug, c.icon, c.sort_order, c.version, c.image, p.slug"
_FROM = "FROM categories c JOIN projects p ON p.id = c.project_id"


def _row_to_dict(row, language: str = "") -> dict:
    """`name` resolved for `language`, plus the raw mapping -- see
    projects_store._row_to_dict(), identical here. `version` rides along so
    a caller holding a category always knows which version's category it is
    (and therefore whether it may be written to).

    The cover comes out as both `image` (what `_category.yml` literally
    says) and `image_url` (that path resolved, or null) -- again exactly as
    projects_store does it. The project slug from the join is used to
    resolve it and is deliberately NOT in the result: the caller asked for a
    category, and every one of them already knows which project it asked
    about."""
    name_i18n = site_languages.parse_i18n(row[3])
    return {
        "id": row[0],
        "project_id": row[1],
        "name": site_languages.pick(row[2], name_i18n, language),
        "name_i18n": name_i18n,
        "slug": row[4],
        "icon": row[5],
        "sort_order": row[6],
        "version": row[7],
        "image": row[8],
        # The version is passed in as well as the slug: a category's cover
        # has to resolve inside its OWN version's assets/, so v2.0's tile
        # keeps showing v2.0's image (see content_assets.category_cover_url).
        "image_url": content_assets.category_cover_url(row[9], row[7], row[4], row[8]),
    }


def list_categories(project_id: int, language: str = "", version: str = "") -> list[dict]:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} {_FROM} WHERE c.project_id = {placeholder} AND c.version = {placeholder} "
            f"ORDER BY c.sort_order, c.name",
            (project_id, version),
        ).fetchall()
    return [_row_to_dict(r, language) for r in rows]


def get_category(category_id: int, language: str = "") -> dict | None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} {_FROM} WHERE c.id = {placeholder}", (category_id,)).fetchone()
    return _row_to_dict(row, language) if row else None


def get_category_by_slug(project_id: int, slug: str, language: str = "", version: str = "") -> dict | None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} {_FROM} WHERE c.project_id = {placeholder} AND c.slug = {placeholder} "
            f"AND c.version = {placeholder}",
            (project_id, slug, version),
        ).fetchone()
    return _row_to_dict(row, language) if row else None


def category_versions(project_id: int) -> dict[str, list[str]]:
    """Which versions each of this project's category slugs exists in --
    what the version switcher needs to know whether switching can stay on
    the category being read or has to land on that version's home instead.

    The whole project in one query rather than one per category: the nav
    response already carries every category, and the switcher has to answer
    for whichever one the reader happens to be on."""
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT slug, version FROM categories WHERE project_id = {placeholder}", (project_id,)
        ).fetchall()
    availability: dict[str, list[str]] = {}
    for slug, version in rows:
        availability.setdefault(slug, []).append(version)
    return availability


def slug_taken(project_id: int, version: str, slug: str, exclude_id: int | None = None) -> bool:
    """Per version: `getting-started` in v2.0 and in current are two
    directories in two different places, so one must not block the other."""
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        if exclude_id is not None:
            row = conn.execute(
                f"SELECT 1 FROM categories WHERE project_id = {placeholder} AND version = {placeholder} "
                f"AND slug = {placeholder} AND id != {placeholder}",
                (project_id, version, slug, exclude_id),
            ).fetchone()
        else:
            row = conn.execute(
                f"SELECT 1 FROM categories WHERE project_id = {placeholder} AND version = {placeholder} "
                f"AND slug = {placeholder}",
                (project_id, version, slug),
            ).fetchone()
    return row is not None


def _next_order(project_id: int, version: str) -> int:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT COALESCE(MAX(sort_order), -1) + 1 FROM categories WHERE project_id = {placeholder} "
            f"AND version = {placeholder}",
            (project_id, version),
        ).fetchone()
    return row[0]


def create_category(
    project_id: int,
    name: str,
    slug: str,
    icon: str,
    author: str,
    name_i18n: dict[str, str] | None = None,
    order: int | None = None,
    image: str = "",
) -> dict | None:
    """Always creates in the project's WRITABLE version -- '' while the
    project is unversioned, `current` once it is. There is deliberately no
    way to create a category inside a frozen version: adding a section to a
    released version's docs is not a thing this UI should make easy.

    `order` None means "at the end", which is what the admin UI always wants
    (it has arrow buttons to move it afterwards). The MCP endpoint passes an
    explicit one when the caller asked for a position, because an assistant
    creating three categories in one go has no arrows to press.

    `image` is last, after `order`, so the MCP endpoint's existing
    positional call keeps meaning what it meant -- it has no cover to set
    (create_category is not an image uploader), and "" is exactly the
    no-cover value."""
    project = projects_store.get_project(project_id)
    if project is None:
        return None
    version = content_versions.writable_version(project["slug"])
    if order is None:
        order = _next_order(project_id, version)
    paths = content_files.write_category(project["slug"], slug, name, icon, image, order, name_i18n, version)
    git_content_repo.commit_and_push(paths, f"Add category: {name} ({project['name']})", author)
    content_sync.full_sync()
    return get_category_by_slug(project_id, slug, "", version)


def update_category(
    category_id: int,
    name: str,
    slug: str,
    icon: str,
    author: str,
    name_i18n: dict[str, str] | None = None,
    image: str = "",
) -> dict | None:
    current = get_category(category_id)
    if current is None:
        return None
    project = projects_store.get_project(current["project_id"])
    version = current["version"]
    content_versions.ensure_writable(project["slug"], version)
    paths: list[str] = []
    if slug != current["slug"]:
        paths += content_files.rename_category(project["slug"], current["slug"], slug, version)
    paths += content_files.write_category(
        project["slug"], slug, name, icon, image, current["sort_order"], name_i18n, version
    )
    git_content_repo.commit_and_push(paths, f"Update category: {name} ({project['name']})", author)
    content_sync.full_sync()
    return get_category_by_slug(current["project_id"], slug, "", version)


def reorder_category(project_id: int, category_id: int, direction: int, author: str) -> None:
    current = get_category(category_id)
    if current is None:
        return
    project = projects_store.get_project(project_id)
    version = current["version"]
    content_versions.ensure_writable(project["slug"], version)
    categories = list_categories(project_id, "", version)
    index = next((i for i, c in enumerate(categories) if c["id"] == category_id), None)
    if index is None:
        return
    swap_index = index + direction
    if not (0 <= swap_index < len(categories)):
        return
    a, b = categories[index], categories[swap_index]
    # name_i18n and image passed back through: this rewrites the whole
    # `_category.yml`, so dropping either would flatten a translated name --
    # or silently delete a cover -- on every reorder.
    paths = content_files.write_category(
        project["slug"], a["slug"], a["name"], a["icon"], a["image"], b["sort_order"], a["name_i18n"], version
    )
    paths += content_files.write_category(
        project["slug"], b["slug"], b["name"], b["icon"], b["image"], a["sort_order"], b["name_i18n"], version
    )
    git_content_repo.commit_and_push(paths, f"Reorder categories: {a['name']} / {b['name']}", author)
    content_sync.full_sync()


def delete_category(category_id: int, author: str) -> None:
    current = get_category(category_id)
    if current is None:
        return
    project = projects_store.get_project(current["project_id"])
    content_versions.ensure_writable(project["slug"], current["version"])
    paths = content_files.delete_category(project["slug"], current["slug"], current["version"])
    if paths:
        git_content_repo.commit_and_push(paths, f"Remove category: {current['name']} ({project['name']})", author)
        content_sync.full_sync()
