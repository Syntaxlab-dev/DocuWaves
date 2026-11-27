#!/usr/bin/env python3
"""docuwaves-lint: checks a content tree against the DocuWaves content format.

    python docuwaves_lint.py path/to/content          # diagnostics, exit 1 on errors
    python docuwaves_lint.py path/to/content --json   # the model and diagnostics as JSON

A second, independent reader of spec/content-format.md: it shares no code
with the DocuWaves backend, and needs nothing but PyYAML. Both are checked
against spec/conformance/, which is what makes the spec the thing they agree
on rather than whatever one of them happens to do.

Section numbers in comments refer to the spec.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # 2.3
LANG_RE = re.compile(r"^[a-z]{2}$")  # 4
MAX_LANGUAGES = 12
MAX_DEPTH = 4  # 5.3
VERSION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")  # 7
RESERVED_VERSION_IDS = {"current", "assets", "c", "pages", "changes", "feed.xml", "print", "glossary"}
MAX_VERSION_ID = 40
MAX_VERSIONS = 50
MAX_REDIRECT_HOPS = 5  # 8

PROJECT_KEYS = {"name", "description", "icon", "color", "image", "order", "visibility", "review", "review_every", "source"}
CATEGORY_KEYS = {"name", "icon", "image", "order", "parent"}
PAGE_KEYS = {"title", "order", "published", "reviewed_by", "reviewed_at", "slug", "draft"}
VERSIONS_KEYS = {"current_label", "default", "versions"}
VERSION_ENTRY_KEYS = {"id", "label", "released"}
SITE_KEYS = {
    "languages", "name", "tagline", "logo", "logo_dark", "favicon", "accent", "footer_text", "footer_links",
    "powered_by", "announcement", "appearance", "custom_css", "analytics",
}

ERROR = "error"
WARNING = "warning"
LEVELS = {
    "yaml-invalid": ERROR,
    "field-invalid": ERROR,
    "unknown-key": WARNING,
    "slug-not-canonical": WARNING,
    "duplicate-page": ERROR,
    "duplicate-language": WARNING,
    "parent-invalid": ERROR,
    "version-invalid": ERROR,
    "redirect-loop": WARNING,
}


class Reader:
    def __init__(self, root: Path):
        self.root = root
        self.diagnostics: list[dict] = []

    # ---- reporting ----

    def report(self, code: str, path: Path, detail: str = "") -> None:
        self.diagnostics.append(
            {"level": LEVELS[code], "code": code, "path": path.relative_to(self.root).as_posix(), "detail": detail}
        )

    # ---- 3. YAML ----

    def load_yaml_text(self, text: str, path: Path) -> dict:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            self.report("yaml-invalid", path, str(exc).splitlines()[0])
            return {}
        if data is None:
            return {}
        if not isinstance(data, dict):
            self.report("yaml-invalid", path, "not a mapping")
            return {}
        return data

    def load_yaml(self, path: Path) -> dict:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            self.report("yaml-invalid", path, str(exc))
            return {}
        return self.load_yaml_text(text, path)

    def unknown_keys(self, data: dict, known: set[str], path: Path, prefixes: tuple[str, ...] = ()) -> None:
        for key in data:
            name = str(key)
            if name not in known and not name.startswith(prefixes or ("\0",)):
                self.report("unknown-key", path, name)

    def text(self, data: dict, key: str, default: str, path: Path) -> str:
        """A plain string field. Numbers and booleans are read as their text;
        anything else takes the default."""
        if key not in data or data[key] is None:
            return default
        value = data[key]
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        self.report("field-invalid", path, key)
        return default

    def integer(self, data: dict, key: str, path: Path, minimum: int | None = None) -> int:
        if key not in data or data[key] is None:
            return 0
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, int) or (minimum is not None and value < minimum):
            self.report("field-invalid", path, key)
            return 0
        return value

    def boolean(self, data: dict, key: str, path: Path) -> bool:
        if key not in data or data[key] is None:
            return False
        value = data[key]
        if not isinstance(value, bool):
            self.report("field-invalid", path, key)
            return False
        return value

    def localized(self, data: dict, key: str, default: str, path: Path, default_language: str) -> str:
        """3.1: the text in the default language, which is what the model records."""
        if key not in data or data[key] is None:
            return default
        value = data[key]
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            return str(value) if str(value).strip() else default
        if isinstance(value, dict):
            mapping = {
                str(k).strip().lower(): v.strip()
                for k, v in value.items()
                if isinstance(v, str) and v.strip() and LANG_RE.match(str(k).strip().lower())
            }
            if not mapping:
                return default
            return mapping.get(default_language) or next(iter(mapping.values()))
        self.report("field-invalid", path, key)
        return default

    def slug_check(self, slug: str, path: Path) -> None:
        if not SLUG_RE.match(slug):
            self.report("slug-not-canonical", path, slug)

    # ---- 4. languages ----

    def languages(self) -> list[str]:
        path = self.root / "_site.yml"
        if not path.is_file():
            return []
        data = self.load_yaml(path)
        self.unknown_keys(data, SITE_KEYS, path)
        raw = data.get("languages")
        if raw is None:
            return []
        if not isinstance(raw, list):
            self.report("field-invalid", path, "languages")
            return []
        result: list[str] = []
        for item in raw[:MAX_LANGUAGES]:
            code = item.strip().lower() if isinstance(item, str) else ""
            if not LANG_RE.match(code) or code in result:
                self.report("field-invalid", path, f"languages: {item!r}")
                continue
            result.append(code)
        return result

    # ---- the tree ----

    def read(self) -> dict:
        languages = self.languages()
        default_language = languages[0] if languages else ""
        projects = []
        for directory in sorted(p for p in self.root.iterdir() if p.is_dir()):
            if directory.name.startswith("_") or not (directory / "_project.yml").is_file():
                continue
            projects.append(self.project(directory, languages, default_language))
        return {"languages": languages, "projects": projects}

    def project(self, directory: Path, languages: list[str], default_language: str) -> dict:
        path = directory / "_project.yml"
        self.slug_check(directory.name, path)
        data = self.load_yaml(path)
        self.unknown_keys(data, PROJECT_KEYS, path)
        name = self.localized(data, "name", directory.name, path, default_language)
        self.localized(data, "description", "", path, default_language)
        for key in ("icon", "color", "image"):
            self.text(data, key, "", path)
        order = self.integer(data, "order", path)
        self.integer(data, "review_every", path, minimum=0)
        if "source" in data and data["source"] is not None and not isinstance(data["source"], dict):
            self.report("field-invalid", path, "source")

        versions = self.versions(directory)
        content_dirs = [(v, directory / v) for v in versions] if versions else [("", directory)]

        categories: list[dict] = []
        pages: list[dict] = []
        for version, content_dir in content_dirs:
            version_categories = self.categories(content_dir, version, default_language)
            categories.extend(version_categories)
            pages.extend(self.pages(content_dir, version, version_categories, languages, default_language))

        return {
            "slug": directory.name,
            "name": name,
            "order": order,
            "private": self.text(data, "visibility", "", path).strip().lower() == "private",
            "review_required": self.text(data, "review", "", path).strip().lower() == "required",
            "versions": versions,
            "categories": categories,
            "pages": pages,
            "redirects": self.redirects(directory),
        }

    # ---- 7. versions ----

    def versions(self, directory: Path) -> list[str]:
        path = directory / "_versions.yml"
        if not path.is_file():
            return []
        data = self.load_yaml(path)
        self.unknown_keys(data, VERSIONS_KEYS, path)
        raw = data.get("versions")
        if raw is not None and not isinstance(raw, list):
            self.report("field-invalid", path, "versions")
            raw = []
        ids: list[str] = []
        for item in (raw or [])[:MAX_VERSIONS]:
            version_id = str(item.get("id", "")).strip() if isinstance(item, dict) else ""
            if (
                not VERSION_ID_RE.match(version_id)
                or len(version_id) > MAX_VERSION_ID
                or version_id in RESERVED_VERSION_IDS
                or version_id in ids
            ):
                self.report("version-invalid", path, repr(item.get("id") if isinstance(item, dict) else item))
                continue
            self.unknown_keys(item, VERSION_ENTRY_KEYS, path)
            ids.append(version_id)
        return ["current", *ids]

    # ---- 5.3 categories ----

    def categories(self, content_dir: Path, version: str, default_language: str) -> list[dict]:
        if not content_dir.is_dir():
            return []
        read: dict[str, dict] = {}
        for directory in sorted(p for p in content_dir.iterdir() if p.is_dir()):
            if directory.name.startswith("_") or directory.name == "assets":
                continue
            path = directory / "_category.yml"
            if not path.is_file():
                continue
            self.slug_check(directory.name, path)
            data = self.load_yaml(path)
            self.unknown_keys(data, CATEGORY_KEYS, path)
            for key in ("icon", "image"):
                self.text(data, key, "", path)
            read[directory.name] = {
                "version": version,
                "slug": directory.name,
                "name": self.localized(data, "name", directory.name, path, default_language),
                "order": self.integer(data, "order", path),
                "parent": self.text(data, "parent", "", path).strip(),
                "_path": path,
            }

        parents = {slug: c["parent"] for slug, c in read.items()}
        for slug in sorted(parents):
            parent = parents[slug]
            if not parent:
                continue
            reason = ""
            if parent == slug:
                reason = "a category cannot be its own parent"
            elif parent not in parents:
                reason = f"parent '{parent}' does not exist"
            else:
                seen, cursor, depth = {slug}, parent, 1
                while cursor:
                    if cursor in seen:
                        reason = f"parent '{parent}' makes a loop"
                        break
                    seen.add(cursor)
                    depth += 1
                    cursor = parents.get(cursor, "")
                if not reason and depth > MAX_DEPTH:
                    reason = f"deeper than {MAX_DEPTH} levels"
            if reason:
                parents[slug] = ""
                self.report("parent-invalid", read[slug]["_path"], reason)

        result = []
        for slug in sorted(read):
            category = read[slug]
            category["parent"] = parents[slug]
            del category["_path"]
            result.append(category)
        return result

    # ---- 6. pages ----

    def pages(
        self, content_dir: Path, version: str, categories: list[dict], languages: list[str], default_language: str
    ) -> list[dict]:
        claimed: dict[tuple[str, str], str] = {}
        result = []
        for category in categories:  # sorted by slug: the first category wins (2.3)
            directory = content_dir / category["slug"]
            files: dict[tuple[str, str], Path] = {}
            for path in sorted(p for p in directory.iterdir() if p.is_file() and p.name.endswith(".md")):
                stem = path.name[: -len(".md")]
                slug, dot, code = stem.rpartition(".")
                if not (dot and code in languages):
                    slug, code = stem, ""
                key = (slug, code or default_language)
                if key in files:
                    # 4: the suffixed file wins; the plain one is the duplicate.
                    loser, winner = (files[key], path) if code else (path, files[key])
                    self.report("duplicate-language", loser, f"{winner.name} is used")
                    files[key] = winner
                    continue
                files[key] = path
            for (slug, language), path in sorted(files.items()):
                if (slug, language) in claimed:
                    self.report("duplicate-page", path, f"already in category '{claimed[(slug, language)]}'")
                    continue
                claimed[(slug, language)] = category["slug"]
                self.slug_check(slug, path)
                result.append(self.page(path, version, category["slug"], slug, language))
        result.sort(key=lambda p: (p["slug"], p["language"]))
        return result

    def page(self, path: Path, version: str, category: str, slug: str, language: str) -> dict:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            self.report("yaml-invalid", path, str(exc))
            text = ""
        data = self.frontmatter(text, path)
        self.unknown_keys(data, PAGE_KEYS, path, prefixes=("review_",))
        title = self.text(data, "title", slug, path)
        for key in ("reviewed_by", "reviewed_at"):
            if key in data and not isinstance(data[key], str) and data[key] is not None:
                if key == "reviewed_at" and hasattr(data[key], "isoformat"):
                    continue  # an unquoted date: readable, only not canonical
                self.report("field-invalid", path, key)
        if "draft" in data:
            self.boolean(data, "draft", path)
        return {
            "version": version,
            "category": category,
            "slug": slug,
            "language": language,
            "title": title if title.strip() else slug,
            "order": self.integer(data, "order", path),
            "published": self.boolean(data, "published", path),
        }

    def frontmatter(self, text: str, path: Path) -> dict:
        lines = text.split("\n")
        if not lines or lines[0].rstrip() != "---":
            return {}
        for index in range(1, len(lines)):
            if lines[index].rstrip() in ("---", "..."):
                return self.load_yaml_text("\n".join(lines[1:index]), path)
        self.report("yaml-invalid", path, "frontmatter is never closed")
        return {}

    # ---- 8. redirects ----

    def redirects(self, directory: Path) -> dict[str, str]:
        path = directory / "_redirects.yml"
        if not path.is_file():
            return {}
        data = self.load_yaml(path)
        self.unknown_keys(data, {"pages"}, path)
        raw = data.get("pages")
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            self.report("field-invalid", path, "pages")
            return {}
        pages = {str(k).strip(): str(v).strip() for k, v in raw.items() if k is not None and v is not None}
        pages = {k: v for k, v in pages.items() if k and v}
        for start in sorted(pages):
            seen, target, hops = {start}, pages[start], 0
            while target in pages and hops < MAX_REDIRECT_HOPS:
                if target in seen:
                    self.report("redirect-loop", path, start)
                    break
                seen.add(target)
                target = pages[target]
                hops += 1
            else:
                if target in seen:
                    self.report("redirect-loop", path, start)
        return dict(sorted(pages.items()))


def lint(root: Path) -> dict:
    reader = Reader(root)
    model = reader.read()
    diagnostics = sorted(reader.diagnostics, key=lambda d: (d["path"], d["code"], d["detail"]))
    return {"model": model, "diagnostics": diagnostics}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a DocuWaves content tree (spec/content-format.md).")
    parser.add_argument("content", type=Path, help="the content/ directory")
    parser.add_argument("--json", action="store_true", help="print the model and the diagnostics as JSON")
    args = parser.parse_args(argv)
    if not args.content.is_dir():
        print(f"{args.content}: not a directory", file=sys.stderr)
        return 2
    result = lint(args.content)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for d in result["diagnostics"]:
            detail = f" ({d['detail']})" if d["detail"] else ""
            print(f"{d['path']}: {d['level']}: {d['code']}{detail}")
        errors = sum(d["level"] == ERROR for d in result["diagnostics"])
        warnings = len(result["diagnostics"]) - errors
        print(f"{errors} error(s), {warnings} warning(s)", file=sys.stderr)
    return 1 if any(d["level"] == ERROR for d in result["diagnostics"]) else 0


if __name__ == "__main__":
    sys.exit(main())
