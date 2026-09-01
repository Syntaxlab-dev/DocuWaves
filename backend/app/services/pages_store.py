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
    db,
    git_content_repo,
    projects_store,
    site_languages,
)

_COLUMNS = (
    "id, project_id, category_id, title, slug, language, markdown_content, sort_order, published, "
    "created_at, updated_at"
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


def list_project_pages(project_id: int, published_only: bool = False, language: str | None = None) -> list[dict]:
    """Every page of one project at once, for the caller to group by
    category itself. The docs sidebar needs a project's whole tree on every
    single page view, and building it by walking list_pages() per category
    would put one round trip per category on that path.

    markdown_content is deliberately not in _NAV_COLUMNS: a navigation tree
    needs titles, and selecting every page's full body to build one would be
    by far the most expensive part of the query."""
    placeholder = "%s" if db.is_postgres() else "?"
    query = f"SELECT {_NAV_COLUMNS} FROM pages WHERE project_id = {placeholder}"
    params: tuple = (project_id,)
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


def get_page_by_slug(project_id: int, slug: str, language: str | None = None) -> dict | None:
    """Exactly this language's row, or None. Reader-facing callers want
    resolve_page() instead -- this one is for the write paths, which must
    never silently edit a different language's file than the one asked
    for."""
    requested, _ = _language_pair(language)
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM pages WHERE project_id = {placeholder} AND slug = {placeholder} "
            f"AND language = {placeholder}",
            (project_id, slug, requested),
        ).fetchone()
    return _row_to_dict(row) if row else None


def resolve_page(project_id: int, slug: str, language: str | None = None, published_only: bool = False) -> dict | None:
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
            f"SELECT {_COLUMNS} FROM pages WHERE project_id = {placeholder} AND slug = {placeholder}",
            (project_id, slug),
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


def page_languages(project_id: int, slug: str) -> list[str]:
    """Which languages this page exists in at all -- what the admin editor's
    tab strip needs to show which translations are there and which are still
    missing."""
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT language FROM pages WHERE project_id = {placeholder} AND slug = {placeholder} ORDER BY language",
            (project_id, slug),
        ).fetchall()
    return [r[0] for r in rows]


def slug_taken(project_id: int, slug: str, exclude_id: int | None = None) -> bool:
    """Any language counts: a slug identifies the page, not one translation
    of it, so a NEW page must not land on a slug some other page already
    uses in a language nobody is looking at right now."""
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        if exclude_id is not None:
            row = conn.execute(
                f"SELECT 1 FROM pages WHERE project_id = {placeholder} AND slug = {placeholder} AND id != {placeholder}",
                (project_id, slug, exclude_id),
            ).fetchone()
        else:
            row = conn.execute(
                f"SELECT 1 FROM pages WHERE project_id = {placeholder} AND slug = {placeholder}",
                (project_id, slug),
            ).fetchone()
    return row is not None


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
    requested, _ = _language_pair(language)
    # A translation takes the position the page already has: order is a
    # property of the page, and a fresh MAX+1 here would put the English
    # "Installation" last in the English sidebar while the German one sits
    # first -- the same page in two places depending on the language.
    siblings = [get_page_by_slug(project_id, slug, code) for code in page_languages(project_id, slug)]
    existing_order = next((s["sort_order"] for s in siblings if s is not None), None)
    order = _next_order(category_id) if existing_order is None else existing_order
    paths = content_files.write_page(
        project["slug"], category["slug"], slug, title, markdown_content, order, False, requested
    )
    git_content_repo.commit_and_push(paths, f"Add page: {title} [{requested or 'default'}]", author)
    content_sync.full_sync()
    return get_page_by_slug(project_id, slug, requested)


def update_page(page_id: int, title: str, slug: str, markdown_content: str, category_id: int, author: str) -> dict | None:
    current = get_page(page_id)
    if current is None:
        return None
    project = projects_store.get_project(current["project_id"])
    old_category = categories_store.get_category(current["category_id"])
    new_category = categories_store.get_category(category_id)
    if project is None or old_category is None or new_category is None:
        return None

    # A slug change or a category change moves EVERY language variant of the
    # page (see content_files.relocate_page): the slug is what makes them one
    # page, so it can only change for all of them at once.
    paths = content_files.relocate_page(project["slug"], old_category["slug"], current["slug"], new_category["slug"], slug)
    order = current["sort_order"] if new_category["id"] == old_category["id"] else _next_order(category_id)
    paths += content_files.write_page(
        project["slug"], new_category["slug"], slug, title, markdown_content, order, current["published"],
        current["language"],
    )
    git_content_repo.commit_and_push(paths, f"Update page: {title}", author)
    content_sync.full_sync()
    return get_page_by_slug(current["project_id"], slug, current["language"])


