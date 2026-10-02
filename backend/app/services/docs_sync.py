"""Docs-as-code: a project whose documentation lives in a code repository.

The code repo's CI packs its `docs/` folder into a ZIP and POSTs it to
`/api/sync/<project>` with a SYNC token -- a token that can do exactly one
thing: replace that one project's content (api_tokens_store.SYNC_SCOPE).
DocuWaves never gets access to the code repository itself.

WHAT A SYNC DOES. The archive is read by the importer (services/importer.py,
`sync=True`) -- every format it knows, the same link and image handling --
and then BECOMES the project's content in its writable version:

- pages and categories that are in the archive are written, everything the
  project had that is not in it is removed (so deleting a file in the repo
  deletes the page);
- a page's address comes from its FILE NAME, not its title, so a reworded
  heading never breaks a link; `slug:` in the front matter pins it;
- pages are PUBLISHED: they went through review as a pull request in the
  code repo, which is the approval -- `draft: true` (or `published: false`)
  in the front matter keeps one a draft. The project's own approval setting
  does not apply to what a sync writes;
- images go to `assets/sync/`, which the sync owns and rewrites whole.

ONE COMMIT per sync ("Sync from <ref>"), and NONE when nothing changed --
running the same CI job twice is a no-op, so it is safe to sync on every
push. Every run is recorded (sync_runs) with what it added, changed and
removed.

Webhooks fire as for any edit -- except on the first sync into an empty
project, which would otherwise announce every page of the docs at once.

WHAT IS LOST: anything written in DocuWaves itself inside this project --
an edit in the editor, a translation -- is replaced by the next sync. The
repository is the source.
"""
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import yaml

from app.services import (
    categories_store,
    content_files,
    content_sync,
    content_versions,
    db,
    git_content_repo,
    importer,
    pages_store,
    projects_store,
    webhooks,
)

_REF_MAX = 80
# Which page came from which file: what "edit in the repository" links to.
# In the project's version directory, next to its categories; rewritten by
# every sync, and unchanged (so no diff) when the files did not change.
SOURCES_FILE = "_sync.yml"


class SyncError(Exception):
    pass


def _placeholder() -> str:
    return "%s" if db.is_postgres() else "?"


def _current(project: dict, version: str) -> dict[str, dict]:
    """The project's pages now, default language only, by slug."""
    pages: dict[str, dict] = {}
    for category in categories_store.list_categories(project["id"], version=version):
        for page in pages_store.list_all_pages(category["id"]):
            pages.setdefault(page["slug"], {**page, "category_slug": category["slug"]})
    return pages


