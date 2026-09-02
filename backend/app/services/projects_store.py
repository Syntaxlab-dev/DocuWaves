"""Top-level content grouping -- one row per SyntaxLab project/app whose
docs live in this DocuWaves instance.

Reads (list_projects, get_project, get_project_by_slug, slug_taken) still
just query the `projects` table exactly as before -- that table is a
database INDEX kept in sync with content_files.py's on-disk `_project.yml`
files by content_sync.py, not the source of truth itself. Writes
(create/update/reorder/delete) go through content_files.py + git_content_repo.py
instead of a plain SQL INSERT/UPDATE/DELETE: they write the file(s), commit +
push to the content repo, then re-run content_sync.full_sync() so the
database reflects exactly what's now on disk (and picks up its assigned id
for a brand-new project) before returning. sort_order is a plain integer the
admin UI shifts with up/down arrows (same "no drag-and-drop library" choice
CachePanel already made deliberately) -- persisted in `order:` inside
`_project.yml` now, not just a DB column.
"""

from app.services import content_assets, content_files, content_sync, db, git_content_repo, site_languages


def _row_to_dict(row, language: str = "") -> dict:
    """`name`/`description` come out resolved for `language` (the default
    language's value when this project has no translation of them, which is
    also every project on a single-language instance), and the raw mapping
    rides along as `name_i18n` for the admin form to edit.

    The cover comes out twice for the same kind of reason `name` does:
    `image` is what the file literally says (the admin form edits that), and
    `image_url` is that path resolved against the repo -- null whenever it
    names no real, allowed image inside the project, so a tile falls back to
    its icon and text rather than rendering a broken one. Resolved on read
    rather than stored, exactly as branding resolves `logo:`: the file on
    disk is the truth, and whether it currently points at something is a
    question about right now."""
    name_i18n = site_languages.parse_i18n(row[2])
    description_i18n = site_languages.parse_i18n(row[7])
    return {
        "id": row[0],
        "name": site_languages.pick(row[1], name_i18n, language),
        "name_i18n": name_i18n,
        "slug": row[3],
        "icon": row[4],
        "color": row[5],
        "description": site_languages.pick(row[6], description_i18n, language),
        "description_i18n": description_i18n,
        "sort_order": row[8],
        "image": row[9],
        "image_url": content_assets.project_cover_url(row[3], row[9]),
    }


# `image` appended rather than slotted in beside `icon`/`color`: every index
# above is a positional read in _row_to_dict(), and the new column is the one
# thing here that has no reason to renumber them.
_COLUMNS = "id, name, name_i18n, slug, icon, color, description, description_i18n, sort_order, image"


def list_projects(language: str = "", published_only: bool = False) -> list[dict]:
    # Ordered by the DEFAULT language's name, not the reader's: the tile
    # order on the homepage is a property of the site, and a list that
    # reshuffles itself when a reader switches language would make the same
    # instance feel like two different ones.
    #
    # published_only is what the PUBLIC list passes. A project has no
    # published flag of its own -- only pages do -- so a project with
    # nothing published has nothing a reader could open, and was still
    # getting a tile on the homepage that led to an empty page. That hits
    # every new project between "created" and "first page written", and it
    # is also the only way to keep a project (a private scratchpad, a draft
    # set of docs) off the public site at all. The admin list is unfiltered,
    # so nothing disappears from the place it is managed from.
    p = "%s" if db.is_postgres() else "?"
    where = ""
    params: tuple = ()
    if published_only:
        published = "TRUE" if db.is_postgres() else "1"
        where = (
            f" WHERE EXISTS (SELECT 1 FROM pages WHERE pages.project_id = projects.id "
            f"AND pages.published = {published})"
        )
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM projects{where} ORDER BY sort_order, name", params
        ).fetchall()
    return [_row_to_dict(r, language) for r in rows]


def get_project(project_id: int, language: str = "") -> dict | None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM projects WHERE id = {placeholder}", (project_id,)).fetchone()
    return _row_to_dict(row, language) if row else None


