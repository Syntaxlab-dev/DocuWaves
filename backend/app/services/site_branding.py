"""Per-instance branding -- the site's own name, tagline, logo, accent colour
and footer, read from the CONTENT REPO rather than from the database:

    content/_site.yml          <- the branding file (every field optional)
    content/_site/<image>      <- its logo / dark logo / favicon

It lives in the content repo on purpose. The database is documented
everywhere else in this codebase as a rebuildable INDEX over these files
(see content_sync.py) -- branding kept only in a DB row would vanish the
moment that index is rebuilt or the /data volume is lost, taking the site's
identity with it. In the repo it's versioned, reviewable in a pull request,
and restored by the same `git clone` that restores every page. It also means
each DocuWaves instance is branded by its OWN content repo: one deployment
for a company's projects and one for this tool's own docs look different
without either of them needing a separate build or env var.

Nothing here is allowed to break the public site. `_site.yml` is a
hand-editable file in a repo a community can send pull requests to, so a
missing file, an empty file, broken YAML, a key holding the wrong type, an
unknown key someone invented, or a colour value that isn't a colour all have
to degrade to the built-in default rather than raise -- read_branding() never
propagates an exception (see _load()).

`_site` is deliberately underscore-prefixed: content_files.list_project_slugs()
skips every underscore-prefixed directory, so this folder can never be
mistaken for (or synced in as) a project of its own.
"""

import logging
import re
from pathlib import Path
from urllib.parse import quote

import yaml

from app.services import content_assets, site_languages
from app.services.content_files import content_root
from app.settings import settings

log = logging.getLogger("docuwaves")

SITE_DIRNAME = "_site"
# Same file site_languages.py reads `languages:` out of -- named there
# because that module sits below this one and has to find it on its own.
SITE_FILENAME = site_languages.SITE_FILENAME

# The product's own name, used when `_site.yml` has no `name:` -- the same
# string the frontend's app.title carries in both dictionaries, so an
# unbranded instance looks exactly as it did before this feature existed.
DEFAULT_NAME = "DocuWaves"

# Long enough for any real site name/tagline/footer line, short enough that a
# pasted essay can't push the header or footer off the screen. Truncation is
# silent on purpose: refusing to render the whole site over an over-long
# string would be the opposite of this module's contract.
_MAX_TEXT = 200
_MAX_FOOTER_LINKS = 12

# Only #rgb / #rrggbb. The value is written into a CSS custom property, so
# anything else -- `red; background: url(...)`, `javascript:alert(1)`, an
# unclosed quote -- must never reach the stylesheet; an unmatched value falls
# back to "" (see _accent), which means "keep the built-in accent".
_ACCENT_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# A footer link's href ends up in the page's DOM, so the scheme is allowlisted
# rather than blocklisted: http(s), mailto, or a site-relative path. That
# rejects `javascript:`/`data:` without having to guess at every other scheme
# a browser might one day treat as executable.
_SAFE_LINK_RE = re.compile(r"^(?:https?://|mailto:|/)", re.IGNORECASE)

_ASSET_URL_PREFIX = "/api/public/site/assets"


def site_dir() -> Path:
    return content_root() / SITE_DIRNAME


def site_file() -> Path:
    return content_root() / SITE_FILENAME


def _rel(path: Path) -> str:
    return str(path.relative_to(Path(settings.content_repo_path)))


# ---- Assets ----
#
# A `_site/` image is served under its own URL prefix but is otherwise
# governed by exactly the same machinery as a project's image: the two
# functions below are thin aliases over content_assets, not a second
# implementation of it. `_site` sits DIRECTLY inside content/, the same as a
# project directory does, so content_assets.resolve_asset() -- whose
# containment check resolves both sides and compares resolved paths -- gives
# `_site` the identical traversal/symlink/extension rules a project gets, and
# the public router runs the identical SVG Content-Security-Policy over the
# response. A separate resolver here would be the same rules re-typed, and
# the copy that quietly drifts is always the one guarding the smaller
# surface.


