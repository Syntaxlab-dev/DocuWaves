"""Reconciles the database (projects/categories/pages tables, plus the FTS5/
tsvector search index built on top of them) with whatever's actually on disk
in the content repo's checkout -- the database is a rebuildable INDEX over
the files, never the other way around. On any doubt or divergence, the
filesystem wins and the database row is overwritten or removed to match it.

Matching existing DB rows to filesystem items is done by slug -- projects.slug
is globally unique, categories.slug is unique per project AND VERSION, a page
is identified by (version, slug, language) within its project, exactly the
same uniqueness the filesystem's own directory/file naming already has to
respect (two categories with the same folder name inside one version
directory is simply impossible on disk, and so is `installation.de.md`
twice). A row whose key is still present on disk keeps its existing id (and
every existing admin-editor deep link / API caller that already has that id
stays valid); a key that's new gets a freshly assigned id; a key that's gone
gets its row (and, via ON DELETE CASCADE, everything under it) removed.

A page's language comes from its filename (`<slug>.<lang>.md`, plain
`<slug>.md` = the default language, '' when the instance configured none) --
see content_files.list_page_variants(). Nothing here rewrites or moves a
file: adding `languages: [de, en]` to an existing repo's _site.yml simply
makes the next sync index every existing `<slug>.md` as German, in place.

A row's VERSION comes from the directory one level above its category (see
content_versions.py), and is '' for a project with no `_versions.yml` --
which is what keeps such a project's rows exactly the rows it has always
had. A versioned project is indexed once per version: `current` and every
frozen one, each holding its own full set of categories and pages. Frozen
rows are indexed exactly like current ones (they are published pages people
read); what makes them frozen is that every WRITE path refuses them, not
that the index treats them differently.

Pages are matched/retired at the PROJECT level, not per-category: a page's
slug is only unique within its project (and version), and moving a page to a
different category of the same project (relocate_page() in content_files.py)
must keep its id. Doing the existing/seen/stale bookkeeping per-category
instead would see the page vanish from its old category's disk listing
before its new category's pass ever runs, and delete-then-recreate it with a
fresh id -- this module resolves that by syncing every category's page
directory first, then reconciling all of that project's pages (across all of
its versions) in one single pass.
"""

import logging
from datetime import datetime, timezone

from app.services import content_files, content_versions, db, site_languages

log = logging.getLogger("docuwaves")

# Files the last sync could not index, and why. Rebuilt from scratch on every
# run (a fixed repo must clear it), and read by the admin content-repo status
# panel -- a page that silently does not appear is a worse failure than one
# that appears with an explanation attached.
_conflicts: list[dict] = []


# When the last full_sync() finished, ISO-8601, or "" before the first one.
# In memory rather than in a table: it describes THIS process, and a value
# that survived a restart would be answering a different question than the
# diagnostics page is asking ("is this instance's index current?").
_last_sync: str = ""


def conflicts() -> list[dict]:
    return list(_conflicts)


def last_sync() -> str:
    return _last_sync


def _record_conflict(project: str, category: str, kept_in: str, slug: str, language: str, version: str) -> None:
    entry = {
        "project": project,
        "slug": slug,
        "language": language,
        "version": version,
        "category": category,
        "kept_in": kept_in,
    }
    _conflicts.append(entry)
    log.warning(
        "Duplicate page slug '%s' in project '%s': using the copy in '%s', ignoring the one in '%s'. "
        "A page's slug is its URL and must be unique within a project -- rename or remove one of the two files.",
        slug, project, kept_in, category,
    )


def full_sync() -> None:
    global _last_sync
    _conflicts.clear()
    if not content_files.content_root().exists():
        # No checkout to reconcile against -- the repo was never cloned, or
        # the clone failed. "No files on disk" is not the same statement as
        # "every page was deleted", and treating it as one would empty a
        # perfectly good index (and, on the first start after a schema
        # rebuild, leave it empty) over a network problem.
        return
    with db.get_connection() as conn:
        _sync_projects(conn)
    # Only after a sync that actually ran: the early return above is "there
    # is nothing on disk to reconcile against", and stamping that as a
    # successful sync would report an index as current that was never built.
    _last_sync = datetime.now(timezone.utc).isoformat()