def set_published(page_id: int, published: bool, author: str) -> dict | None:
    current = get_page(page_id)
    if current is None:
        return None
    project = projects_store.get_project(current["project_id"])
    category = categories_store.get_category(current["category_id"])
    # Per language: a translation that isn't finished stays a draft while
    # the language it was translated from is published.
    paths = content_files.write_page(
        project["slug"], category["slug"], current["slug"], current["title"], current["markdown_content"],
        current["sort_order"], published, current["language"],
    )
    verb = "Publish" if published else "Unpublish"
    git_content_repo.commit_and_push(paths, f"{verb} page: {current['title']}", author)
    content_sync.full_sync()
    return get_page(page_id)


def _write_order(project_slug: str, category_slug: str, project_id: int, slug: str, order: int) -> list[str]:
    """Writes one page's new sort_order into EVERY language variant's file.
    Order is a property of the page, not of one translation: letting the
    German and English files drift apart would give a reader who switches
    language a differently ordered sidebar and a different next/previous
    page."""
    paths: list[str] = []
    for language in page_languages(project_id, slug):
        variant = get_page_by_slug(project_id, slug, language)
        if variant is None:
            continue
        paths += content_files.write_page(
            project_slug, category_slug, slug, variant["title"], variant["markdown_content"], order,
            variant["published"], language,
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
    paths = _write_order(project["slug"], category["slug"], a["project_id"], a["slug"], b["sort_order"])
    paths += _write_order(project["slug"], category["slug"], b["project_id"], b["slug"], a["sort_order"])
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
    paths = content_files.delete_page(project["slug"], category["slug"], current["slug"])
    if paths:
        git_content_repo.commit_and_push(paths, f"Remove page: {current['title']}", author)
        content_sync.full_sync()


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


def search(query: str, limit: int = 20, language: str | None = None) -> list[dict]:
    """Published pages only, across every project, in ONE language (see
    _LANGUAGE_FILTER). Each result also carries its project/category
    name+slug so the UI can show where a hit lives, and `language` +
    `fallback` so it can link to the right URL and mark a hit that isn't in
    the language the reader searched in.

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

    if db.is_postgres():
        sql = f"""
            SELECT p.id, p.title, p.slug, p.markdown_content, pr.name, pr.slug, c.name, c.slug,
                   p.language, pr.name_i18n, c.name_i18n
            FROM pages p
            JOIN projects pr ON pr.id = p.project_id
            JOIN categories c ON c.id = p.category_id
            WHERE p.published = TRUE
              AND to_tsvector('simple', p.title || ' ' || p.markdown_content) @@ plainto_tsquery('simple', %s)
              {_language_filter(priority, "%s", "TRUE")}
            ORDER BY ts_rank(to_tsvector('simple', p.title || ' ' || p.markdown_content), plainto_tsquery('simple', %s)) DESC
            LIMIT %s
        """
        with db.get_connection() as conn:
            rows = conn.execute(sql, (query, *language_params, query, limit)).fetchall()
    else:
        fts_query = _fts5_query(query)
        if fts_query is None:
            return []
        sql = f"""
            SELECT p.id, p.title, p.slug, p.markdown_content, pr.name, pr.slug, c.name, c.slug,
                   p.language, pr.name_i18n, c.name_i18n
            FROM pages_fts
            JOIN pages p ON p.id = pages_fts.rowid
            JOIN projects pr ON pr.id = p.project_id
            JOIN categories c ON c.id = p.category_id
            WHERE pages_fts MATCH ? AND p.published = 1
              {_language_filter(priority, "?", "1")}
            ORDER BY bm25(pages_fts)
            LIMIT ?
        """
        with db.get_connection() as conn:
            rows = conn.execute(sql, (fts_query, *language_params, limit)).fetchall()

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
            }
        )
    return results