def resolve_site_asset(relative_path: str) -> Path | None:
    """A `_site/` file, or None if it doesn't exist, isn't an allowed image
    type, or points outside `_site/` -- content_assets.resolve_asset() with
    `_site` in the place of a project slug, which is literally what the
    directory is."""
    return content_assets.resolve_asset(SITE_DIRNAME, relative_path)


def asset_url(filename: str) -> str:
    # quote(): a file committed into `_site/` by hand can have spaces or
    # other characters in its name (uploads are slugified, hand-added files
    # aren't). safe="" so a `/` in a stored name can't widen the path.
    return f"{_ASSET_URL_PREFIX}/{quote(filename, safe='')}"


def unique_asset_filename(original_name: str) -> str:
    return content_assets.unique_filename_in(site_dir(), original_name)


def write_site_asset(filename: str, data: bytes) -> str:
    """Returns the written path relative to the content repo ROOT, the form
    git_content_repo.commit_and_push() stages."""
    return content_assets.write_asset_in(site_dir(), filename, data)


# ---- Reading ----


def _load() -> dict:
    """The raw mapping from `_site.yml`, or {} for every failure mode there
    is -- see site_languages.load_site_document(), which is this loader,
    moved one layer down so the language list can share it (and so the file
    is parsed once per change rather than once per reader)."""
    return site_languages.load_site_document()


def _text(data: dict, key: str, default: str = "") -> str:
    value = data.get(key, default)
    # A non-string scalar (`name: 2026`, `tagline: true`) is a mistake, not a
    # value worth str()-ing into the header -- YAML would also turn an
    # unquoted `#00d4d5`-style value into something surprising. Fall back.
    if not isinstance(value, str):
        return default
    return value.strip()[:_MAX_TEXT] or default


def _localized_text(data: dict, key: str, default: str = "") -> tuple[str, dict[str, str]]:
    """`name`/`tagline`/`footer_text` as (default-language text, per-language
    mapping) -- the same string-or-mapping rule `_project.yml` follows, see
    site_languages.split_localized(). A plain string still answers exactly
    as _text() does, mapping empty, which is every existing instance."""
    value = data.get(key)
    if not isinstance(value, dict):
        return _text(data, key, default), {}
    text, mapping = site_languages.split_localized(value)
    mapping = {code: value[:_MAX_TEXT] for code, value in mapping.items()}
    return (text[:_MAX_TEXT] or default), mapping


def _accent(data: dict) -> str:
    value = data.get("accent")
    if isinstance(value, str) and _ACCENT_RE.match(value.strip()):
        return value.strip().lower()
    # "" rather than the stylesheet's own #4f6df5: the built-in accent has a
    # DIFFERENT value in dark mode, so answering with the light-mode hex here
    # would silently break dark mode for every unbranded instance. Empty
    # means "don't override anything", which both modes already handle.
    return ""


def _footer_links(data: dict) -> list[dict]:
    raw = data.get("footer_links")
    if not isinstance(raw, list):
        return []
    links: list[dict] = []
    for item in raw[:_MAX_FOOTER_LINKS]:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        url = item.get("url")
        if not isinstance(label, str) or not isinstance(url, str):
            continue
        label = label.strip()[:_MAX_TEXT]
        url = url.strip()
        # One malformed row is dropped, the rest of the footer still renders
        # -- the same "degrade, don't fail" rule the whole file follows.
        if label and _SAFE_LINK_RE.match(url):
            links.append({"label": label, "url": url})
    return links


def _asset_field(data: dict, key: str) -> tuple[str, str | None]:
    """(configured filename, servable URL). The URL is None whenever the name
    doesn't resolve to a real allowed image inside `_site/` -- a typo'd or
    deleted logo then falls back to the site name as text instead of leaving
    a broken image in the header. The configured name is still returned, so
    the admin form shows what the file actually says."""
    name = data.get(key)
    if not isinstance(name, str) or not name.strip():
        return "", None
    name = name.strip()
    if resolve_site_asset(name) is None:
        return name, None
    return name, asset_url(name)


