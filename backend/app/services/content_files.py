"""Reads and writes the actual Markdown/YAML files under the content repo's
`content/` directory -- pure file I/O, no git and no database. See the
project README's "Content repo structure" section for the on-disk
convention this implements (also documented inline below, since that's the
single source of truth a community contributor would read this file to
understand):

    content/<project-slug>/_project.yml
    content/<project-slug>/<category-slug>/_category.yml
    content/<project-slug>/<category-slug>/<page-slug>.md
    content/<project-slug>/<category-slug>/<page-slug>.<lang>.md

...or, once the project has frozen a documentation version, with one extra
directory level between the project and its categories:

    content/<project-slug>/_versions.yml
    content/<project-slug>/current/<category-slug>/<page-slug>.<lang>.md
    content/<project-slug>/v2.0/<category-slug>/<page-slug>.<lang>.md

(content/_site.yml and content/_site/ are the instance's own branding, owned
by site_branding.py -- underscore-prefixed names are skipped by every
enumeration here, see _RESERVED_PREFIX.)

`_project.yml` / `_category.yml` are plain YAML: name, icon, (color/
description for projects only), order. A page's `.md` file is YAML
frontmatter (title, order, published) followed by its Markdown body,
parsed/written with python-frontmatter so the format is the same one most
static-site generators already use -- a contributor who's touched Jekyll,
Hugo or MkDocs will recognize it immediately.

Multi-language content changes only two things here, both governed by
site_languages.py (which owns `languages:` in _site.yml):
- a page file may carry a language code before its `.md` extension, and the
  SLUG is the part in front of it, so `installation.de.md` and
  `installation.en.md` are one page in two languages, not two pages;
- `name`/`description` in a `_project.yml`/`_category.yml` may be a mapping
  of language code to string instead of a plain string. Every reader here
  returns BOTH the resolved default-language text and that raw mapping
  (`name` + `name_i18n`), so callers that serve one language index the
  mapping and callers that serve the file back to an editor still see what
  the file actually says.
An instance with no `languages:` configured hits neither: no suffix is
recognized, every field is a plain string, and every function below behaves
exactly as it did before any of this existed.

Versions are the same kind of addition, one level up: every function below
takes a `version`, and content_versions.content_dir() resolves it to the
project directory itself for a project with no `_versions.yml` -- so an
unversioned project reads and writes exactly the paths it always did, with
`version=""` flowing through untouched. The default is "" on purpose:
nothing has to pass a version for the unversioned case to keep working.

Every write function returns the list of paths it touched, *relative to the
content repo root* (not the `content/` subdirectory), exactly the form
git_content_repo.commit_and_push() expects for staging.
"""

import logging
import shutil
from pathlib import Path

import frontmatter
import yaml
from slugify import slugify

from app.services import content_versions, site_languages
from app.settings import settings

log = logging.getLogger("docuwaves")

# Defined in site_languages.py rather than here: that module has to build the
# path to content/_site.yml itself (it sits BELOW this one -- see its layering
# note), and one spelling of the directory name is better than two.
_CONTENT_DIRNAME = site_languages.CONTENT_DIRNAME

# A leading underscore marks a directory as DocuWaves' own, not a
# project/category: content/_site/ holds the instance's branding images (see
# site_branding.py). Enumerating skips those names, so `_site` can never turn
# into a phantom project on the homepage -- not even if someone drops a
# _project.yml into it -- and the namespace stays free for whatever the next
# instance-level folder turns out to be.
_RESERVED_PREFIX = "_"


def content_root() -> Path:
    return Path(settings.content_repo_path) / _CONTENT_DIRNAME


def project_content_dir(project_slug: str, version: str = "") -> Path:
    """Where this project's categories and assets/ live for `version` -- the
    project directory itself while the project is unversioned. Every path
    below is built from this one function, so the optional version level is
    resolved in exactly one place (content_versions.content_dir())."""
    return content_versions.content_dir(project_slug, version)


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


def _localized_field(data: dict, key: str, fallback: str = "") -> tuple[str, dict[str, str]]:
    """A `name:`/`description:` that may be a plain string or a per-language
    mapping, as (default-language text, mapping). See site_languages."""
    text, mapping = site_languages.split_localized(data.get(key))
    return (text or fallback), mapping


def read_project(slug: str) -> dict | None:
    path = content_root() / slug / "_project.yml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    name, name_i18n = _localized_field(data, "name", slug)
    description, description_i18n = _localized_field(data, "description")
    return {
        "name": name,
        "name_i18n": name_i18n,
        "icon": data.get("icon", ""),
        "color": data.get("color", ""),
        "description": description,
        "description_i18n": description_i18n,
        "order": int(data.get("order", 0)),
    }


