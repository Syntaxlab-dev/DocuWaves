"""A glossary: terms and what they mean, shown as a tooltip where a page
uses them and listed on a page of their own.

The terms live in the content repo, as `_glossary.yml` -- in the project's
content directory (the VERSION directory once the project is versioned, so
a frozen release keeps the definitions it shipped with), and/or in
`content/` for the whole site. A project's entry wins over the site's for
the same term.

    SLA: The availability we promise, as a percentage per month.
    Deployment:
      de: Das Ausliefern einer neuen Version auf die Server.
      en: Shipping a new release to the servers.

One term per line, the definition as plain text -- or one per language,
the same shape `name:` takes in `_project.yml`. A term written with a
lowercase letter matches regardless of case ("deployment" too); an acronym
written in capitals matches only in capitals, so "SLA" never marks the
"sla" inside a URL slug. Only the first use on a page gets the tooltip:
twenty underlined words in one paragraph would be noise.

Plain text on purpose. A definition is read in a small bubble; links and
lists belong on the page the term is about.
"""
from pathlib import Path

import yaml

from app.services import site_languages, snippets
from app.settings import settings

FILENAME = "_glossary.yml"
MAX_CHARS = 100_000
MAX_TERM = 80
MAX_DEFINITION = 600


class InvalidGlossary(ValueError):
    """Shown to the admin as it is."""


def _path(project_slug: str, version: str) -> Path:
    return snippets.scope_dir(project_slug, version) / FILENAME


def read_text(project_slug: str, version: str) -> str:
    path = _path(project_slug, version)
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _parse(text: str) -> dict:
    if not text.strip():
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (line {mark.line + 1})" if mark else ""
        raise InvalidGlossary(f"This is not valid YAML{where}.") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise InvalidGlossary("Write one term per line: Term: what it means")
    return data


def check_text(text: str) -> None:
    if len(text) > MAX_CHARS:
        raise InvalidGlossary("The glossary is too long.")
    for term, value in _parse(text).items():
        if not isinstance(term, (str, int, float)) or isinstance(term, bool) or not str(term).strip():
            raise InvalidGlossary(f"'{term}' can't be a term.")
        if len(str(term)) > MAX_TERM:
            raise InvalidGlossary(f"'{str(term)[:30]}…': a term is at most {MAX_TERM} characters.")
        values = value.values() if isinstance(value, dict) else [value]
        for item in values:
            if isinstance(item, bool) or not isinstance(item, (str, int, float)) or not str(item).strip():
                raise InvalidGlossary(
                    f"'{term}': a definition is text (or one per language). Put quotes around it if needed."
                )
            if len(str(item)) > MAX_DEFINITION:
                raise InvalidGlossary(f"'{term}': a definition is at most {MAX_DEFINITION} characters.")


def write_text(project_slug: str, version: str, text: str) -> list[str]:
    check_text(text)
    path = _path(project_slug, version)
    relative = str(path.relative_to(Path(settings.content_repo_path)))
    if not text.strip():
        if path.exists():
            path.unlink()
        return [relative]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return [relative]


def _definition(value, language: str) -> str:
    if isinstance(value, dict):
        mapping = {str(k): str(v) for k, v in value.items() if v is not None}
        default = site_languages.default_language()
        return (
            mapping.get(language)
            or mapping.get(default)
            or next(iter(mapping.values()), "")
        ).strip()
    return str(value).strip() if value is not None else ""


def _entries(project_slug: str, version: str, language: str) -> dict[str, str]:
    try:
        data = _parse(read_text(project_slug, version))
    except InvalidGlossary:
        return {}  # a broken file written by hand: no tooltips rather than an error page
    result = {}
    for term, value in data.items():
        if isinstance(term, bool) or not isinstance(term, (str, int, float)):
            continue
        definition = _definition(value, language)[:MAX_DEFINITION]
        name = str(term).strip()[:MAX_TERM]
        if name and definition:
            result[name] = definition
    return result


def terms(project_slug: str, version: str, language: str) -> list[dict]:
    """[{term, definition}], the site's and the project's, sorted by term."""
    merged = {**_entries("", "", language), **_entries(project_slug, version, language)}
    return [{"term": t, "definition": d} for t, d in sorted(merged.items(), key=lambda item: item[0].casefold())]
