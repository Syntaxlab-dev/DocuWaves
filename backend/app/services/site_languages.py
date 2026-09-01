"""The instance's CONTENT languages -- which languages the documentation
itself is written in. Configured in one place, `languages:` in
content/_site.yml:

    languages: [de, en]     # ordered; the FIRST one is the default

This is deliberately not the same thing as the admin/reader UI's interface
language (frontend/src/lib/i18n.tsx, which only ever translates button
labels and lives entirely in the frontend bundle). A page's language is a
property of the CONTENT in the repo, so it belongs in the content repo,
exactly like branding does -- see site_branding.py for the same reasoning.

Two on-disk conventions follow from the list, and both are implemented here
so nothing else has to re-derive them:

- A page file carries its language in its name: `<slug>.<lang>.md`, with a
  plain `<slug>.md` meaning the DEFAULT language. The slug is the same in
  both forms, so the same page in two languages shares one slug (and one
  URL, bar the language prefix).
- A human-readable field in `_site.yml`/`_project.yml`/`_category.yml`
  (`name`, `description`, `tagline`, `footer_text`) is EITHER a plain
  string, applying to every language as it always has, OR a mapping of
  language code to string. A language missing from the mapping falls back
  to the default language's value.

Absent `languages:` the whole feature is off: default_language() is "",
no filename suffix is ever recognized as a language (so a hand-written
`release.v2.md` keeps the slug `release.v2`, and an old single-language
repo is read byte-for-byte as it was before this module existed), and the
frontend renders no language prefix and no switcher. That "off" state is
the one an existing install starts in, and nothing about it changes until
someone adds the key themselves.

Layering note: content_files.py imports THIS module (it needs the language
list to know whether a filename's `.de` is a language code or part of the
slug), so this module must not import content_files back -- which is why
CONTENT_DIRNAME and the _site.yml loader live down here rather than up in
content_files.py / site_branding.py, both of which import them from here.
"""

import json
import logging
import re
from pathlib import Path

import yaml

from app.settings import settings

log = logging.getLogger("docuwaves")

CONTENT_DIRNAME = "content"
SITE_FILENAME = "_site.yml"

# ISO 639-1: exactly two letters, lowercase. Narrow on purpose -- the code
# ends up in a URL path segment and in a filename, and a two-letter set is
# also what makes `<slug>.<lang>.md` unambiguous to read at a glance.
_LANG_RE = re.compile(r"^[a-z]{2}$")

# More than this many languages in one instance is a configuration mistake,
# not a use case -- and every extra language multiplies the admin editor's
# tab strip and the switcher in the header.
_MAX_LANGUAGES = 12


def site_file() -> Path:
    return Path(settings.content_repo_path) / CONTENT_DIRNAME / SITE_FILENAME


# Parsing a tiny YAML file is cheap, but this is now on the path of every
# single file a full reindex touches (read_page() has to know the language
# list to split a filename) as well as every branding request. Keyed by the
# file's identity AND its mtime+size, so a `git pull` that rewrites the file
# -- which always moves mtime -- invalidates it on the next read rather than
# serving yesterday's configuration.
_cache: tuple[tuple, dict] | None = None


def load_site_document() -> dict:
    """The raw mapping from `_site.yml`, or {} for every failure mode there
    is. Logged, not raised: a typo in this one file must not take the public
    site down with it (see site_branding.py's module docstring -- this is
    that module's own loader, moved down here so the language list can use
    it too)."""
    global _cache
    path = site_file()
    try:
        stat = path.stat()
    except OSError:
        _cache = None
        return {}
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if _cache is not None and _cache[0] == key:
        return _cache[1]

    data = _parse(path)
    _cache = (key, data)
    return data


