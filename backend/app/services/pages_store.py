"""Individual doc pages. Content is stored as raw Markdown text in a `.md`
file with YAML frontmatter (see content_files.py for the exact on-disk
shape) -- the backend never transforms it beyond that, rendering is a
frontend concern (see frontend/src/components/MarkdownView.tsx).

Reads (list_pages, get_page, get_page_by_slug, search) are unchanged from
the database-only version: they query the `pages` table exactly as before,
which content_sync.py keeps as a live index over the actual files. Writes
go through content_files.py + git_content_repo.py; see projects_store.py's
own docstring for the full "files are truth, DB is a rebuildable index"
reasoning, identical here.

Search is genuinely two different implementations per backend rather than
one shared query, because SQLite and Postgres have unrelated full-text
mechanisms:
- SQLite: the pages_fts FTS5 virtual table (see db.py), queried with a
  MATCH expression built from the user's search terms, each term quoted as
  its own FTS5 string literal (`"term"`) so punctuation inside a term can't
  break FTS5's own query-syntax parser -- terms are OR'd together, ranked
  by FTS5's built-in bm25().
- Postgres: to_tsvector('simple', title || ' ' || content) computed live
  in the query (no materialized tsvector column/trigger -- simpler, and
  fast enough at the row counts a self-hosted docs tool actually holds)
  matched against plainto_tsquery('simple', %s), which safely tokenizes
  arbitrary user input as a parameterized value (no injection risk, unlike
  hand-building an FTS5 MATCH string).
'simple' text search config on the Postgres side deliberately skips
English-specific stemming, matching FTS5's own non-stemming default --
keeps search behavior close to identical between the two backends.

A page also exists once per documentation VERSION: a frozen version holds
its own full copy of every page, so (version, slug, language) is what
identifies a row. `version` is '' for a project with no `_versions.yml`,
which keeps such a project's queries exactly the ones they were. Reads take
the version being served; writes take the version from the page's own row
and refuse a frozen one (content_versions.ensure_writable) -- frozen means
frozen, and correcting an old page is a file edit in the content repo.

A page exists once PER LANGUAGE: one row per `<slug>.<lang>.md` file, all
sharing the slug (see content_files.py). Every reader-facing function here
therefore takes the language being served and answers with one row per
slug -- the requested language's row when there is one, otherwise the best
other one there is (see _priority), flagged as `fallback` so the UI can say
so rather than pretending the page is translated. Nothing 404s over a
missing translation. On an instance with no `languages:` configured every
row's language is '', requested == default == '', and each of these
functions reduces to exactly the query it ran before.
"""

from app.services import (
    categories_store,
    content_files,
    content_sync,
    content_versions,
    db,
    git_content_repo,
    projects_store,
    site_languages,
)

_COLUMNS = (
    "id, project_id, category_id, title, slug, language, markdown_content, sort_order, published, "
    "created_at, updated_at, version"
)

_NAV_COLUMNS = "id, category_id, title, slug, language, sort_order"


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "project_id": row[1],
        "category_id": row[2],
        "title": row[3],
        "slug": row[4],
        "language": row[5],
        "markdown_content": row[6],
        "sort_order": row[7],
        "published": bool(row[8]),
        "created_at": row[9],
        "updated_at": row[10],
        "version": row[11],
    }


def _language_pair(language: str | None) -> tuple[str, str]:
    """(requested, default). `None` means "whatever the default is", which
    is what an unprefixed URL and every single-language install resolve
    to."""
    default = site_languages.default_language()
    return ((language or default), default)


def _priority(language: str | None) -> list[str]:
    """Which language to serve a reader of `language`, best first: their
    own, then the site's default, then whatever else the page exists in, in
    the order _site.yml lists them.

    The tail matters. A page that exists only in English is still a page a
    German reader can reach -- from a link, from search in English, or by
    switching language while reading it. Stopping the chain at the default
    language would 404 them at exactly that moment, which is the dead end
    this whole feature is supposed not to have. So the chain never runs out
    while any version of the page exists, and everything below the reader's
    own language is flagged `fallback` and says so on the page.

    On a single-language instance this is [""] -- every row, one language,
    no fallback anywhere."""
    requested, default = _language_pair(language)
    order = [requested]
    for code in [default, *site_languages.languages()]:
        if code not in order:
            order.append(code)
    return order


