"""Documentation versions -- a project's docs as they stood at a release,
kept as a FROZEN SNAPSHOT DIRECTORY next to the working one:

    content/<project-slug>/
      _project.yml
      _versions.yml       <- which versions exist, which one readers get
      current/            <- the working version; the editor writes here
        assets/
        <category-slug>/
          _category.yml
          <page-slug>.<lang>.md
      v2.0/               <- frozen at release: a copy of current/ at that moment
        assets/
        <category-slug>/
          ...

Snapshots rather than git branches, deliberately. A version of the docs has
to keep saying what it said on release day while the current one is edited
every week; a branch says the opposite -- it is a line of development you
merge, rebase and eventually delete, and reading an old one means checking
it out, which one working clone can only do for one version at a time. This
tool serves every version at once, from one checkout, and a community
contributor's pull request has to be able to touch v2.0 and current in the
same diff. Duplication is the point: `v2.0/` is bytes nothing will ever
rewrite. The cost is disk (text files, next to nothing) and the benefit is
that "what did 2.0 say?" is answered by looking at a directory.

THE VERSION LEVEL IS OPTIONAL, and that is the most important rule here. A
project with no `_versions.yml` has its categories and `assets/` directly
under the project directory, exactly as before any of this existed:

    content/<project-slug>/<category-slug>/<page-slug>.md

...and behaves exactly as before too -- no `current/`, no version in its
URLs, no switcher, one row per page in the index (with version ''). Every
function below answers for that shape first; the version level only appears
once someone freezes their first version, at which point DocuWaves performs
the move itself (see freeze()), in ONE commit, so nobody has to reshuffle a
repo by hand.

`assets/` moves under the version with the content, because a screenshot
belongs to the version it documents -- 2.0's install page must keep showing
2.0's install screen. The page sources do NOT change during that move: a
page still sits exactly one directory below `assets/` afterwards
(`<project>/<version>/<category>/<page>.md` vs `<project>/<version>/assets/`),
so `../assets/x.png` still resolves, in DocuWaves and in GitHub's own file
preview alike.

Layering note: this module sits BELOW content_files.py (which imports it to
build every path) and above site_languages.py -- so, like site_languages, it
derives the content root itself from settings rather than importing it back
from content_files.
"""

import logging
import re
import shutil
from datetime import date
from pathlib import Path

import yaml

from app.services import site_languages
from app.settings import settings

log = logging.getLogger("docuwaves")

VERSIONS_FILENAME = "_versions.yml"

# The id of the working version -- the one the editor writes to and the one
# a project's content is moved into on its first freeze. It is not listed in
# `versions:` (that list is the frozen ones); it always exists once a project
# is versioned at all.
CURRENT_ID = "current"

DEFAULT_CURRENT_LABEL = "Current"

# A version id is a DIRECTORY NAME and a URL path segment, so it is checked
# rather than slugified: slugify("v2.0") is "v2-0", and the dot in a version
# number is the whole point of the name. Must start alphanumeric (which also
# rules out ".", "..", and the underscore-prefixed names reserved for
# DocuWaves' own directories).
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# Names a version can't have: `current` is the working version itself, and
# the rest would collide with a fixed segment of a reading URL
# (/p/<project>/<version>/c/<category>, .../pages/<page>) or with the assets
# folder that sits inside every version directory.
_RESERVED_IDS = {CURRENT_ID, "assets", "c", "pages"}

_MAX_ID_LENGTH = 40
_MAX_LABEL_LENGTH = 60

# More than this many frozen versions of one project is an archive, not a
# switcher -- and the switcher is a row of links in a header.
_MAX_VERSIONS = 50


class FrozenVersionError(RuntimeError):
    """Raised by the write paths when a frozen version is the target. Frozen
    means frozen: correcting an old page is a file edit in the content repo,
    reviewable like any other contribution, not a silent rewrite of what a
    release said."""


def _content_root() -> Path:
    # Same expression content_files.content_root() evaluates; spelled out
    # here rather than imported because content_files imports THIS module
    # (see the layering note in the docstring), exactly as site_languages
    # spells out its own path to _site.yml.
    return Path(settings.content_repo_path) / site_languages.CONTENT_DIRNAME


def project_dir(project_slug: str) -> Path:
    return _content_root() / project_slug


def versions_file(project_slug: str) -> Path:
    return project_dir(project_slug) / VERSIONS_FILENAME


def _rel(path: Path) -> str:
    return str(path.relative_to(Path(settings.content_repo_path)))


# ---- Reading _versions.yml ----

# Keyed by the file's path AND its mtime+size, like site_languages' own
# cache: read_versions() is on the path of every public request and of every
# file a full reindex touches, and a `git pull` that rewrites the file always
# moves its mtime.
_cache: dict[str, tuple[tuple, dict]] = {}