def _parse(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        log.warning("Ignoring unreadable %s: %s", SITE_FILENAME, exc)
        return {}
    if data is None:
        return {}  # an empty file parses to None, which is not an error
    if not isinstance(data, dict):
        log.warning("Ignoring %s: expected a YAML mapping, got %s.", SITE_FILENAME, type(data).__name__)
        return {}
    return data


def languages() -> list[str]:
    """The configured content languages, in order, first one being the
    default. Empty list = this instance never configured any, which is the
    single-language behaviour everything defaults to.

    A malformed entry is dropped rather than failing the read, same
    degrade-don't-break contract the rest of `_site.yml` follows."""
    raw = load_site_document().get("languages")
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw[:_MAX_LANGUAGES]:
        if not isinstance(item, str):
            continue
        code = item.strip().lower()
        if _LANG_RE.match(code) and code not in result:
            result.append(code)
    return result


def default_language() -> str:
    """The language an unsuffixed `<slug>.md` is written in, and the one an
    unprefixed URL redirects to. "" when no `languages:` is configured --
    which is also what gets stored in the index's `language` column for such
    an install, so its rows keep exactly one row per page, as before."""
    configured = languages()
    return configured[0] if configured else ""


def is_multilingual() -> bool:
    """Whether the reader-facing multi-language machinery (URL prefix,
    switcher, fallback notice, per-language admin fields) turns on at all.
    A list with a single entry is still a single-language site: it only
    names which language that is, so `<slug>.<lang>.md` is recognized."""
    return len(languages()) > 1


# ---- Filenames ----


def parse_page_filename(stem: str) -> tuple[str, str]:
    """`installation.de` -> ("installation", "de"), `installation` ->
    ("installation", ""). The suffix only counts when it is one of THIS
    instance's configured languages: on a single-language install nothing is
    configured, so a file someone named `notes.io.md` keeps the slug
    `notes.io` instead of silently becoming an Ido translation of `notes`."""
    configured = languages()
    if not configured:
        return stem, ""
    slug, dot, code = stem.rpartition(".")
    if dot and code in configured:
        return slug, code
    return stem, ""


def page_filename(slug: str, language: str) -> str:
    """The name a page in `language` is written under. The suffix is always
    spelled out on a multilingual instance -- `installation.de.md` next to
    `installation.en.md` is what makes a missing translation visible in a
    directory listing, which is the whole point of putting the language in
    the filename rather than in the frontmatter. Callers that are UPDATING
    an existing page go through content_files._page_path_for_write() instead, so a repo that
    already spells the default language `installation.md` keeps that file
    rather than growing a second one beside it."""
    if language and is_multilingual():
        return f"{slug}.{language}.md"
    return f"{slug}.md"


# ---- Localized fields ----


def split_localized(value, default_lang: str | None = None) -> tuple[str, dict[str, str]]:
    """A `name:`/`description:`/`tagline:` field as (default-language text,
    per-language mapping). A plain string yields (value, {}) -- an install
    that never heard of `languages:` reads exactly as it always did. A
    mapping yields its default language's entry (or, if that one is missing,
    whichever entry comes first, so a mapping that forgot the default
    language still shows something rather than nothing) plus the mapping
    itself for the caller to index by whatever language it is serving.

    Anything else (a number, a list, a mapping of mappings) is not a
    human-readable name and degrades to ("", {})."""
    if isinstance(value, str):
        return value, {}
    if isinstance(value, dict):
        mapping = {
            str(k).strip().lower(): v.strip()
            for k, v in value.items()
            if isinstance(v, str) and _LANG_RE.match(str(k).strip().lower()) and v.strip()
        }
        if not mapping:
            return "", {}
        fallback_lang = default_lang if default_lang is not None else default_language()
        text = mapping.get(fallback_lang) or next(iter(mapping.values()))
        return text, mapping
    return "", {}


def pick(text: str, mapping: dict[str, str], language: str) -> str:
    """The value to show a reader of `language`: their own if the mapping
    has one, otherwise the default-language text `split_localized` already
    resolved. Never empty when `text` isn't -- a name is structural, so
    falling back is always better than a blank tile."""
    if language and mapping:
        return mapping.get(language) or text
    return text


def dump_i18n(mapping: dict[str, str]) -> str:
    """A per-language mapping in the form the database index stores it (see
    db.py's schema comment on name_i18n): JSON, or '' for the plain-string
    form a single-language repo uses."""
    return json.dumps(mapping, ensure_ascii=False, sort_keys=True) if mapping else ""


def parse_i18n(text: str | None) -> dict[str, str]:
    """Inverse of dump_i18n(). Tolerant on the way back in: this column is
    written by content_sync from a file anyone can edit, and a row that
    somehow holds something else must degrade to "no translations" rather
    than break a listing."""
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, str)}


def to_yaml_value(text: str, mapping: dict[str, str], default_lang: str = "") -> str | dict[str, str]:
    """Inverse of split_localized(), for the admin writers: what to put in
    the YAML file for a field the form edited.

    A mapping that only really says one thing is written back as the plain
    string it would have been anyway -- so enabling `languages:` and then
    saving a project without translating it doesn't rewrite every
    `name: My Project` into a one-key mapping nobody asked for."""
    cleaned = {
        code: value.strip()
        for code, value in (mapping or {}).items()
        if isinstance(value, str) and value.strip() and _LANG_RE.match(code)
    }
    if not cleaned:
        return text
    # A mapping that says the same thing in every language, or only says
    # anything at all in the default one, IS a plain string -- writing it as
    # a mapping would put three lines in the file where one carries exactly
    # the same meaning, on every project whose name doesn't get translated.
    if set(cleaned) <= {default_lang} or len(set(cleaned.values())) == 1:
        return cleaned.get(default_lang) or next(iter(cleaned.values()))
    return cleaned
