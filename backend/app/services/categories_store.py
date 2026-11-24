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
_COLUMNS = "c.id, c.project_id, c.name, c.name_i18n, c.slug, c.icon, c.sort_order, c.version, c.image, p.slug, c.parent"
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
        # The slug of the category this one sits under, '' at the top level.
        # Already checked by the sync (content_sync._valid_parents), so it
        # always names a category of the same version and never loops.
        "parent": row[10],
    }


def tree_order(categories: list[dict]) -> list[dict]:
    """The categories in reading order -- each one followed by everything
    under it -- with a `depth` (0 at the top) on every entry. `categories`
    is one version's list in sort order, as list_categories() returns it;
    siblings keep that order. What the book, the static export and every
    "next page" walk read, so a nested project reads the way its sidebar
    looks."""
    children: dict[str, list[dict]] = {}
    for category in categories:
        children.setdefault(category.get("parent", ""), []).append(category)
    ordered: list[dict] = []

    def walk(parent: str, depth: int) -> None:
        for category in children.get(parent, []):
            ordered.append({**category, "depth": depth})
            walk(category["slug"], depth + 1)

    walk("", 0)
    return ordered


def descendants(categories: list[dict], slug: str) -> list[dict]:
    """Every category under `slug` (not `slug` itself), in reading order."""
    ordered = tree_order(categories)
    start = next((i for i, c in enumerate(ordered) if c["slug"] == slug), None)
    if start is None:
        return []
    depth = ordered[start]["depth"]
    result = []
    for category in ordered[start + 1:]:
        if category["depth"] <= depth:
            break
        result.append(category)
    return result


def ancestors(categories: list[dict], slug: str) -> list[dict]:
    """The categories above `slug`, outermost first -- a breadcrumb."""
    by_slug = {c["slug"]: c for c in categories}
    chain: list[dict] = []
    cursor = by_slug.get(slug, {}).get("parent", "")
    while cursor and cursor in by_slug and len(chain) < content_sync.MAX_CATEGORY_DEPTH:
        chain.insert(0, by_slug[cursor])
        cursor = by_slug[cursor].get("parent", "")
    return chain


class InvalidParent(ValueError):
    """The parent asked for cannot hold this category."""


def _check_parent(categories: list[dict], slug: str | None, parent: str) -> None:
    """`slug` None for a category that does not exist yet. Refused here,
    with a reason, rather than written and then silently dropped by the
    sync: the editor asked for something specific."""
    if not parent:
        return
    by_slug = {c["slug"]: c for c in categories}
    if parent not in by_slug:
        raise InvalidParent("That parent category does not exist in this version.")
    if slug is not None and (parent == slug or parent in {c["slug"] for c in descendants(categories, slug)}):
        raise InvalidParent("A category cannot sit inside itself or inside one of its own subcategories.")
    depth = 1 + len(ancestors(categories, parent)) + 1
    below = 0
    if slug is not None:
        sub = descendants(categories, slug)
        if sub:
            base = next(c["depth"] for c in tree_order(categories) if c["slug"] == slug)
            below = max(c["depth"] for c in sub) - base
    if depth + below > content_sync.MAX_CATEGORY_DEPTH:
        raise InvalidParent(f"Categories nest at most {content_sync.MAX_CATEGORY_DEPTH} levels deep.")


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
    parent: str = "",
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
    _check_parent(list_categories(project_id, "", version), None, parent)
    if order is None:
        order = _next_order(project_id, version)
    paths = content_files.write_category(
        project["slug"], slug, name, icon, image, order, name_i18n, version, parent
    )
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
    parent: str | None = None,
) -> dict | None:
    """`parent` None keeps the one it has -- the MCP tools and older
    callers never send it, and must not flatten a nested category."""
    current = get_category(category_id)
    if current is None:
        return None
    project = projects_store.get_project(current["project_id"])
    version = current["version"]
    content_versions.ensure_editable(project["slug"], version)
    siblings = list_categories(current["project_id"], "", version)
    if parent is None:
        parent = current["parent"]
    _check_parent(siblings, current["slug"], parent)
    order = current["sort_order"]
    if parent != current["parent"]:
        # Moved under another category: it goes to the end of its new
        # siblings rather than keeping a number that meant something among
        # the old ones.
        order = max((c["sort_order"] for c in siblings if c["parent"] == parent), default=-1) + 1
    paths: list[str] = []
    if slug != current["slug"]:
        paths += content_files.rename_category(project["slug"], current["slug"], slug, version)
        # The subcategories name this one by its slug, so they follow it.
        for child in siblings:
            if child["parent"] == current["slug"]:
                paths += _rewrite(project["slug"], child, version, parent=slug)
    paths += content_files.write_category(
        project["slug"], slug, name, icon, image, order, name_i18n, version, parent
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
    content_versions.ensure_editable(project["slug"], version)
    # Among its siblings only: moving a subcategory up must not swap it
    # with some unrelated category that happens to sit above it in the list.
    categories = [c for c in list_categories(project_id, "", version) if c["parent"] == current["parent"]]
    index = next((i for i, c in enumerate(categories) if c["id"] == category_id), None)
    if index is None:
        return
    swap_index = index + direction
    if not (0 <= swap_index < len(categories)):
        return
    a, b = categories[index], categories[swap_index]
    paths = _rewrite(project["slug"], a, version, order=b["sort_order"])
    paths += _rewrite(project["slug"], b, version, order=a["sort_order"])
    git_content_repo.commit_and_push(paths, f"Reorder categories: {a['name']} / {b['name']}", author)
    content_sync.full_sync()


def delete_category(category_id: int, author: str) -> None:
    current = get_category(category_id)
    if current is None:
        return
    project = projects_store.get_project(current["project_id"])
    content_versions.ensure_editable(project["slug"], current["version"])
    paths = content_files.delete_category(project["slug"], current["slug"], current["version"])
    # Its subcategories are not deleted with it (they are directories of
    # their own, with their own pages): they move up one level, into the
    # place it held.
    if paths:
        for child in list_categories(current["project_id"], "", current["version"]):
            if child["parent"] == current["slug"]:
                paths += _rewrite(project["slug"], child, current["version"], parent=current["parent"])
    if paths:
        git_content_repo.commit_and_push(paths, f"Remove category: {current['name']} ({project['name']})", author)
        content_sync.full_sync()


def _rewrite(project_slug: str, category: dict, version: str, *, order: int | None = None, parent: str | None = None) -> list[str]:
    """Writes `category`'s `_category.yml` back with one thing changed.
    name_i18n, image and parent are all passed through: this rewrites the
    whole file, so dropping any of them would flatten a translated name,
    delete a cover or un-nest a category as a side effect."""
    return content_files.write_category(
        project_slug,
        category["slug"],
        category["name"],
        category["icon"],
        category["image"],
        category["sort_order"] if order is None else order,
        category["name_i18n"],
        version,
        category["parent"] if parent is None else parent,
    )
