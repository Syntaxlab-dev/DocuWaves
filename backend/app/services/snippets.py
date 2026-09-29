"""Snippets and variables: write a thing once, use it on every page.

    Install {{product}} {{version}}:

    <!-- snippet: prerequisites -->

VARIABLES are `{{name}}`. They come from, weakest first:

- built in: `project` (the project's name) and, in a versioned project,
  `version` (the label of the version being read -- so a frozen 2.0 page
  that says `{{version}}` keeps saying 2.0 without anyone editing it);
- `content/_variables.yml`, for the whole site;
- `_variables.yml` in the project's content directory -- the project
  directory, or the VERSION directory once the project is versioned, which is
  what lets a frozen version keep the download URL it was released with.

A value may be a mapping per language (`{de: ..., en: ...}`), the same shape
`name:` takes in `_project.yml`. An unknown name is left exactly as written,
because `{{ ... }}` means something else in plenty of what documentation
quotes (GitHub Actions, Helm, Jinja); for the same reason `${{ name }}` is
never touched. `\\{{name}}` writes the braces themselves.

SNIPPETS are Markdown files, `<name>.md` (or `<name>.<lang>.md`), in a
`_snippets/` directory next to the categories -- or in `content/_snippets/`
for the whole site -- included with `<!-- snippet: name -->` on a line of its
own. On GitHub the comment is invisible; the page reads without the snippet
rather than with stray syntax in it. A snippet may use variables and include
other snippets (a few levels deep; a loop is cut off, not followed). Inside a
fenced code block the line is code and stays as it is.

WHERE THIS APPLIES: to what READERS get -- the public page, a preview link,
search snippets, the page description, the chat's sources, webhook
summaries. The content repo, the editor and the MCP read tool keep the
SOURCE, because that is what gets edited: resolving it there would mean the
next save wrote `2.0` over every `{{version}}`. What search MATCHES is also
still the source text (see README, "Snippets and variables").
"""
import logging
import re
from pathlib import Path

import frontmatter
import yaml

from app.services import content_files, content_versions, site_languages

log = logging.getLogger("docuwaves")

VARIABLES_FILENAME = "_variables.yml"
SNIPPETS_DIRNAME = "_snippets"

_NAME = r"[A-Za-z0-9][A-Za-z0-9_-]*"
_VARIABLE_RE = re.compile(r"(\\|\$)?\{\{\s*([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*\}\}")
_INCLUDE_RE = re.compile(rf"^ {{0,3}}<!--\s*snippet:\s*({_NAME})\s*-->\s*$", re.IGNORECASE)
_SNIPPET_NAME_RE = re.compile(rf"^{_NAME}$")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8})*$")
_MAX_DEPTH = 4
_MAX_VALUE_CHARS = 2000

_MISSING = {
    "de": "> [!CAUTION]\n> Snippet „{name}“ nicht gefunden.",
    "en": "> [!CAUTION]\n> Snippet \"{name}\" not found.",
}


def resolve(markdown: str, project_slug: str, version: str, language: str = "", *, mark_missing: bool = False) -> str:
    """The page as a reader gets it. `mark_missing` shows an unknown snippet
    as a warning box (the editor's preview) instead of dropping it (the
    public site, where nobody can do anything about it)."""
    if "{{" not in markdown and "snippet:" not in markdown.lower():
        return markdown
    try:
        values = variables(project_slug, version, language)
        text = _include(markdown, project_slug, version, language, mark_missing, stack=())
        return _substitute(text, values)
    except OSError:
        # A read error on a snippet or variables file must cost the reader
        # the substitution, never the page.
        log.warning("Could not resolve snippets/variables for %s/%s.", project_slug, version, exc_info=True)
        return markdown


def resolve_page(page: dict, project_slug: str, *, mark_missing: bool = False) -> dict:
    """A copy of an index row with its body resolved."""
    return {
        **page,
        "markdown_content": resolve(
            page.get("markdown_content", ""), project_slug, page.get("version", ""), page.get("language", ""),
            mark_missing=mark_missing,
        ),
    }