def _pick_one_per_slug(rows: list[dict], priority: list[str]) -> list[dict]:
    """Collapses per-language rows to one entry per slug: the best language
    available for this reader, by `priority`. The chosen entry carries
    `fallback` so a caller can mark a page that is only readable in another
    language -- dropping it instead would hide a page a reader can perfectly
    well read, and showing it silently would surprise them when they open
    it.

    Done in Python rather than in SQL: the alternative is a correlated
    NOT EXISTS per row on both backends (see search() below, where the
    filter genuinely has to happen inside the query to keep ranking and
    LIMIT honest), for a list this already holds in full."""
    rank = {code: index for index, code in enumerate(priority)}
    worst = len(priority)
    by_slug: dict[str, dict] = {}
    for row in rows:
        current = by_slug.get(row["slug"])
        if current is not None and rank.get(current["language"], worst) <= rank.get(row["language"], worst):
            continue
        by_slug[row["slug"]] = {**row, "fallback": row["language"] != priority[0]}
    # Re-sorted rather than kept in arrival order: a better-ranked row can
    # replace an earlier entry, which moves it in the dict.
    return sorted(by_slug.values(), key=lambda entry: (entry["sort_order"], entry["title"]))


def list_pages(category_id: int, published_only: bool = False, language: str | None = None) -> list[dict]:
    """No version parameter: a category id already belongs to exactly one
    version (categories are per version too), so its pages can only be that
    version's."""
    placeholder = "%s" if db.is_postgres() else "?"
    query = f"SELECT {_COLUMNS} FROM pages WHERE category_id = {placeholder}"
    params: tuple = (category_id,)
    if published_only:
        query += " AND published = " + ("TRUE" if db.is_postgres() else "1")
    query += " ORDER BY sort_order, title"
    with db.get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return _pick_one_per_slug([_row_to_dict(r) for r in rows], _priority(language))


def list_all_pages(category_id: int) -> list[dict]:
    """Every language variant as its own entry, for the ADMIN page list --
    which is the one place that has to show what does and doesn't exist per
    language rather than hiding it behind a fallback."""
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM pages WHERE category_id = {placeholder} ORDER BY sort_order, title, language",
            (category_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_project_pages(
    project_id: int, published_only: bool = False, language: str | None = None, version: str = ""
) -> list[dict]:
    """Every page of one project at once, for the caller to group by
    category itself. The docs sidebar needs a project's whole tree on every
    single page view, and building it by walking list_pages() per category
    would put one round trip per category on that path.

    markdown_content is deliberately not in _NAV_COLUMNS: a navigation tree
    needs titles, and selecting every page's full body to build one would be
    by far the most expensive part of the query."""
    placeholder = "%s" if db.is_postgres() else "?"
    query = f"SELECT {_NAV_COLUMNS} FROM pages WHERE project_id = {placeholder} AND version = {placeholder}"
    params: tuple = (project_id, version)
    if published_only:
        query += " AND published = " + ("TRUE" if db.is_postgres() else "1")
    query += " ORDER BY sort_order, title"
    with db.get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    entries = [
        {"id": r[0], "category_id": r[1], "title": r[2], "slug": r[3], "language": r[4], "sort_order": r[5]}
        for r in rows
    ]
    return _pick_one_per_slug(entries, _priority(language))


def get_page(page_id: int) -> dict | None:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM pages WHERE id = {placeholder}", (page_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_page_by_slug(project_id: int, slug: str, language: str | None = None, version: str = "") -> dict | None:
    """Exactly this language's row, or None. Reader-facing callers want
    resolve_page() instead -- this one is for the write paths, which must
    never silently edit a different language's file than the one asked
    for."""
    requested, _ = _language_pair(language)
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM pages WHERE project_id = {placeholder} AND slug = {placeholder} "
            f"AND language = {placeholder} AND version = {placeholder}",
            (project_id, slug, requested, version),
        ).fetchone()
    return _row_to_dict(row) if row else None