def read_branding() -> dict:
    """The resolved branding, every field filled in -- what both
    GET /api/public/site and the admin form are built from.

    The three human-readable fields come back twice: `name` is the default
    language's value (what a single-language instance has always had), and
    `name_i18n` is the raw per-language mapping, empty for a plain string.
    Resolving them server-side would mean the frontend refetching branding
    on every language switch -- the mappings are two short strings, so the
    one response carries every language and the reader's current one is
    picked in the browser.

    `languages` / `default_language` ride along because they live in this
    same file and every consumer that has the branding needs them (the
    header's switcher, the URL prefix, the admin form's per-language
    fields)."""
    data = _load()
    logo, logo_url = _asset_field(data, "logo")
    logo_dark, logo_dark_url = _asset_field(data, "logo_dark")
    favicon, favicon_url = _asset_field(data, "favicon")
    name, name_i18n = _localized_text(data, "name", DEFAULT_NAME)
    tagline, tagline_i18n = _localized_text(data, "tagline")
    footer_text, footer_text_i18n = _localized_text(data, "footer_text")
    return {
        "languages": site_languages.languages(),
        "default_language": site_languages.default_language(),
        "name": name,
        "name_i18n": name_i18n,
        "tagline": tagline,
        "tagline_i18n": tagline_i18n,
        "footer_text": footer_text,
        "footer_text_i18n": footer_text_i18n,
        "logo": logo,
        "logo_url": logo_url,
        "logo_dark": logo_dark,
        "logo_dark_url": logo_dark_url,
        "favicon": favicon,
        "favicon_url": favicon_url,
        "accent": _accent(data),
        "footer_links": _footer_links(data),
    }


# ---- Writing ----


def _i18n_payload(payload: dict, key: str) -> dict[str, str]:
    """A `*_i18n` mapping as it arrived from the admin form, filtered to
    real strings. Only the CONFIGURED languages survive: the form can't
    offer any others, so anything else is a hand-crafted request, and
    letting it through would put a language in the file that no reader of
    this instance can ever select."""
    raw = payload.get(key)
    if not isinstance(raw, dict):
        return {}
    configured = site_languages.languages()
    return {
        code: value.strip()[:_MAX_TEXT]
        for code, value in raw.items()
        if code in configured and isinstance(value, str) and value.strip()
    }


def write_branding(payload: dict) -> list[str]:
    """Writes `_site.yml` from an admin-form payload, normalized through the
    exact same validators reading uses -- a rejected accent or a
    `javascript:` footer link never reaches the file in the first place,
    rather than being written and then filtered out on every later read.

    Empty fields are omitted entirely instead of written as `key: ''`: the
    file stays the short, hand-editable thing a contributor can read, and an
    omitted key and an empty one already mean the same thing to the reader
    above. Keys this version doesn't know about are NOT carried over -- the
    admin form is the whole file's editor, and silently re-emitting something
    it can't show would be worse than the honest round-trip.

    `languages:` is the one exception, and it is re-emitted from the FILE
    rather than from the payload: it decides how every page file in the repo
    is named and how every URL is shaped, so a branding save must never be
    able to drop or change it (a stale admin tab posting a payload from
    before the key existed would otherwise silently un-translate the whole
    instance). It is edited in the file, by hand or by pull request."""
    default_lang = site_languages.default_language()
    normalized = {
        "languages": site_languages.languages(),
        "name": site_languages.to_yaml_value(_text(payload, "name", DEFAULT_NAME), _i18n_payload(payload, "name_i18n"), default_lang),
        "tagline": site_languages.to_yaml_value(_text(payload, "tagline"), _i18n_payload(payload, "tagline_i18n"), default_lang),
        "logo": _text(payload, "logo"),
        "logo_dark": _text(payload, "logo_dark"),
        "favicon": _text(payload, "favicon"),
        "accent": _accent(payload),
        "footer_text": site_languages.to_yaml_value(
            _text(payload, "footer_text"), _i18n_payload(payload, "footer_text_i18n"), default_lang
        ),
        "footer_links": _footer_links(payload),
    }
    document = {k: v for k, v in normalized.items() if v}

    path = site_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return [_rel(path)]
