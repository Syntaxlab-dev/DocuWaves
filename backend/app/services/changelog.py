"""What is new in the docs: the public changelog and its RSS feeds.

Built from the content repo's history, not from the index. The index's
`updated_at` is rewritten by every reindex (see pages_store.last_updated),
and a changelog claiming that everything changed the day the container
restarted would be worse than none.

WHAT COUNTS, per page file and commit, newest first:

- "new"      the page is published after the commit and was not before it
             (created published, or a draft that went live)
- "updated"  it was published before and after, and its title or text changed

Everything else a commit can do to a page file -- reorder it, mark it
reviewed, touch its frontmatter -- is not news to a reader and is skipped. A
page appears once, with its newest qualifying change. Only pages that are
published NOW, in each project's default version, are listed: a page that
was published and later withdrawn is gone from the changelog too.

WHAT IS SAID: the title, the date, new/updated, where it lives, and the
opening of its text. Never the commit message or its author -- the public
side says no more about the history than a date (see pages_store).

Cached per HEAD: the walk reads two versions of each candidate file, which
is the one expensive thing here, and nothing about the answer can change
while HEAD stands still.
"""
import threading

from app.services import content_versions, db, git_content_repo, prose, seo, site_languages, snippets
from app.services.content_files import parse_page_document

MAX_ENTRIES = 100
_SUMMARY_CHARS = 240

_lock = threading.Lock()
_cache: tuple[str, list[dict]] | None = None


def _published_pages() -> dict[str, dict]:
    """repo path -> the page, for every page published now in its project's
    default version. One query."""
    true = "TRUE" if db.is_postgres() else "1"
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT p.title, p.slug, p.language, p.version, p.markdown_content, "
            "pr.slug, pr.name, pr.name_i18n, c.slug, c.name, c.name_i18n "
            "FROM pages p JOIN projects pr ON pr.id = p.project_id JOIN categories c ON c.id = p.category_id "
            f"WHERE p.published = {true}"
        ).fetchall()
    defaults: dict[str, str] = {}
    pages: dict[str, dict] = {}
    for r in rows:
        project_slug = r[5]
        if project_slug not in defaults:
            defaults[project_slug] = content_versions.default_version(project_slug)
        if r[3] != defaults[project_slug]:
            continue
        page = {
            "title": r[0], "slug": r[1], "language": r[2], "version": r[3], "markdown_content": r[4],
            "project_slug": project_slug, "project_name": r[6], "project_name_i18n": r[7],
            "category_slug": r[8], "category_name": r[9], "category_name_i18n": r[10],
        }
        pages[seo.page_file(project_slug, r[8], r[1], r[2], r[3])] = page
    return pages


def _kind(change: dict) -> str | None:
    if change["status"] == "D":
        return None
    after_text = git_content_repo.blob_text(change["sha"], change["path"])
    if after_text is None:
        return None
    after = parse_page_document(after_text)
    if not after["published"]:
        return None
    before_text = git_content_repo.blob_text(change["parent"], change["path"]) if change["parent"] else None
    before = parse_page_document(before_text) if before_text is not None else None
    if before is None or not before["published"]:
        return "new"
    if (before["title"], before["markdown_content"].strip()) != (after["title"], after["markdown_content"].strip()):
        return "updated"
    return None


def _build() -> list[dict]:
    pages = _published_pages()
    entries: list[dict] = []
    seen: set[str] = set()
    for change in git_content_repo.recent_file_changes("content/"):
        path = change["path"]
        if path in seen or path not in pages:
            continue
        kind = _kind(change)
        if kind is None:
            continue  # this commit was not news; an older one may be
        seen.add(path)
        page = pages[path]
        body = snippets.resolve(page["markdown_content"], page["project_slug"], page["version"], page["language"])
        entries.append({**page, "kind": kind, "date": change["date"][:10], "timestamp": change["date"],
                        "summary": prose.first_paragraph(body, _SUMMARY_CHARS)})
        if len(entries) >= MAX_ENTRIES:
            break
    return entries


def _all() -> list[dict]:
    global _cache
    head = git_content_repo.head_sha()
    if not head:
        return []
    with _lock:
        if _cache is None or _cache[0] != head:
            _cache = (head, _build())
        return _cache[1]


def entries(language: str = "", project_slug: str = "", limit: int = 50) -> list[dict]:
    """The changelog as a reader in `language` sees it, newest first,
    optionally for one project."""
    out = []
    for entry in _all():
        if project_slug and entry["project_slug"] != project_slug:
            continue
        # On a multilingual site each language has its own changelog: a
        # German reader is not told about an English text they won't get.
        if entry["language"] and language and entry["language"] != language:
            continue
        out.append({
            "kind": entry["kind"],
            "date": entry["date"],
            "timestamp": entry["timestamp"],
            "title": entry["title"],
            "summary": entry["summary"],
            "page_slug": entry["slug"],
            "language": entry["language"],
            "project_slug": entry["project_slug"],
            "project_name": site_languages.pick(
                entry["project_name"], site_languages.parse_i18n(entry["project_name_i18n"]), language
            ),
            "category_name": site_languages.pick(
                entry["category_name"], site_languages.parse_i18n(entry["category_name_i18n"]), language
            ),
        })
        if len(out) >= limit:
            break
    return out