def resolve_page(
    project_id: int, slug: str, language: str | None = None, published_only: bool = False, version: str = ""
) -> dict | None:
    """The page to SERVE a reader of `language`: their own translation, or
    the best other one there is (see _priority), with `fallback` saying
    which happened. None only when the page exists in no language at all --
    a missing translation is never a 404, it's a notice on an otherwise
    normal page.

    published_only skips unpublished rows anywhere in the chain, which is
    what the public site wants: a half-finished English draft must not
    shadow the published German page it was translated from -- from out
    there, that page simply isn't translated yet."""
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM pages WHERE project_id = {placeholder} AND slug = {placeholder} "
            f"AND version = {placeholder}",
            (project_id, slug, version),
        ).fetchall()
    pages = [_row_to_dict(r) for r in rows]
    priority = _priority(language)
    for candidate_language in priority:
        for page in pages:
            if page["language"] != candidate_language:
                continue
            if published_only and not page["published"]:
                continue
            return {**page, "fallback": candidate_language != priority[0]}
    return None


def page_languages(project_id: int, slug: str, version: str = "") -> list[str]:
    """Which languages this page exists in at all -- what the admin editor's
    tab strip needs to show which translations are there and which are still
    missing."""
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT language FROM pages WHERE project_id = {placeholder} AND slug = {placeholder} "
            f"AND version = {placeholder} ORDER BY language",
            (project_id, slug, version),
        ).fetchall()
    return [r[0] for r in rows]


def slug_taken(project_id: int, version: str, slug: str, exclude_id: int | None = None) -> bool:
    """Any language counts: a slug identifies the page, not one translation
    of it, so a NEW page must not land on a slug some other page already
    uses in a language nobody is looking at right now.

    Scoped to ONE version, though: `installation` in v2.0 and `installation`
    in current are the same page at two points in time, in two separate
    directories -- one must not push the other's slug to `installation-2`."""
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        if exclude_id is not None:
            row = conn.execute(
                f"SELECT 1 FROM pages WHERE project_id = {placeholder} AND version = {placeholder} "
                f"AND slug = {placeholder} AND id != {placeholder}",
                (project_id, version, slug, exclude_id),
            ).fetchone()
        else:
            row = conn.execute(
                f"SELECT 1 FROM pages WHERE project_id = {placeholder} AND version = {placeholder} "
                f"AND slug = {placeholder}",
                (project_id, version, slug),
            ).fetchone()
    return row is not None


def page_versions(project_id: int, slug: str, published_only: bool = False) -> list[str]:
    """Which versions this page slug exists in -- what the version switcher
    needs to decide between staying on this page and landing on the
    version's home, rather than sending a reader to a 404 to find out."""
    placeholder = "%s" if db.is_postgres() else "?"
    query = f"SELECT DISTINCT version FROM pages WHERE project_id = {placeholder} AND slug = {placeholder}"
    if published_only:
        query += " AND published = " + ("TRUE" if db.is_postgres() else "1")
    with db.get_connection() as conn:
        rows = conn.execute(query, (project_id, slug)).fetchall()
    return [r[0] for r in rows]


def _next_order(category_id: int) -> int:
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT COALESCE(MAX(sort_order), -1) + 1 FROM pages WHERE category_id = {placeholder}",
            (category_id,),
        ).fetchone()
    return row[0]