def _placeholder() -> str:
    return "%s" if db.is_postgres() else "?"


# A per-language name/description mapping as the index stores it -- see
# db.py's schema comment on name_i18n.
_i18n = site_languages.dump_i18n


def _sync_projects(conn) -> None:
    p = _placeholder()
    disk_slugs = content_files.list_project_slugs()
    existing = {row[0]: row[1] for row in conn.execute("SELECT slug, id FROM projects").fetchall()}

    seen_ids: set[int] = set()
    for slug in disk_slugs:
        data = content_files.read_project(slug)
        if data is None:
            continue
        values = (
            data["name"], _i18n(data["name_i18n"]), data["icon"], data["color"], data["image"],
            data["description"], _i18n(data["description_i18n"]), data["order"],
        )
        if slug in existing:
            project_id = existing[slug]
            conn.execute(
                f"UPDATE projects SET name={p}, name_i18n={p}, icon={p}, color={p}, image={p}, description={p}, "
                f"description_i18n={p}, sort_order={p} WHERE id={p}",
                (*values, project_id),
            )
        else:
            columns = "name, name_i18n, slug, icon, color, image, description, description_i18n, sort_order"
            # slug sits second in the tuple, matching its position in the
            # column list -- everything else keeps the shared `values` order.
            params = (values[0], values[1], slug, *values[2:])
            if db.is_postgres():
                row = conn.execute(
                    f"INSERT INTO projects ({columns}) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p}) RETURNING id",
                    params,
                ).fetchone()
                project_id = row[0]
            else:
                cursor = conn.execute(
                    f"INSERT INTO projects ({columns}) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p})",
                    params,
                )
                project_id = cursor.lastrowid
        seen_ids.add(project_id)
        _sync_categories_and_pages(conn, project_id, slug)

    stale_ids = set(existing.values()) - seen_ids
    for stale_id in stale_ids:
        conn.execute(f"DELETE FROM projects WHERE id={p}", (stale_id,))


