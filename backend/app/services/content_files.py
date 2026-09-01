"""Reads and writes the actual Markdown/YAML files under the content repo's
`content/` directory -- pure file I/O, no git and no database. See the
project README's "Content repo structure" section for the on-disk
convention this implements (also documented inline below, since that's the
single source of truth a community contributor would read this file to
understand):

    content/<project-slug>/_project.yml
    content/<project-slug>/<category-slug>/_category.yml
    content/<project-slug>/<category-slug>/<page-slug>.md

(content/_site.yml and content/_site/ are the instance's own branding, owned
by site_branding.py -- underscore-prefixed names are skipped by every
enumeration here, see _RESERVED_PREFIX.)

`_project.yml` / `_category.yml` are plain YAML: name, icon, (color/
description for projects only), order. A page's `.md` file is YAML
frontmatter (title, order, published) followed by its Markdown body,
parsed/written with python-frontmatter so the format is the same one most
static-site generators already use -- a contributor who's touched Jekyll,
Hugo or MkDocs will recognize it immediately.

Every write function returns the list of paths it touched, *relative to the
content repo root* (not the `content/` subdirectory), exactly the form
git_content_repo.commit_and_push() expects for staging.
"""

import shutil
from pathlib import Path

import frontmatter
import yaml
from slugify import slugify

from app.settings import settings

_CONTENT_DIRNAME = "content"

# A leading underscore marks a directory as DocuWaves' own, not a
# project/category: content/_site/ holds the instance's branding images (see
# site_branding.py). Enumerating skips those names, so `_site` can never turn
# into a phantom project on the homepage -- not even if someone drops a
# _project.yml into it -- and the namespace stays free for whatever the next
# instance-level folder turns out to be.
_RESERVED_PREFIX = "_"


def content_root() -> Path:
    return Path(settings.content_repo_path) / _CONTENT_DIRNAME


def is_reserved(name: str) -> bool:
    return name.startswith(_RESERVED_PREFIX)


def _rel(path: Path) -> str:
    return str(path.relative_to(Path(settings.content_repo_path)))


def make_slug(name: str) -> str:
    return slugify(name) or "item"


# ---- Projects ----


def list_project_slugs() -> list[str]:
    root = content_root()
    if not root.exists():
        return []
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and not is_reserved(p.name) and (p / "_project.yml").exists()
    )


def read_project(slug: str) -> dict | None:
    path = content_root() / slug / "_project.yml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "name": data.get("name", slug),
        "icon": data.get("icon", ""),
        "color": data.get("color", ""),
        "description": data.get("description", ""),
        "order": int(data.get("order", 0)),
    }


def write_project(slug: str, name: str, icon: str, color: str, description: str, order: int) -> list[str]:
    path = content_root() / slug / "_project.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"name": name, "icon": icon, "color": color, "description": description, "order": order}
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return [_rel(path)]


def delete_project(slug: str) -> list[str]:
    """Removes the whole project directory (all its categories/pages with
    it) and returns every file path that existed, for git staging as
    deletions -- an empty return means the project directory didn't exist,
    which callers treat as a no-op, not an error."""
    path = content_root() / slug
    if not path.exists():
        return []
    touched = [_rel(p) for p in path.rglob("*") if p.is_file()]
    shutil.rmtree(path)
    return touched


def rename_project(old_slug: str, new_slug: str) -> list[str]:
    """Only called when the slug actually changes (a name edit that keeps
    the same slug just rewrites _project.yml in place via write_project).
    Returns both the old (now-deleted) and new paths for git staging."""
    old_path = content_root() / old_slug
    new_path = content_root() / new_slug
    if not old_path.exists() or new_path.exists():
        return []
    old_files = [_rel(p) for p in old_path.rglob("*") if p.is_file()]
    old_path.rename(new_path)
    new_files = [_rel(p) for p in new_path.rglob("*") if p.is_file()]
    return old_files + new_files


# ---- Categories ----


def list_category_slugs(project_slug: str) -> list[str]:
    root = content_root() / project_slug
    if not root.exists():
        return []
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and not is_reserved(p.name) and (p / "_category.yml").exists()
    )


def read_category(project_slug: str, slug: str) -> dict | None:
    path = content_root() / project_slug / slug / "_category.yml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {"name": data.get("name", slug), "icon": data.get("icon", ""), "order": int(data.get("order", 0))}


def write_category(project_slug: str, slug: str, name: str, icon: str, order: int) -> list[str]:
    path = content_root() / project_slug / slug / "_category.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"name": name, "icon": icon, "order": order}
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return [_rel(path)]


def delete_category(project_slug: str, slug: str) -> list[str]:
    path = content_root() / project_slug / slug
    if not path.exists():
        return []
    touched = [_rel(p) for p in path.rglob("*") if p.is_file()]
    shutil.rmtree(path)
    return touched


def rename_category(project_slug: str, old_slug: str, new_slug: str) -> list[str]:
    old_path = content_root() / project_slug / old_slug
    new_path = content_root() / project_slug / new_slug
    if not old_path.exists() or new_path.exists():
        return []
    old_files = [_rel(p) for p in old_path.rglob("*") if p.is_file()]
    old_path.rename(new_path)
    new_files = [_rel(p) for p in new_path.rglob("*") if p.is_file()]
    return old_files + new_files


# ---- Pages ----


def list_page_slugs(project_slug: str, category_slug: str) -> list[str]:
    root = content_root() / project_slug / category_slug
    if not root.exists():
        return []
    return sorted(p.stem for p in root.glob("*.md") if p.is_file())


def read_page(project_slug: str, category_slug: str, slug: str) -> dict | None:
    path = content_root() / project_slug / category_slug / f"{slug}.md"
    if not path.exists():
        return None
    post = frontmatter.loads(path.read_text(encoding="utf-8"))
    return {
        "title": post.metadata.get("title", slug),
        "order": int(post.metadata.get("order", 0)),
        "published": bool(post.metadata.get("published", False)),
        "markdown_content": post.content,
    }


def write_page(
    project_slug: str, category_slug: str, slug: str, title: str, markdown_content: str, order: int, published: bool
) -> list[str]:
    path = content_root() / project_slug / category_slug / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(markdown_content, title=title, order=order, published=published)
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    return [_rel(path)]


def delete_page(project_slug: str, category_slug: str, slug: str) -> list[str]:
    path = content_root() / project_slug / category_slug / f"{slug}.md"
    if not path.exists():
        return []
    rel = _rel(path)
    path.unlink()
    return [rel]


def relocate_page(project_slug: str, old_category_slug: str, old_slug: str, new_category_slug: str, new_slug: str) -> list[str]:
    """Handles both cases an admin edit can trigger at once -- a title edit
    that changes the slug, and/or picking a different category for the page
    -- in one filesystem move (always within the same project: the admin
    editor's category dropdown only ever offers the currently selected
    project's own categories). No-op (empty list) if neither actually
    changed, so callers can call this unconditionally rather than checking
    themselves."""
    if old_category_slug == new_category_slug and old_slug == new_slug:
        return []
    old_path = content_root() / project_slug / old_category_slug / f"{old_slug}.md"
    new_path = content_root() / project_slug / new_category_slug / f"{new_slug}.md"
    if not old_path.exists() or new_path.exists():
        return []
    new_path.parent.mkdir(parents=True, exist_ok=True)
    old_rel = _rel(old_path)
    old_path.rename(new_path)
    return [old_rel, _rel(new_path)]