def create_page(
    project_id: int,
    category_id: int,
    title: str,
    slug: str,
    markdown_content: str,
    author: str,
    language: str | None = None,
) -> dict | None:
    """`language` None means the instance's default -- which is what every
    "new page" is, and the only thing a single-language install ever has.
    A TRANSLATION is this same call with the existing page's slug and the
    language being written, which is why the slug is a parameter rather than
    something derived from the title here: `installation.en.md` has to land
    on `installation`, whatever "Installation" happens to be called in
    English."""
    project = projects_store.get_project(project_id)
    category = categories_store.get_category(category_id)
    if project is None or category is None:
        return None
    # The version is the CATEGORY's, not a parameter: a page lives in a
    # category directory, so which version it belongs to is already decided
    # by the category it is being created in. A frozen one is refused here
    # rather than after the file has been written.
    version = category["version"]
    content_versions.ensure_writable(project["slug"], version)
    requested, _ = _language_pair(language)
    # A translation takes the position the page already has: order is a
    # property of the page, and a fresh MAX+1 here would put the English
    # "Installation" last in the English sidebar while the German one sits
    # first -- the same page in two places depending on the language.
    siblings = [get_page_by_slug(project_id, slug, code, version) for code in page_languages(project_id, slug, version)]
    existing_order = next((s["sort_order"] for s in siblings if s is not None), None)
    order = _next_order(category_id) if existing_order is None else existing_order
    paths = content_files.write_page(
        project["slug"], category["slug"], slug, title, markdown_content, order, False, requested, version
    )
    git_content_repo.commit_and_push(paths, f"Add page: {title} [{requested or 'default'}]", author)
    content_sync.full_sync()
    return get_page_by_slug(project_id, slug, requested, version)


def update_page(page_id: int, title: str, slug: str, markdown_content: str, category_id: int, author: str) -> dict | None:
    current = get_page(page_id)
    if current is None:
        return None
    project = projects_store.get_project(current["project_id"])
    old_category = categories_store.get_category(current["category_id"])
    new_category = categories_store.get_category(category_id)
    if project is None or old_category is None or new_category is None:
        return None
    version = current["version"]
    content_versions.ensure_writable(project["slug"], version)
    if new_category["version"] != version:
        # The category dropdown only ever offers the page's own version's
        # categories, so this is a hand-built request: moving a page across
        # versions is not an edit, it is rewriting what a release said.
        return None

    # A slug change or a category change moves EVERY language variant of the
    # page (see content_files.relocate_page): the slug is what makes them one
    # page, so it can only change for all of them at once.
    paths = content_files.relocate_page(
        project["slug"], old_category["slug"], current["slug"], new_category["slug"], slug, version
    )
    order = current["sort_order"] if new_category["id"] == old_category["id"] else _next_order(category_id)
    paths += content_files.write_page(
        project["slug"], new_category["slug"], slug, title, markdown_content, order, current["published"],
        current["language"], version,
    )
    git_content_repo.commit_and_push(paths, f"Update page: {title}", author)
    content_sync.full_sync()
    return get_page_by_slug(current["project_id"], slug, current["language"], version)


def set_published(page_id: int, published: bool, author: str) -> dict | None:
    current = get_page(page_id)
    if current is None:
        return None
    project = projects_store.get_project(current["project_id"])
    category = categories_store.get_category(current["category_id"])
    content_versions.ensure_writable(project["slug"], current["version"])
    # Per language: a translation that isn't finished stays a draft while
    # the language it was translated from is published.
    paths = content_files.write_page(
        project["slug"], category["slug"], current["slug"], current["title"], current["markdown_content"],
        current["sort_order"], published, current["language"], current["version"],
    )
    verb = "Publish" if published else "Unpublish"
    git_content_repo.commit_and_push(paths, f"{verb} page: {current['title']}", author)
    content_sync.full_sync()
    return get_page(page_id)


def _write_order(project_slug: str, category_slug: str, project_id: int, slug: str, order: int, version: str) -> list[str]:
    """Writes one page's new sort_order into EVERY language variant's file.
    Order is a property of the page, not of one translation: letting the
    German and English files drift apart would give a reader who switches
    language a differently ordered sidebar and a different next/previous
    page."""
    paths: list[str] = []
    for language in page_languages(project_id, slug, version):
        variant = get_page_by_slug(project_id, slug, language, version)
        if variant is None:
            continue
        paths += content_files.write_page(
            project_slug, category_slug, slug, variant["title"], variant["markdown_content"], order,
            variant["published"], language, version,
        )
    return paths


