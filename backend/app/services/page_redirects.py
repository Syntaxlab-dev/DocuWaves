"""Old page addresses that still lead somewhere.

Renaming a page changes its slug, and the slug IS the page's address
(`/p/<project>/pages/<slug>`). Every link to the old address -- in a chat, in
an email, in another site's docs, in a search engine's index -- would 404
from that moment on. So a rename leaves a note behind, and the old address
answers with a permanent redirect to the new one.

The notes live in the content repo, one file per project:

    content/<project-slug>/_redirects.yml

    # Old page addresses and where they lead now.
    pages:
      old-slug: new-slug
      install: installation

In the repo rather than the database for the same reason as everything else
there: it is part of the documentation, it is versioned, it survives a
reindex, and a docs-as-code project can add an entry by hand -- for a page
that was renamed in an editor, or one that was merged into another.

THE RULES a rename applies, so the file never needs tidying by hand:

  * `old -> new` is added (or updated).
  * Every entry that pointed at `old` now points at `new` directly, so a
    page renamed three times redirects in one hop, not three.
  * An entry whose OLD side is `new` is removed: the slug is a real page
    again, and a real page always wins over a redirect.

A redirect is only followed when no page has that slug, so an entry can
never hide a page. Versions share the map: a rename happens in the version
being edited, and a frozen version that still has the old slug simply finds
its own page first.
"""

import logging
from pathlib import Path

import yaml

from app.services import content_versions
from app.settings import settings

log = logging.getLogger("docuwaves")

_FILENAME = "_redirects.yml"
_HEADER = "# Old page addresses and where they lead now (services/page_redirects.py).\n"
# A loop someone wrote by hand (a -> b, b -> a) must end somewhere.
_MAX_HOPS = 5


def _path(project_slug: str):
    return content_versions.project_dir(project_slug) / _FILENAME


def read(project_slug: str) -> dict[str, str]:
    path = _path(project_slug)
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        log.warning("Could not read %s; no page redirects for this project", path)
        return {}
    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, dict):
        return {}
    return {str(old).strip(): str(new).strip() for old, new in pages.items() if old and new}


def _write(project_slug: str, pages: dict[str, str]) -> str:
    path = _path(project_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump({"pages": dict(sorted(pages.items()))}, allow_unicode=True, sort_keys=False)
    path.write_text(_HEADER + body, encoding="utf-8")
    return str(path.relative_to(Path(settings.content_repo_path)))


def record_rename(project_slug: str, old_slug: str, new_slug: str) -> list[str]:
    """Called by a page rename. Returns the repo path it wrote, for the
    commit that renames the page -- one commit, so the redirect and the
    rename can never be found apart in the history."""
    if not old_slug or old_slug == new_slug:
        return []
    pages = read(project_slug)
    pages.pop(new_slug, None)
    pages = {old: (new_slug if target == old_slug else target) for old, target in pages.items()}
    pages[old_slug] = new_slug
    return [_write(project_slug, pages)]


def resolve(project_slug: str, slug: str) -> str | None:
    """Where an old slug leads now, following chains written by hand, or
    None. Whether the target exists is the caller's question."""
    pages = read(project_slug)
    seen = {slug}
    target = pages.get(slug)
    hops = 0
    while target and target in pages and hops < _MAX_HOPS and target not in seen:
        seen.add(target)
        target = pages[target]
        hops += 1
    return target if target and target != slug else None