def sync(data: bytes, project_slug: str, author: str, ref: str = "", source: dict | None = None) -> dict:
    """`source`: where the docs live ({repo, branch, path}), when the CI says
    so -- it becomes the project's `source:` (and with it the "edit in the
    repository" links). Left out, the project keeps what it has."""
    project = projects_store.get_project_by_slug(project_slug)
    if project is None:
        raise SyncError(f"There is no project '{project_slug}'. Create it in the admin area first.")
    ref = "".join(ch for ch in (ref or "") if ch.isprintable()).strip()[:_REF_MAX]

    with pages_store._update_lock:
        result = importer.plan(data, project_slug=project_slug, sync=True)
        version = result.version
        content_versions.ensure_writable(project_slug, version)
        before = _current(project, version)
        first_sync = not before

        # Everything the project has goes -- then the archive is written.
        # Files that come back unchanged produce no change in git at all.
        paths: list[str] = []
        for category in categories_store.list_categories(project["id"], version=version):
            paths += content_files.delete_category(project_slug, category["slug"], version)
        sync_assets = content_files.project_content_dir(project_slug, version) / "assets" / "sync"
        if sync_assets.exists():
            for old in sync_assets.rglob("*"):
                if old.is_file():
                    paths.append(content_files._rel(old))
                    old.unlink()

        after: dict[str, dict] = {}
        for category in result.categories:
            if not category.pages:
                continue
            paths += content_files.write_category(
                project_slug, category.slug, category.name, category.icon, "", category.order, version=version
            )
            for page in category.pages:
                paths += content_files.write_page(
                    project_slug, category.slug, page.slug, page.title, page.body, page.order, page.published,
                    "", version, review={},
                )
                after[page.slug] = {
                    "title": page.title, "markdown_content": page.body, "published": page.published,
                    "category_slug": category.slug, "slug": page.slug, "language": "", "version": version,
                }
        sources_path = content_files.project_content_dir(project_slug, version) / SOURCES_FILE
        sources_path.write_text(
            yaml.safe_dump(
                {"pages": {p.slug: p.source for c in result.categories for p in c.pages}},
                sort_keys=True, allow_unicode=True,
            ),
            encoding="utf-8",
        )
        paths.append(content_files._rel(sources_path))
        # The first sync makes it official: from now on the project's pages
        # are read-only in the editor (content_versions.ensure_editable).
        wanted = content_files.normalize_source({**(project.get("source") or {}), **(source or {})})
        if project.get("source") != wanted:
            paths += content_files.write_project(
                project["slug"], project["name"], project["icon"], project["color"], project["image"],
                project["description"], project["sort_order"], project["name_i18n"], project["description_i18n"],
                project["private"], project["review_required"], wanted,
            )
        asset_dir = content_files.project_content_dir(project_slug, version) / "assets"
        for source, target in result.assets.items():
            destination = asset_dir / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(result.asset_bytes[source])
            paths.append(content_files._rel(destination))

        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        changed = sorted(
            slug for slug in set(after) & set(before)
            if after[slug]["title"] != before[slug]["title"]
            or after[slug]["markdown_content"].strip() != before[slug]["markdown_content"].strip()
            or after[slug]["published"] != before[slug]["published"]
            or after[slug]["category_slug"] != before[slug]["category_slug"]
        )

        message = f"Sync from {ref}" if ref else "Sync"
        message += f"\n\n{len(added)} added, {len(changed)} changed, {len(removed)} removed."
        sha_before = git_content_repo.head_sha()
        git_content_repo.commit_and_push(paths, message, author)
        committed = git_content_repo.head_sha() != sha_before
        content_sync.full_sync()

    if committed and not first_sync:
        categories = {c["slug"]: c for c in categories_store.list_categories(project["id"], version=version)}
        for slug in added:
            if after[slug]["published"]:
                webhooks.notify("published", after[slug], project, categories.get(after[slug]["category_slug"]))
        for slug in changed:
            new, old = after[slug], before[slug]
            category = categories.get(new["category_slug"])
            if new["published"] and not old["published"]:
                webhooks.notify("published", new, project, category)
            elif old["published"] and not new["published"]:
                webhooks.notify("unpublished", old, project, category)
            elif new["published"] and (
                new["title"] != old["title"] or new["markdown_content"].strip() != old["markdown_content"].strip()
            ):
                webhooks.notify("updated", new, project, category)
        for slug in removed:
            if before[slug]["published"]:
                webhooks.notify("unpublished", before[slug], project, None)

    record = {
        "project": project_slug,
        "ref": ref,
        "committed": committed,
        "added": added,
        "changed": changed,
        "removed": removed,
        "unchanged": len(after) - len(added) - len(changed),
        "drafts": sorted(slug for slug, page in after.items() if not page["published"]),
        "assets": len(result.assets),
        "warnings": result.warnings,
        "skipped": result.skipped,
    }
    _record_run(project_slug, ref, author, record)
    return record


def _record_run(project_slug: str, ref: str, author: str, record: dict) -> None:
    p = _placeholder()
    with db.get_connection() as conn:
        conn.execute(
            f"INSERT INTO sync_runs (project_slug, ref, author, synced_at, added, changed, removed, committed) "
            f"VALUES ({p},{p},{p},{p},{p},{p},{p},{p})",
            (
                project_slug, ref, author, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                len(record["added"]), len(record["changed"]), len(record["removed"]), 1 if record["committed"] else 0,
            ),
        )
        # A history, not a log of everything forever.
        conn.execute(
            f"DELETE FROM sync_runs WHERE project_slug = {p} AND id NOT IN "
            f"(SELECT id FROM sync_runs WHERE project_slug = {p} ORDER BY id DESC LIMIT 50)",
            (project_slug, project_slug),
        )


def runs(project_slug: str, limit: int = 20) -> list[dict]:
    p = _placeholder()
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT ref, author, synced_at, added, changed, removed, committed FROM sync_runs "
            f"WHERE project_slug = {p} ORDER BY id DESC LIMIT {p}",
            (project_slug, limit),
        ).fetchall()
    return [
        {"ref": r[0], "author": r[1], "synced_at": r[2], "added": r[3], "changed": r[4], "removed": r[5],
         "committed": bool(r[6])}
        for r in rows
    ]


def source_file(project_slug: str, version: str, page_slug: str) -> str:
    """The page's file inside the synced docs folder, or ""."""
    path = content_files.project_content_dir(project_slug, version) / SOURCES_FILE
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ""
    value = (data.get("pages") or {}).get(page_slug)
    return value if isinstance(value, str) else ""


def edit_url(source: dict | None, file: str) -> str:
    """Where to change this file in the repository's web interface, or ""
    when the project names no repository. GitHub, GitLab and
    Forgejo/Gitea (Codeberg included) each spell the editor differently."""
    if not source or not source.get("repo") or not file:
        return ""
    repo = source["repo"].rstrip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    host = (urlsplit(repo).hostname or "").lower()
    path = "/".join(part for part in (source.get("path") or "", file) if part)
    branch = quote(source.get("branch") or "main", safe="")
    if host == "github.com" or host.endswith(".github.com"):
        return f"{repo}/edit/{branch}/{quote(path)}"
    if "gitlab" in host:
        return f"{repo}/-/edit/{branch}/{quote(path)}"
    return f"{repo}/_edit/{branch}/{quote(path)}"