def reorder_page(category_id: int, page_id: int, direction: int, author: str) -> None:
    pages = list_pages(category_id)
    index = next((i for i, pg in enumerate(pages) if pg["id"] == page_id), None)
    if index is None:
        return
    swap_index = index + direction
    if not (0 <= swap_index < len(pages)):
        return
    a, b = pages[index], pages[swap_index]
    project = projects_store.get_project(a["project_id"])
    category = categories_store.get_category(category_id)
    version = category["version"]
    content_versions.ensure_writable(project["slug"], version)
    paths = _write_order(project["slug"], category["slug"], a["project_id"], a["slug"], b["sort_order"], version)
    paths += _write_order(project["slug"], category["slug"], b["project_id"], b["slug"], a["sort_order"], version)
    git_content_repo.commit_and_push(paths, f"Reorder pages: {a['title']} / {b['title']}", author)
    content_sync.full_sync()


def delete_page(page_id: int, author: str) -> None:
    """Removes the page, translations included -- one page, one delete (see
    content_files.delete_page). Removing a single translation and keeping
    the rest is a file deletion in the content repo; offering it as a button
    next to the whole-page delete would be two very similar controls with
    very different consequences."""
    current = get_page(page_id)
    if current is None:
        return
    project = projects_store.get_project(current["project_id"])
    category = categories_store.get_category(current["category_id"])
    content_versions.ensure_writable(project["slug"], current["version"])
    paths = content_files.delete_page(project["slug"], category["slug"], current["slug"], current["version"])
    if paths:
        git_content_repo.commit_and_push(paths, f"Remove page: {current['title']}", author)
        content_sync.full_sync()


# ---- Change history ----
#
# Every page is a file in a git repository and every save is a commit, so a
# complete, attributed history already exists -- these functions only make it
# visible. They are the join between the index (which knows what a page id
# means) and git_content_repo (which knows what happened to a file); no git
# command is run here, and none of them changes anything, except restore_page,
# which is an ordinary write that happens to take its text from the past.
#
# All of this is per LANGUAGE, because a page's translations are separate
# files with separate histories: the German file's log says nothing about when
# the English one was last touched, and pretending otherwise would attribute
# somebody's edit to a text they never opened.


def _page_file(page: dict) -> tuple[dict, dict, str] | None:
    """(project row, category row, repo-relative path of this page's file), or
    None when any of the three can't be resolved -- which a caller shows as
    "nothing is known about this file", never as an error."""
    project = projects_store.get_project(page["project_id"])
    category = categories_store.get_category(page["category_id"])
    if project is None or category is None:
        return None
    path = content_files.page_repo_path(
        project["slug"], category["slug"], page["slug"], page["language"], page["version"]
    )
    return project, category, path


def last_updated(project_slug: str, category_slug: str, page: dict) -> str:
    """The ISO date this page's FILE last changed in the content repo, or ""
    when that isn't knowable (no content repo, no commits yet, a file git has
    never seen).

    Deliberately not the row's `updated_at`: that column belongs to the index,
    and the index gets rebuilt -- by a reindex, by a schema change, by a fresh
    clone on a new machine -- none of which is a change to the page. Telling a
    reader a page was updated on the day the container happened to restart is
    worse than telling them nothing. Git is the only place that knows when the
    content itself last moved.

    Takes the slugs the caller already holds rather than a page id, because
    every caller is already looking at the project and category rows it would
    otherwise have to query again on the path of a public page view."""
    return git_content_repo.last_modified(
        content_files.page_repo_path(project_slug, category_slug, page["slug"], page["language"], page["version"])
    )


def page_history(page_id: int, limit: int = git_content_repo.DEFAULT_HISTORY) -> dict | None:
    """This page's commits, newest first, plus enough context for the panel
    showing them to say WHICH file it is the history of -- the path names the
    language, and a page's translations each have their own.

    None only when the page id names nothing. An empty `commits` list is a
    perfectly ordinary answer: an instance with no content repo, a file that
    has never been committed, a repo with no commits at all."""
    page = get_page(page_id)
    if page is None:
        return None
    resolved = _page_file(page)
    if resolved is None:
        return None
    project, _, path = resolved
    return {
        "path": path,
        "language": page["language"],
        "version": page["version"],
        # The panel reads a frozen version's history normally and only hides
        # the restore button; the API refuses the write regardless (see
        # restore_page).
        "frozen": content_versions.is_frozen(project["slug"], page["version"]),
        "commits": git_content_repo.page_history(path, limit),
    }


