"""The backend against spec/conformance/ (spec/content-format.md, section 10).

The model is built from the same functions a reindex uses
(content_sync._sync_categories_and_pages walks them in this order), without
a database: which categories, parents, pages and redirects a content tree
gives is decided by the files and these functions, not by the index.

tools/docuwaves-lint is held to the same cases, so the two readers can only
both pass by agreeing with the spec. Diagnostics are not compared here: the
backend logs what it drops rather than reporting codes.
"""

import json
import shutil
from pathlib import Path

import pytest

from app.services import content_files, content_sync, content_versions, page_redirects, site_languages

CASES = Path(__file__).resolve().parents[2] / "spec" / "conformance"
CASE_DIRS = sorted(p for p in CASES.iterdir() if (p / "content").is_dir())


def _model() -> dict:
    projects = []
    for slug in content_files.list_project_slugs():
        project = content_files.read_project(slug)
        versions = content_versions.version_ids(slug)
        categories, pages = [], []
        for version in content_versions.index_versions(slug):
            read = {}
            for category_slug in content_files.list_category_slugs(slug, version):
                data = content_files.read_category(slug, category_slug, version)
                if data is not None:
                    read[category_slug] = data
            parents = content_sync._valid_parents(slug, version, {s: d["parent"] for s, d in read.items()})
            claimed = set()
            for category_slug, data in read.items():
                categories.append(
                    {
                        "version": version,
                        "slug": category_slug,
                        "name": data["name"],
                        "order": data["order"],
                        "parent": parents[category_slug],
                    }
                )
            version_pages = []
            for category_slug in read:
                for page_slug, language in content_files.list_page_variants(slug, category_slug, version):
                    if (page_slug, language) in claimed:
                        continue
                    claimed.add((page_slug, language))
                    page = content_files.read_page(slug, category_slug, page_slug, language, version)
                    version_pages.append(
                        {
                            "version": version,
                            "category": category_slug,
                            "slug": page_slug,
                            "language": language,
                            "title": page["title"],
                            "order": page["order"],
                            "published": page["published"],
                        }
                    )
            pages.extend(sorted(version_pages, key=lambda p: (p["slug"], p["language"])))
        projects.append(
            {
                "slug": slug,
                "name": project["name"],
                "order": project["order"],
                "private": project["private"],
                "review_required": project["review_required"],
                "versions": versions,
                "categories": categories,
                "pages": pages,
                "redirects": dict(sorted(page_redirects.read(slug).items())),
            }
        )
    return {"languages": site_languages.languages(), "projects": projects}


@pytest.mark.parametrize("case", CASE_DIRS, ids=lambda p: p.name)
def test_case(case, content):
    shutil.rmtree(content.root)
    shutil.copytree(case / "content", content.root)
    expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
    assert _model() == expected["model"]