def _sync_categories_and_pages(conn, project_id: int, project_slug: str) -> None:
    p = _placeholder()

    # [''] for an unversioned project -- one pass over the project directory
    # with an empty version, which is byte-for-byte the work this function
    # did before versions existed.
    versions = content_versions.index_versions(project_slug)

    # -- Categories first (pages need a resolved category_id) --
    existing_categories = {
        (row[0], row[1]): row[2]
        for row in conn.execute(
            f"SELECT version, slug, id FROM categories WHERE project_id={p}", (project_id,)
        ).fetchall()
    }

    # (version, category_slug) -> id, for the page pass below.
    category_ids: dict[tuple[str, str], int] = {}
    seen_category_ids: set[int] = set()
    for version in versions:
        for slug in content_files.list_category_slugs(project_slug, version):
            data = content_files.read_category(project_slug, slug, version)
            if data is None:
                continue
            if (version, slug) in existing_categories:
                category_id = existing_categories[(version, slug)]
                conn.execute(
                    f"UPDATE categories SET name={p}, name_i18n={p}, icon={p}, image={p}, sort_order={p} WHERE id={p}",
                    (data["name"], _i18n(data["name_i18n"]), data["icon"], data["image"], data["order"], category_id),
                )
            else:
                params = (
                    project_id, data["name"], _i18n(data["name_i18n"]), slug, version, data["icon"], data["image"],
                    data["order"],
                )
                if db.is_postgres():
                    row = conn.execute(
                        f"INSERT INTO categories (project_id, name, name_i18n, slug, version, icon, image, sort_order) "
                        f"VALUES ({p},{p},{p},{p},{p},{p},{p},{p}) RETURNING id",
                        params,
                    ).fetchone()
                    category_id = row[0]
                else:
                    cursor = conn.execute(
                        f"INSERT INTO categories (project_id, name, name_i18n, slug, version, icon, image, sort_order) "
                        f"VALUES ({p},{p},{p},{p},{p},{p},{p},{p})",
                        params,
                    )
                    category_id = cursor.lastrowid
            category_ids[(version, slug)] = category_id
            seen_category_ids.add(category_id)

    stale_category_ids = set(existing_categories.values()) - seen_category_ids
    for stale_id in stale_category_ids:
        conn.execute(f"DELETE FROM categories WHERE id={p}", (stale_id,))

    # -- Pages: one pass across ALL of this project's categories and
    #    versions, see module docstring --
    existing_pages = {
        (row[0], row[1], row[2]): row[3]
        for row in conn.execute(
            f"SELECT version, slug, language, id FROM pages WHERE project_id={p}", (project_id,)
        ).fetchall()
    }
    seen_page_ids: set[int] = set()

    # A page's slug is unique per PROJECT (its URL is /pages/<slug>, with no
    # category in it), but nothing on disk stops two categories from holding
    # the same filename -- a/install.md and b/install.md is a perfectly
    # ordinary thing for someone to commit, or for a merged pull request to
    # introduce. The second INSERT then violated the unique constraint and
    # the exception took the whole instance down at startup: the site was
    # gone, and nothing said why. One repo file must never be able to do
    # that. The first one wins (iteration is ordered, so which one that is
    # stays stable across syncs), the rest are skipped and reported.
    claimed: dict[tuple, str] = {}

    for (version, category_slug), category_id in category_ids.items():
        for slug, language in content_files.list_page_variants(project_slug, category_slug, version):
            key = (version, slug, language)
            if key in claimed:
                _record_conflict(project_slug, category_slug, claimed[key], slug, language, version)
                continue
            claimed[key] = category_slug

            data = content_files.read_page(project_slug, category_slug, slug, language, version)
            if data is None:
                continue
            published_value = data["published"] if db.is_postgres() else (1 if data["published"] else 0)
            if (version, slug, language) in existing_pages:
                page_id = existing_pages[(version, slug, language)]
                conn.execute(
                    # updated_at was left out entirely, so the column recorded
                    # when the row was first indexed and never moved again --
                    # a page edited for a year still claimed the date it was
                    # imported. It is exposed on the public page response and
                    # to assistants through the MCP read_page tool, so it was
                    # quietly wrong in both.
                    #
                    # Set through a CASE rather than unconditionally: this
                    # UPDATE runs for every page on every reindex, so always
                    # stamping it would replace "frozen at import" with the
                    # equally untrue "everything changed just now". The
                    # right-hand sides see the pre-update row in both SQLite
                    # and Postgres, so the comparison is old-vs-new.
                    #
                    # The review note is SET but is deliberately not part of
                    # the CASE: marking a page as checked does not change
                    # what the page says, so it must not move the date that
                    # claims the page changed.
                    f"UPDATE pages SET title={p}, markdown_content={p}, sort_order={p}, published={p}, "
                    f"category_id={p}, reviewed_by={p}, reviewed_at={p}, "
                    f"updated_at = CASE WHEN title <> {p} OR markdown_content <> {p} "
                    f"OR sort_order <> {p} OR published <> {p} OR category_id <> {p} "
                    f"THEN {p} ELSE updated_at END WHERE id={p}",
                    (
                        data["title"], data["markdown_content"], data["order"], published_value, category_id,
                        data["reviewed_by"], data["reviewed_at"],
                        data["title"], data["markdown_content"], data["order"], published_value, category_id,
                        datetime.now(timezone.utc).isoformat(),
                        page_id,
                    ),
                )
            else:
                columns = (
                    "project_id, category_id, title, slug, language, version, markdown_content, sort_order, "
                    "published, reviewed_by, reviewed_at, created_at, updated_at"
                )
                now = datetime.now(timezone.utc).isoformat()
                params = (
                    project_id, category_id, data["title"], slug, language, version, data["markdown_content"],
                    data["order"], published_value, data["reviewed_by"], data["reviewed_at"], now, now,
                )
                placeholders = ",".join([p] * len(params))
                if db.is_postgres():
                    row = conn.execute(
                        f"INSERT INTO pages ({columns}) VALUES ({placeholders}) RETURNING id",
                        params,
                    ).fetchone()
                    page_id = row[0]
                else:
                    cursor = conn.execute(
                        f"INSERT INTO pages ({columns}) VALUES ({placeholders})",
                        params,
                    )
                    page_id = cursor.lastrowid
            seen_page_ids.add(page_id)

    stale_page_ids = set(existing_pages.values()) - seen_page_ids
    for stale_id in stale_page_ids:
        conn.execute(f"DELETE FROM pages WHERE id={p}", (stale_id,))