def _history_entry(path: str, sha: str) -> dict | None:
    """The one commit `sha` names in THIS file's history, or None.

    Looking the sha up in the file's own history rather than handing it
    straight to git is what makes a sha from a URL safe to act on: only a
    commit that actually touched this page can be read back or restored, so no
    crafted (or simply mistaken) sha can reach another file in the repo. It
    also resolves which name the file had at that commit, which is what makes
    a version from before a rename readable at all.

    Searched to MAX_HISTORY rather than to the panel's own limit, so anything
    the panel could have listed is also restorable."""
    for entry in git_content_repo.page_history(path, git_content_repo.MAX_HISTORY):
        # Equal, or the caller passed the full sha of the abbreviation git
        # printed -- someone reading `git log` in the repo itself has the
        # long one.
        if entry["sha"] == sha or sha.startswith(entry["sha"]):
            return entry
    return None


def page_at_commit(page_id: int, sha: str) -> dict | None:
    """One version of this page: the commit's own metadata, the title and
    Markdown it held then, and the diff of what that commit changed.

    None when the page, the commit, or the file at that commit isn't there.
    The FIRST commit for a file needs no special handling -- its diff is the
    whole file as additions, and `status` is "A", which is how a caller knows
    there was no predecessor to compare against rather than having to guess
    from an empty diff."""
    page = get_page(page_id)
    if page is None:
        return None
    resolved = _page_file(page)
    if resolved is None:
        return None
    _, _, path = resolved
    entry = _history_entry(path, sha)
    if entry is None:
        return None
    text = git_content_repo.file_at(entry["path"], entry["sha"])
    if text is None:
        return None
    document = content_files.parse_page_document(text)
    return {
        **entry,
        "title": document["title"],
        "markdown_content": document["markdown_content"],
        "published": document["published"],
        "diff": git_content_repo.diff(entry["path"], entry["sha"]),
    }


def restore_page(page_id: int, sha: str, author: str) -> dict | None:
    """Writes the title and Markdown this page had at `sha` back as a NEW
    commit on top of the history. Nothing is rewritten, nothing is reverted,
    no old commit is touched: the version being replaced stays in the log
    right where it is, and undoing a restore is the same button again on the
    commit above it.

    Three things deliberately do NOT come back with the text, and each is a
    rule that already exists elsewhere in this module rather than a special
    case invented here:

    - The page's POSITION. sort_order belongs to the page across all of its
      translations (see _write_order) -- restoring one language's old position
      would give a reader who switches language a differently ordered sidebar.
    - Whether it is PUBLISHED. That is a decision about what readers should
      see right now, not text somebody wrote in the past; a restore must never
      quietly take a live page off the site.
    - Its ADDRESS. The slug is the page's URL and is shared by its
      translations, so an old title is written into the frontmatter while the
      file stays exactly where it is. An admin who wants the old title's URL
      back renames the page, which is what the title field already does.

    Subject to every rule any other write is subject to: a frozen version is
    refused before anything is read or written (with its usual message), and
    the write goes through the same content_files -> commit -> push -> reindex
    path as a save from the editor."""
    current = get_page(page_id)
    if current is None:
        return None
    project = projects_store.get_project(current["project_id"])
    category = categories_store.get_category(current["category_id"])
    if project is None or category is None:
        return None
    # Before the history is even read: a frozen version answers with the
    # frozen message, not with a restore that turns out to be refused later.
    content_versions.ensure_writable(project["slug"], current["version"])

    version = page_at_commit(page_id, sha)
    if version is None:
        return None

    # A version whose frontmatter has no title at all (hand-written in the
    # repo, say) keeps the page's current one rather than blanking it -- a
    # title is structural, and the editor's own save would reject an empty one.
    title = version["title"] or current["title"]
    paths = content_files.write_page(
        project["slug"], category["slug"], current["slug"], title, version["markdown_content"],
        current["sort_order"], current["published"], current["language"], current["version"],
    )
    message = (
        f"Restore page: {title} [{current['language'] or 'default'}] to {version['sha']}"
        f"\n\nThe content of commit {version['sha']} (\"{version['subject']}\") written back as a new commit. "
        f"Nothing was removed from the history: that commit, and every commit since, are still there."
    )
    git_content_repo.commit_and_push(paths, message, author)
    content_sync.full_sync()
    return get_page_by_slug(current["project_id"], current["slug"], current["language"], current["version"])