def _load(project_slug: str) -> dict | None:
    """The raw mapping from a project's `_versions.yml`, or None when the
    project has no such file -- which is the unversioned shape, not an
    error. A file that exists but is broken (unparseable, not a mapping)
    degrades to an EMPTY mapping rather than to None: the directory layout
    on disk is already the versioned one at that point, so pretending the
    project is unversioned would look for categories one level too high and
    show an empty project. An empty mapping still resolves to
    current/ + no frozen versions, which is what is actually there."""
    path = versions_file(project_slug)
    key = str(path)
    try:
        stat = path.stat()
    except OSError:
        _cache.pop(key, None)
        return None
    identity = (stat.st_mtime_ns, stat.st_size)
    cached = _cache.get(key)
    if cached is not None and cached[0] == identity:
        return cached[1]

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        log.warning("Ignoring unreadable %s/%s: %s", project_slug, VERSIONS_FILENAME, exc)
        data = {}
    if data is None:
        data = {}  # an empty file parses to None, which is not an error
    if not isinstance(data, dict):
        log.warning("Ignoring %s/%s: expected a YAML mapping.", project_slug, VERSIONS_FILENAME)
        data = {}
    _cache[key] = (identity, data)
    return data


def is_versioned(project_slug: str) -> bool:
    """Whether this project has a version level at all. False is the
    original shape and stays the default forever -- nothing here ever
    creates `_versions.yml` on its own."""
    return _load(project_slug) is not None


def _released(value) -> str:
    """`released:` as a plain string. YAML parses an unquoted 2026-08-01
    into a date object and a quoted one into a string; both are the same
    fact, and the API answers with the ISO string either way."""
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip() if value else ""


def read_versions(project_slug: str) -> dict | None:
    """The project's versions, resolved: `current_label`, `default`, and the
    frozen `versions` list in file order (newest first). None for an
    unversioned project.

    Every field degrades on its own -- a missing `current_label` is
    "Current", a `default` naming a version that no longer exists falls back
    to `current`, an entry that isn't a mapping with a usable id is dropped.
    This file is hand-editable and arrives by pull request like every other
    file in the repo, so a typo in it must not take a project's docs down."""
    data = _load(project_slug)
    if data is None:
        return None

    versions: list[dict] = []
    seen: set[str] = set()
    raw = data.get("versions")
    for item in raw[:_MAX_VERSIONS] if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        version_id = str(item.get("id", "")).strip()
        # The same checks a freeze goes through -- a hand-written id that
        # isn't a usable directory name never becomes a URL here either.
        if not _ID_RE.match(version_id) or version_id in _RESERVED_IDS or version_id in seen:
            log.warning("%s/%s: ignoring version entry %r.", project_slug, VERSIONS_FILENAME, item.get("id"))
            continue
        seen.add(version_id)
        label = str(item.get("label", "")).strip()[:_MAX_LABEL_LENGTH] or version_id
        versions.append({"id": version_id, "label": label, "released": _released(item.get("released"))})

    current_label = data.get("current_label")
    if not isinstance(current_label, str) or not current_label.strip():
        current_label = DEFAULT_CURRENT_LABEL
    default = str(data.get("default", "") or "").strip()
    if default != CURRENT_ID and default not in seen:
        default = CURRENT_ID

    return {
        "current_label": current_label.strip()[:_MAX_LABEL_LENGTH],
        "default": default,
        "versions": versions,
    }


def version_ids(project_slug: str) -> list[str]:
    """Every version a reader can ask for, working version first. Empty for
    an unversioned project -- which is what makes "no version in the URL"
    fall out of the same code path rather than needing its own."""
    document = read_versions(project_slug)
    if document is None:
        return []
    return [CURRENT_ID, *(v["id"] for v in document["versions"])]


def default_version(project_slug: str) -> str:
    """The version an UNPREFIXED URL shows -- '' for an unversioned project.
    Readers land here, and every link shared before this project was
    versioned still points at it."""
    document = read_versions(project_slug)
    return document["default"] if document else ""


def writable_version(project_slug: str) -> str:
    """Where the editor writes: `current` once a project is versioned, ''
    (i.e. straight into the project directory) while it isn't."""
    return CURRENT_ID if is_versioned(project_slug) else ""


def is_frozen(project_slug: str, version: str) -> bool:
    """A frozen version is any version that isn't the working one. '' (the
    unversioned project's single implicit version) is never frozen."""
    if not version or version == CURRENT_ID:
        return False
    return version in version_ids(project_slug)


