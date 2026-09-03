"""Shared fixtures.

Everything here runs against a content repo built in a temp directory and
NO database. That is a deliberate boundary: the rules worth pinning down --
where an image path is allowed to resolve to, what a slug becomes when it
collides, which language a reader falls back to, whether a frozen version
refuses a write -- are all decided by the files and by pure functions above
them. Testing them needs a directory, not a server.
"""
import sys
from pathlib import Path

import pytest
import yaml

# The tests import `app.*` the same way the application does, so the backend
# directory has to be importable whether pytest is run from there or from the
# repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import content_versions, site_languages  # noqa: E402
from app.settings import settings  # noqa: E402

# Any bytes with an allowed extension: resolve_asset checks the suffix and
# that the file exists, never that it decodes as an image.
IMAGE_BYTES = b"not really a png, and nothing here reads it as one"


class ContentRepo:
    """A content repo under construction, in the layout content_files writes."""

    def __init__(self, root: Path):
        self.root = root  # <repo>/content

    def site(self, **fields) -> "ContentRepo":
        (self.root / "_site.yml").write_text(yaml.safe_dump(fields), encoding="utf-8")
        return self

    def project(self, slug: str, **fields) -> "ContentRepo":
        directory = self.root / slug
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "_project.yml").write_text(
            yaml.safe_dump({"name": slug.title(), **fields}), encoding="utf-8"
        )
        return self

    def category(self, project: str, slug: str, version: str = "", **fields) -> "ContentRepo":
        directory = self.content_dir(project, version) / slug
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "_category.yml").write_text(
            yaml.safe_dump({"name": slug.title(), **fields}), encoding="utf-8"
        )
        return self

    def asset(self, project: str, name: str, version: str = "") -> Path:
        directory = self.content_dir(project, version) / "assets"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_bytes(IMAGE_BYTES)
        return path

    def versions(self, project: str, default: str, frozen: list[str]) -> "ContentRepo":
        """Writes _versions.yml. Does NOT move anything -- the callers that
        care about the move do it explicitly, so a test that depends on the
        first freeze's layout shows that layout in its own body."""
        (self.root / project / "_versions.yml").write_text(
            yaml.safe_dump(
                {
                    "current_label": "Current",
                    "default": default,
                    "versions": [{"id": v, "label": v, "released": "2026-01-01"} for v in frozen],
                }
            ),
            encoding="utf-8",
        )
        return self

    def content_dir(self, project: str, version: str = "") -> Path:
        return self.root / project / version if version else self.root / project


@pytest.fixture
def content(tmp_path, monkeypatch) -> ContentRepo:
    """An empty content repo, with `settings` pointed at it.

    The module-level caches are reset too. They key on path plus mtime and
    size, so a fresh temp directory per test would almost always miss them
    anyway -- "almost always" being the reason to clear them rather than
    reason not to.
    """
    root = tmp_path / "repo" / "content"
    root.mkdir(parents=True)
    monkeypatch.setattr(settings, "content_repo_path", str(tmp_path / "repo"))
    monkeypatch.setattr(content_versions, "_cache", {})
    monkeypatch.setattr(site_languages, "_cache", None)
    monkeypatch.setattr(site_languages, "_languages_cache", None)
    return ContentRepo(root)