def _fts5_query(raw: str) -> str | None:
    terms = [t.replace('"', '') for t in raw.strip().split() if t.strip()]
    terms = [t for t in terms if t]
    if not terms:
        return None
    return " OR ".join(f'"{t}"' for t in terms)


# Language filter for search, shared by both backends' queries below (only
# the placeholder and the boolean literal differ).
#
# A row survives only if this page has no published version in a language
# the reader would rather have -- so searching in English returns the
# English page, never the English page AND its German original as if they
# were two results, and returns the German one only when there is no
# English version to prefer. Which is exactly the set the sidebar shows.
#
# "would rather have" is _priority()'s order, encoded as a CASE that turns
# a language code into a rank; comparing two ranks then expresses the whole
# chain in one correlated NOT EXISTS. This has to happen inside the query
# rather than in a pass over the results (which is how the nav lists do it,
# where the caller holds every row anyway) because ranking and LIMIT happen
# in the database: filtering afterwards would quietly return fewer than
# `limit` hits, or none at all.
_LANGUAGE_FILTER = """
              AND NOT EXISTS (
                    SELECT 1 FROM pages t
                    WHERE t.project_id = p.project_id AND t.slug = p.slug AND t.published = {true}
                      AND {rank_t} < {rank_p}
              )
"""


def _rank_case(column: str, priority: list[str], placeholder: str) -> str:
    """`CASE <column> WHEN ? THEN 0 WHEN ? THEN 1 ... ELSE n END` -- the
    language codes stay parameterized (they reach here from a URL)."""
    whens = " ".join(f"WHEN {placeholder} THEN {index}" for index in range(len(priority)))
    return f"CASE {column} {whens} ELSE {len(priority)} END"


def _language_filter(priority: list[str], placeholder: str, true_literal: str) -> str:
    return _LANGUAGE_FILTER.format(
        true=true_literal,
        rank_t=_rank_case("t.language", priority, placeholder),
        rank_p=_rank_case("p.language", priority, placeholder),
    )


# Which (project, version) pairs a search may return rows from -- the whole
# version scoping, in one WHERE clause.
#
# A reader inside a version is searching THAT version: the results they can
# act on are the ones in the docs in front of them, and a hit in a release
# they aren't reading would send them out of it without saying so. A reader
# who is not inside any version (the home page, the search page itself)
# searches each project's DEFAULT version -- one hit per page, rather than
# the same paragraph three times because three releases documented it.
#
# Expressed as OR'd pairs rather than a row-value IN: a project's default
# version comes from its own `_versions.yml`, so this is a handful of
# literal pairs either way, and OR'd equalities work identically on both
# backends. Like _LANGUAGE_FILTER, it has to be inside the query, because
# ranking and LIMIT happen in the database.
def _version_filter(pairs: list[tuple[int, str]], placeholder: str) -> str:
    clauses = " OR ".join(f"(p.project_id = {placeholder} AND p.version = {placeholder})" for _ in pairs)
    return f"              AND ({clauses})\n"


def _default_version_pairs() -> list[tuple[int, str]]:
    """(project id, that project's default version) for every project -- ''
    for the unversioned ones, which is exactly the version their rows carry,
    so an instance where nothing is versioned gets `p.version = ''` for
    every project and searches precisely the set it always searched."""
    with db.get_connection() as conn:
        rows = conn.execute("SELECT id, slug FROM projects").fetchall()
    return [(row[0], content_versions.default_version(row[1])) for row in rows]