def ensure_writable(project_slug: str, version: str) -> None:
    """Guard for every write path. Raising here rather than at each caller
    means a frozen version cannot be edited through ANY route -- the admin
    UI hides the controls, but the API is what actually refuses."""
    if not is_frozen(project_slug, version):
        return
    document = read_versions(project_slug) or {}
    label = next((v["label"] for v in document.get("versions", []) if v["id"] == version), version)
    raise FrozenVersionError(
        f"Version {label} ({version}) is frozen and can't be edited here. A frozen version is a snapshot of "
        f"what the docs said at that release -- to correct a page in it, edit the file under "
        f"content/{project_slug}/{version}/ in the content repo."
    )


def content_dir(project_slug: str, version: str = "") -> Path:
    """Where this project's categories and `assets/` actually live for
    `version`. The whole optional-version rule lives in this one function:
    an unversioned project answers with the project directory itself, so
    every caller above stays identical for it."""
    root = project_dir(project_slug)
    if not is_versioned(project_slug):
        return root
    return root / (version or default_version(project_slug))


def index_versions(project_slug: str) -> list[str]:
    """Which versions a reindex has to walk: [''] for an unversioned project
    (one pass over the project directory, exactly as before), otherwise
    every version id. The '' entry is also what lands in the index's
    `version` column for such a project, keeping its rows one-per-page."""
    ids = version_ids(project_slug)
    return ids or [""]


# ---- Validating a new version ----


def normalize_id(raw: str) -> str:
    """A user-typed version id as a safe directory name. Not slugify():
    that eats the dot in `v2.0`, and a version id is a version NUMBER --
    `v2-0` is a different (and worse) name than the one the user typed.
    Lowercased, spaces and anything unexpected turned into `-`, then
    trimmed back to something that starts alphanumeric.

    Cosmetic only, by design. Everything this could change MEANINGFULLY --
    a leading `_` or `.`, a path separator -- is refused outright by
    rejection_reason() instead, because silently turning `../escape` into
    `escape` would create a directory the user never asked for and never
    saw named."""
    text = (raw or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text[:_MAX_ID_LENGTH]


def rejection_reason(project_slug: str, version_id: str, label: str, raw: str = "") -> str | None:
    """None = this freeze can go ahead. Every check spells out what is wrong
    with the id the user typed, since the only fix is to type a different
    one.

    `raw` is what the user actually typed, before normalize_id() tidied it.
    The two checks below run against it rather than against the normalized
    form on purpose: an id starting with `_` or `.`, or holding a path
    separator, is refused rather than repaired, so nobody types `../escape`
    and gets a directory called `escape`."""
    typed = (raw or "").strip()
    if typed.startswith("_") or typed.startswith("."):
        return (
            f"A version id can't start with '{typed[0]}'. Names starting with '_' are reserved for DocuWaves' "
            f"own files in the content repo, and one starting with '.' isn't a usable directory name."
        )
    if "/" in typed or "\\" in typed:
        return "A version id is a single directory name, so it can't contain '/' or '\\'."
    if not version_id:
        return "A version id is required (for example 'v2.0')."
    if not _ID_RE.match(version_id):
        return (
            f"'{version_id}' isn't usable as a directory name. Use letters, digits, dots, dashes or "
            f"underscores, starting with a letter or digit -- for example 'v2.0'."
        )
    if version_id in _RESERVED_IDS:
        return f"'{version_id}' is a reserved name. Pick another id -- for example 'v2.0'."
    if not label.strip():
        return "A label is required (what the switcher calls this version, for example '2.0')."

    document = read_versions(project_slug)
    if document is not None:
        if version_id in {v["id"] for v in document["versions"]}:
            return f"This project already has a version '{version_id}'."
        if len(document["versions"]) >= _MAX_VERSIONS:
            return f"This project already has {_MAX_VERSIONS} frozen versions, which is the limit."

    root = project_dir(project_slug)
    if not root.is_dir():
        return "That project has no content directory in the content repo."
    if (root / version_id).exists():
        return f"content/{project_slug}/{version_id}/ already exists in the content repo."
    if document is None and (root / CURRENT_ID).exists():
        return (
            f"content/{project_slug}/{CURRENT_ID}/ already exists but this project has no {VERSIONS_FILENAME}. "
            f"Sort that out in the content repo first -- freezing would move content into a directory that is "
            f"already holding something else."
        )
    if not _content_entries(project_slug):
        return "There is nothing to freeze yet -- this project has no content."
    return None


def _content_entries(project_slug: str) -> list[Path]:
    """What a freeze snapshots: everything in the version's content
    directory that isn't one of DocuWaves' own underscore-prefixed files
    (`_project.yml` and `_versions.yml` describe the PROJECT, not one
    version of it, and stay at the project level). Categories, `assets/`,
    and anything else a contributor put there travel together -- a rule
    stated once here is one nobody has to re-derive."""
    directory = content_dir(project_slug, writable_version(project_slug))
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if not p.name.startswith("_"))