def write_project(
    slug: str,
    name: str,
    icon: str,
    color: str,
    description: str,
    order: int,
    name_i18n: dict[str, str] | None = None,
    description_i18n: dict[str, str] | None = None,
) -> list[str]:
    """The two i18n mappings default to None so every existing caller (and
    every single-language install) writes exactly the plain `name: My
    Project` string it always wrote -- a mapping only appears in the file
    once someone actually translates the field."""
    path = content_root() / slug / "_project.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    default_lang = site_languages.default_language()
    data = {
        "name": site_languages.to_yaml_value(name, name_i18n or {}, default_lang),
        "icon": icon,
        "color": color,
        "description": site_languages.to_yaml_value(description, description_i18n or {}, default_lang),
        "order": order,
    }
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


def list_category_slugs(project_slug: str, version: str = "") -> list[str]:
    root = project_content_dir(project_slug, version)
    if not root.exists():
        return []
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and not is_reserved(p.name) and (p / "_category.yml").exists()
    )


def read_category(project_slug: str, slug: str, version: str = "") -> dict | None:
    path = project_content_dir(project_slug, version) / slug / "_category.yml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    name, name_i18n = _localized_field(data, "name", slug)
    return {"name": name, "name_i18n": name_i18n, "icon": data.get("icon", ""), "order": int(data.get("order", 0))}


def write_category(
    project_slug: str,
    slug: str,
    name: str,
    icon: str,
    order: int,
    name_i18n: dict[str, str] | None = None,
    version: str = "",
) -> list[str]:
    path = project_content_dir(project_slug, version) / slug / "_category.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "name": site_languages.to_yaml_value(name, name_i18n or {}, site_languages.default_language()),
        "icon": icon,
        "order": order,
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return [_rel(path)]


def delete_category(project_slug: str, slug: str, version: str = "") -> list[str]:
    path = project_content_dir(project_slug, version) / slug
    if not path.exists():
        return []
    touched = [_rel(p) for p in path.rglob("*") if p.is_file()]
    shutil.rmtree(path)
    return touched


def rename_category(project_slug: str, old_slug: str, new_slug: str, version: str = "") -> list[str]:
    directory = project_content_dir(project_slug, version)
    old_path = directory / old_slug
    new_path = directory / new_slug
    if not old_path.exists() or new_path.exists():
        return []
    old_files = [_rel(p) for p in old_path.rglob("*") if p.is_file()]
    old_path.rename(new_path)
    new_files = [_rel(p) for p in new_path.rglob("*") if p.is_file()]
    return old_files + new_files


# ---- Pages ----


def list_page_variants(project_slug: str, category_slug: str, version: str = "") -> list[tuple[str, str]]:
    """Every page file in the category as (slug, language) -- one entry per
    file, so `installation.de.md` and `installation.en.md` are two entries
    sharing one slug. `language` is the file's EFFECTIVE language: the
    suffix when it has one, the instance's default otherwise (and "" on an
    instance with no `languages:` configured, which is what keeps such a
    repo indexing to exactly one row per page as it always did).

    A repo holding BOTH `installation.md` and `installation.<default>.md`
    describes the same page twice; that's one entry here (and one row in
    the index, whose uniqueness is (project, slug, language)), served from
    the explicitly suffixed file -- see page_path(), which prefers it as the
    more specific statement of what it is. The duplicate is logged so it
    doesn't stay invisible."""
    root = project_content_dir(project_slug, version) / category_slug
    if not root.exists():
        return []
    default_lang = site_languages.default_language()
    variants: dict[tuple[str, str], None] = {}
    for path in sorted(root.glob("*.md")):
        if not path.is_file():
            continue
        slug, code = site_languages.parse_page_filename(path.stem)
        key = (slug, code or default_lang)
        if key in variants:
            log.warning(
                "%s/%s: %s and its unsuffixed form both describe page '%s' in '%s' -- serving the suffixed file.",
                project_slug, category_slug, path.name, slug, key[1],
            )
        variants[key] = None
    return list(variants)


def _page_paths(
    project_slug: str, category_slug: str, slug: str, language: str, version: str = ""
) -> tuple[Path, Path | None]:
    """(the file this language would be named, the unsuffixed `<slug>.md` if
    that file is ALSO this language's).

    The second one is only ever the DEFAULT language's: an unsuffixed file
    is by definition written in the default language, which is what lets a
    repo that predates `languages:` keep every file exactly where it is. For
    any other language it is somebody else's file and must be left alone --
    reading it would serve German text as English, writing it would
    overwrite the very page the translation was made from."""
    directory = project_content_dir(project_slug, version) / category_slug
    suffixed = directory / site_languages.page_filename(slug, language)
    plain = directory / f"{slug}.md"
    return suffixed, (plain if language == site_languages.default_language() else None)