def search(
    query: str,
    limit: int = 20,
    language: str | None = None,
    project_id: int | None = None,
    version: str | None = None,
) -> list[dict]:
    """Published pages only, in ONE language (see _LANGUAGE_FILTER) and in
    ONE version per project (see _version_filter): the version being read
    when `project_id`/`version` name one, each project's default version
    otherwise. Each result also carries its project/category name+slug so
    the UI can show where a hit lives, and `language` + `fallback` so it can
    link to the right URL and mark a hit that isn't in the language the
    reader searched in.

    The full-text index itself is not per-language and doesn't need to be:
    it indexes each row's own title and body, and each row IS one language's
    text, so a German page only ever matches German words. What the language
    dimension changes is WHICH rows are eligible, which is a plain WHERE on
    `pages` alongside the published filter -- no second index, and no
    stemming configuration to get wrong per language (both backends already
    search unstemmed, see this module's docstring)."""
    query = query.strip()
    if not query:
        return []
    priority = _priority(language)
    # The two rank CASEs in the filter take the priority list once each, in
    # the order they appear in the SQL text (t's, then p's).
    language_params = (*priority, *priority)

    pairs = [(project_id, version or "")] if project_id is not None and version is not None else _default_version_pairs()
    if not pairs:
        return []  # no projects at all -- nothing could match anyway
    version_params = tuple(value for pair in pairs for value in pair)

    if db.is_postgres():
        sql = f"""
            SELECT p.id, p.title, p.slug, p.markdown_content, pr.name, pr.slug, c.name, c.slug,
                   p.language, pr.name_i18n, c.name_i18n, p.version
            FROM pages p
            JOIN projects pr ON pr.id = p.project_id
            JOIN categories c ON c.id = p.category_id
            WHERE p.published = TRUE
              AND to_tsvector('simple', p.title || ' ' || p.markdown_content) @@ plainto_tsquery('simple', %s)
              {_language_filter(priority, "%s", "TRUE")}
{_version_filter(pairs, "%s")}
            ORDER BY ts_rank(to_tsvector('simple', p.title || ' ' || p.markdown_content), plainto_tsquery('simple', %s)) DESC
            LIMIT %s
        """
        with db.get_connection() as conn:
            rows = conn.execute(sql, (query, *language_params, *version_params, query, limit)).fetchall()
    else:
        fts_query = _fts5_query(query)
        if fts_query is None:
            return []
        sql = f"""
            SELECT p.id, p.title, p.slug, p.markdown_content, pr.name, pr.slug, c.name, c.slug,
                   p.language, pr.name_i18n, c.name_i18n, p.version
            FROM pages_fts
            JOIN pages p ON p.id = pages_fts.rowid
            JOIN projects pr ON pr.id = p.project_id
            JOIN categories c ON c.id = p.category_id
            WHERE pages_fts MATCH ? AND p.published = 1
              {_language_filter(priority, "?", "1")}
{_version_filter(pairs, "?")}
            ORDER BY bm25(pages_fts)
            LIMIT ?
        """
        with db.get_connection() as conn:
            rows = conn.execute(sql, (fts_query, *language_params, *version_params, limit)).fetchall()

    results = []
    for r in rows:
        snippet_source = r[3] or ""
        snippet = snippet_source[:220] + ("..." if len(snippet_source) > 220 else "")
        results.append(
            {
                "page_id": r[0],
                "title": r[1],
                "page_slug": r[2],
                "snippet": snippet,
                # The project/category names come out of the same rows the
                # tiles and the sidebar use, so a hit is labelled with the
                # names the reader has been seeing, not the default
                # language's.
                "project_name": site_languages.pick(r[4], site_languages.parse_i18n(r[9]), priority[0]),
                "project_slug": r[5],
                "category_name": site_languages.pick(r[6], site_languages.parse_i18n(r[10]), priority[0]),
                "category_slug": r[7],
                "language": r[8],
                "fallback": r[8] != priority[0],
                # Which version this hit is in, so the result link lands in
                # the same docs the reader is standing in.
                "version": r[11],
            }
        )
    return results