def would_move(project_slug: str) -> list[str]:
    """The top-level names a FIRST freeze will move into `current/`, for the
    admin UI to show before anything happens. Empty once the project is
    versioned (nothing moves on any later freeze)."""
    if is_versioned(project_slug):
        return []
    return [f"{p.name}/" if p.is_dir() else p.name for p in _content_entries(project_slug)]


# ---- Writing ----


def _as_yaml_date(text: str):
    """`released` written back as a real date so YAML spells it 2026-08-01
    rather than quoting it -- the file is read by people too. A value that
    isn't an ISO date (hand-edited to "spring 2026", say) is kept verbatim
    as the string it is, rather than being dropped or crashing the write."""
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return text


def _write_document(project_slug: str, document: dict) -> list[str]:
    path = versions_file(project_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "current_label": document["current_label"],
        "default": document["default"],
        "versions": [
            {"id": v["id"], "label": v["label"], "released": _as_yaml_date(v["released"])}
            for v in document["versions"]
        ],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return [_rel(path)]


def _files_under(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return [p for p in path.rglob("*") if p.is_file()]


def _migrate_to_versioned(project_slug: str) -> list[str]:
    """The first freeze's move: everything that is content goes one level
    down into `current/`, and `_project.yml` stays where it is.

    Page SOURCES are deliberately untouched by this -- not rewritten, not
    even re-read. A page keeps sitting exactly one directory above
    `assets/` (it was <project>/<category>/x.md next to <project>/assets/,
    it becomes <project>/current/<category>/x.md next to
    <project>/current/assets/), so every `../assets/x.png` in the repo still
    points at the same image afterwards."""
    root = project_dir(project_slug)
    entries = _content_entries(project_slug)
    # Old paths are collected BEFORE anything moves (they have to be staged
    # as deletions), and the destination is created only after the listing,
    # so `current/` can't enumerate itself.
    touched = [_rel(p) for entry in entries for p in _files_under(entry)]

    current = root / CURRENT_ID
    current.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        entry.rename(current / entry.name)
    touched += [_rel(p) for p in _files_under(current)]
    return touched


def freeze(project_slug: str, version_id: str, label: str) -> list[str]:
    """Freezes the working version as `version_id`, and returns every path
    touched, for ONE commit (see git_content_repo.commit_and_push).

    On the very first freeze this also performs the migration above, in the
    same commit: a repo whose history shows content moving into `current/`
    and being copied to `v2.0/` as two commits would have a commit in the
    middle where the site is in neither shape."""
    touched: list[str] = []
    document = read_versions(project_slug)
    if document is None:
        touched += _migrate_to_versioned(project_slug)
        document = {"current_label": DEFAULT_CURRENT_LABEL, "default": CURRENT_ID, "versions": []}

    root = project_dir(project_slug)
    # copytree, not a rewrite: the frozen directory is a byte-identical copy
    # of what current/ holds right now. Nothing here parses a page, so
    # nothing here can reformat one.
    shutil.copytree(root / CURRENT_ID, root / version_id)
    touched += [_rel(p) for p in _files_under(root / version_id)]

    document["versions"] = [
        {"id": version_id, "label": label.strip()[:_MAX_LABEL_LENGTH], "released": date.today().isoformat()},
        *document["versions"],
    ]
    touched += _write_document(project_slug, document)
    return touched


def delete_version(project_slug: str, version_id: str) -> list[str]:
    """Removes a frozen version's directory and its `_versions.yml` entry --
    old docs do get retired. Empty list = there was nothing to delete, which
    callers treat as a no-op (same contract as content_files.delete_page).

    `current` is never deletable: it is not a frozen version, it is the
    project's content. Deleting the LAST frozen version leaves the project
    versioned with just `current/` -- which reads exactly like an
    unversioned project (no switcher, no prefix, the default is `current`)
    without moving a single file back up a level and breaking every link a
    second time."""
    document = read_versions(project_slug)
    if document is None or version_id == CURRENT_ID:
        return []
    if version_id not in {v["id"] for v in document["versions"]}:
        return []

    directory = project_dir(project_slug) / version_id
    touched = [_rel(p) for p in _files_under(directory)] if directory.is_dir() else []
    if directory.is_dir():
        shutil.rmtree(directory)

    document["versions"] = [v for v in document["versions"] if v["id"] != version_id]
    if document["default"] == version_id:
        document["default"] = CURRENT_ID
    touched += _write_document(project_slug, document)
    return touched