def get_project_by_slug(slug: str, language: str = "") -> dict | None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM projects WHERE slug = {placeholder}", (slug,)).fetchone()
    return _row_to_dict(row, language) if row else None


def slug_taken(slug: str, exclude_id: int | None = None) -> bool:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        if exclude_id is not None:
            row = conn.execute(
                f"SELECT 1 FROM projects WHERE slug = {placeholder} AND id != {placeholder}", (slug, exclude_id)
            ).fetchone()
        else:
            row = conn.execute(f"SELECT 1 FROM projects WHERE slug = {placeholder}", (slug,)).fetchone()
    return row is not None


def _next_order() -> int:
    with db.get_connection() as conn:
        row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM projects").fetchone()
    return row[0]


def create_project(
    name: str,
    slug: str,
    icon: str,
    color: str,
    description: str,
    author: str,
    name_i18n: dict[str, str] | None = None,
    description_i18n: dict[str, str] | None = None,
    image: str = "",
) -> dict:
    order = _next_order()
    paths = content_files.write_project(slug, name, icon, color, image, description, order, name_i18n, description_i18n)
    git_content_repo.commit_and_push(paths, f"Add project: {name}", author)
    content_sync.full_sync()
    return get_project_by_slug(slug)


def update_project(
    project_id: int,
    name: str,
    slug: str,
    icon: str,
    color: str,
    description: str,
    author: str,
    name_i18n: dict[str, str] | None = None,
    description_i18n: dict[str, str] | None = None,
    image: str = "",
) -> dict | None:
    current = get_project(project_id)
    if current is None:
        return None
    paths: list[str] = []
    if slug != current["slug"]:
        paths += content_files.rename_project(current["slug"], slug)
    paths += content_files.write_project(
        slug, name, icon, color, image, description, current["sort_order"], name_i18n, description_i18n
    )
    git_content_repo.commit_and_push(paths, f"Update project: {name}", author)
    content_sync.full_sync()
    return get_project_by_slug(slug)


def _rewrite(project: dict, order: int) -> list[str]:
    """Rewrites a project's `_project.yml` unchanged except for its order --
    every field, translations and cover included, taken from the row as it
    reads now. `image` (the raw path, not the resolved URL) has to travel
    through here for the same reason the i18n mappings do: this rewrites the
    whole file, so a field left out is a field silently dropped on every
    reorder."""
    return content_files.write_project(
        project["slug"], project["name"], project["icon"], project["color"], project["image"],
        project["description"], order, project["name_i18n"], project["description_i18n"],
    )


def reorder_project(project_id: int, direction: int, author: str) -> None:
    """direction: -1 (move up) or +1 (move down) -- swaps the `order:` field
    in the two affected projects' _project.yml files with their adjacent
    project in that direction, same up/down-arrow mechanism
    categories_store.py and pages_store.py use for their own ordering."""
    projects = list_projects()
    index = next((i for i, pr in enumerate(projects) if pr["id"] == project_id), None)
    if index is None:
        return
    swap_index = index + direction
    if not (0 <= swap_index < len(projects)):
        return
    a, b = projects[index], projects[swap_index]
    # The i18n mappings are passed straight back through: this rewrites the
    # whole `_project.yml`, so leaving them out would quietly flatten a
    # translated name into its default language on every reorder.
    paths = _rewrite(a, b["sort_order"])
    paths += _rewrite(b, a["sort_order"])
    git_content_repo.commit_and_push(paths, f"Reorder projects: {a['name']} / {b['name']}", author)
    content_sync.full_sync()


def delete_project(project_id: int, author: str) -> None:
    current = get_project(project_id)
    if current is None:
        return
    paths = content_files.delete_project(current["slug"])
    if paths:
        git_content_repo.commit_and_push(paths, f"Remove project: {current['name']}", author)
        content_sync.full_sync()