# ---- Variables ----


def variables(project_slug: str, version: str, language: str = "") -> dict[str, str]:
    values: dict[str, str] = {}
    project = content_files.read_project(project_slug)
    if project:
        values["project"] = site_languages.pick(project["name"], project["name_i18n"], language)
    label = _version_label(project_slug, version)
    if label:
        values["version"] = label
    values.update(_read_variables(content_files.content_root() / VARIABLES_FILENAME, language))
    values.update(_read_variables(content_files.project_content_dir(project_slug, version) / VARIABLES_FILENAME, language))
    return values


def _version_label(project_slug: str, version: str) -> str:
    document = content_versions.read_versions(project_slug)
    if document is None:
        return ""
    version = version or document["default"]
    if version == content_versions.CURRENT_ID:
        return document["current_label"]
    return next((v["label"] for v in document["versions"] if v["id"] == version), "")


def _read_variables(path: Path, language: str) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        # Hand-edited and arriving by pull request like every other file:
        # a typo in it must not take pages down, just their variables.
        log.warning("%s is not valid YAML; its variables are ignored.", path)
        return {}
    if not isinstance(data, dict):
        return {}
    values: dict[str, str] = {}
    for name, raw in data.items():
        name = str(name)
        if isinstance(raw, dict):
            text, mapping = site_languages.split_localized(raw)
            value = site_languages.pick(text, mapping, language)
        elif isinstance(raw, (str, int, float)) and not isinstance(raw, bool):
            value = str(raw)
        else:
            continue
        values[name] = value[:_MAX_VALUE_CHARS]
    return values


def _substitute(text: str, values: dict[str, str]) -> str:
    def replace(match: re.Match) -> str:
        prefix, name = match.group(1), match.group(2)
        if prefix == "\\":
            return match.group(0)[1:]
        if prefix == "$" or name not in values:
            return match.group(0)
        return values[name]

    return _VARIABLE_RE.sub(replace, text)


# ---- Snippets ----


def snippet_path(project_slug: str, version: str, name: str, language: str = "") -> Path | None:
    """The file `<!-- snippet: name -->` means here: the project's own
    before the site's, the reader's language before the plain file."""
    if not _SNIPPET_NAME_RE.match(name):
        return None
    directories = [
        content_files.project_content_dir(project_slug, version) / SNIPPETS_DIRNAME,
        content_files.content_root() / SNIPPETS_DIRNAME,
    ]
    # Both parts are checked, never just trusted: they become a file name.
    localized = bool(language) and bool(_LANGUAGE_RE.match(language))
    filenames = [f"{name}.{language}.md", f"{name}.md"] if localized else [f"{name}.md"]
    for directory in directories:
        for filename in filenames:
            path = directory / filename
            if path.is_file():
                return path
    return None


def _include(
    markdown: str, project_slug: str, version: str, language: str, mark_missing: bool, stack: tuple[str, ...]
) -> str:
    out: list[str] = []
    fence: str | None = None
    for line in markdown.split("\n"):
        fence_match = _FENCE_RE.match(line)
        if fence is not None:
            if fence_match and fence_match.group(1)[0] == fence[0] and len(fence_match.group(1)) >= len(fence):
                fence = None
            out.append(line)
            continue
        if fence_match:
            fence = fence_match.group(1)
            out.append(line)
            continue

        match = _INCLUDE_RE.match(line)
        if not match:
            out.append(line)
            continue
        name = match.group(1)
        if name in stack or len(stack) >= _MAX_DEPTH:
            log.warning("Snippet %r includes itself or nests too deeply; not expanded further.", name)
            continue
        path = snippet_path(project_slug, version, name, language)
        if path is None:
            if mark_missing:
                lang = "de" if (language or site_languages.default_language()).startswith("de") else "en"
                out.append(_MISSING[lang].format(name=name))
            continue
        body = frontmatter.loads(path.read_text(encoding="utf-8")).content.strip("\n")
        out.append(_include(body, project_slug, version, language, mark_missing, (*stack, name)))
    return "\n".join(out)