def page_path(project_slug: str, category_slug: str, slug: str, language: str, version: str = "") -> Path:
    """Where a page in `language` lives, for reading."""
    suffixed, plain = _page_paths(project_slug, category_slug, slug, language, version)
    if suffixed.exists() or plain is None:
        return suffixed
    return plain


def _page_path_for_write(project_slug: str, category_slug: str, slug: str, language: str, version: str = "") -> Path:
    """Where to WRITE a page in `language`. An existing file is rewritten
    where it already is (so saving a page whose default-language version
    the repo spells `installation.md` doesn't leave that file behind and
    start a second `installation.de.md` beside it); anything new gets the
    explicit `<slug>.<lang>.md` name on a multilingual instance."""
    suffixed, plain = _page_paths(project_slug, category_slug, slug, language, version)
    if not suffixed.exists() and plain is not None and plain.exists():
        return plain
    return suffixed


def read_page(project_slug: str, category_slug: str, slug: str, language: str = "", version: str = "") -> dict | None:
    path = page_path(project_slug, category_slug, slug, language, version)
    if not path.exists():
        return None
    post = frontmatter.loads(path.read_text(encoding="utf-8"))
    return {
        "title": post.metadata.get("title", slug),
        "order": int(post.metadata.get("order", 0)),
        "published": bool(post.metadata.get("published", False)),
        "markdown_content": post.content,
        "language": language,
    }


def write_page(
    project_slug: str,
    category_slug: str,
    slug: str,
    title: str,
    markdown_content: str,
    order: int,
    published: bool,
    language: str = "",
    version: str = "",
) -> list[str]:
    path = _page_path_for_write(project_slug, category_slug, slug, language, version)
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(markdown_content, title=title, order=order, published=published)
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    return [_rel(path)]


def page_variant_paths(project_slug: str, category_slug: str, slug: str, version: str = "") -> list[Path]:
    """Every file that is this page, in any language -- `<slug>.md` plus
    every `<slug>.<lang>.md`. The unit of a rename/move/delete is the PAGE,
    not one translation of it: the slug is shared by definition (that's what
    keeps a reader on the same page when they switch language), so a slug
    that changes has to change for all of them at once or the translations
    silently come apart."""
    directory = project_content_dir(project_slug, version) / category_slug
    if not directory.is_dir():
        return []
    return [
        path
        for path in sorted(directory.glob("*.md"))
        if path.is_file() and site_languages.parse_page_filename(path.stem)[0] == slug
    ]


def delete_page(project_slug: str, category_slug: str, slug: str, version: str = "") -> list[str]:
    paths = page_variant_paths(project_slug, category_slug, slug, version)
    touched = [_rel(p) for p in paths]
    for path in paths:
        path.unlink()
    return touched


def relocate_page(
    project_slug: str,
    old_category_slug: str,
    old_slug: str,
    new_category_slug: str,
    new_slug: str,
    version: str = "",
) -> list[str]:
    """Handles both cases an admin edit can trigger at once -- a title edit
    that changes the slug, and/or picking a different category for the page
    -- in one filesystem move (always within the same project: the admin
    editor's category dropdown only ever offers the currently selected
    project's own categories). No-op (empty list) if neither actually
    changed, so callers can call this unconditionally rather than checking
    themselves.

    Every language variant of the page moves together, see
    page_variant_paths()."""
    if old_category_slug == new_category_slug and old_slug == new_slug:
        return []
    old_paths = page_variant_paths(project_slug, old_category_slug, old_slug, version)
    if not old_paths:
        return []
    new_directory = project_content_dir(project_slug, version) / new_category_slug
    moves: list[tuple[Path, Path]] = []
    for old_path in old_paths:
        _, code = site_languages.parse_page_filename(old_path.stem)
        # Keeps each variant's own naming: a `<slug>.md` stays unsuffixed,
        # a `<slug>.de.md` stays `.de`.
        name = f"{new_slug}.{code}.md" if code else f"{new_slug}.md"
        new_path = new_directory / name
        if new_path.exists():
            return []  # something is already there -- refuse the whole move rather than half of it
        moves.append((old_path, new_path))

    new_directory.mkdir(parents=True, exist_ok=True)
    touched: list[str] = []
    for old_path, new_path in moves:
        touched.append(_rel(old_path))
        old_path.rename(new_path)
        touched.append(_rel(new_path))
    return touched
