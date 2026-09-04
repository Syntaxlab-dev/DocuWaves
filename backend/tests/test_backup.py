"""What the export archive contains -- and, more importantly, what it does
not.

The single rule worth a test: `.git` never goes into the archive. That
directory's `config` holds the remote URL, and on a remote-backed instance
that URL has the push token embedded in it. An export is a file made to be
emailed to yourself and dropped in cloud storage, so a `.git` entry in it is
a leaked credential with a delivery mechanism attached.
"""
import zipfile
from datetime import datetime, timezone

import pytest

from app.services import backup, page_feedback_store


@pytest.fixture
def repo(content, monkeypatch, tmp_path):
    """A content repo with a page, an image, and a `.git` directory that
    looks exactly like the real one does -- push token included, because
    that is the thing being kept out."""
    content.project("demo").category("demo", "guide")
    (content.root / "demo" / "guide" / "install.md").write_text(
        "---\ntitle: Install\n---\n\nBody.\n", encoding="utf-8"
    )
    content.asset("demo", "shot.png")
    git_dir = content.root.parent / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text(
        '[remote "origin"]\n\turl = https://x:github_pat_SECRET@github.com/x/y.git\n', encoding="utf-8"
    )
    # No database in these tests (see conftest), and no git repository to
    # bundle -- both are stubbed to the answers they would give on a fresh
    # instance, which is also the interesting case for the README.
    monkeypatch.setattr(page_feedback_store, "export_all", lambda: [])
    monkeypatch.setattr(backup, "_write_bundle", lambda destination: False)
    return content


def entries(archive_path) -> list[str]:
    with zipfile.ZipFile(archive_path) as archive:
        return archive.namelist()


class TestWhatIsExcluded:
    def test_the_git_directory_never_travels(self, repo, tmp_path):
        names = entries_for(repo, tmp_path)
        assert not any(".git" in name for name in names)

    def test_and_the_token_it_holds_is_nowhere_in_the_file(self, repo, tmp_path):
        """Belt and braces: not merely "no entry named .git", but the secret
        itself absent from the bytes of the archive."""
        destination = tmp_path / "export.zip"
        backup.build_archive(destination)
        assert b"github_pat_SECRET" not in destination.read_bytes()


class TestWhatIsIncluded:
    def test_the_working_tree_under_the_repository_s_own_layout(self, repo, tmp_path):
        """`content-repo/content/...`, which is the path these files have on
        disk -- so the restore step can name a directory to copy rather than
        describe a rewrite."""
        names = entries_for(repo, tmp_path)
        assert f"{backup.CONTENT_DIRNAME}/content/demo/guide/install.md" in names
        assert f"{backup.CONTENT_DIRNAME}/content/demo/assets/shot.png" in names

    def test_the_feedback_and_the_readme_are_always_there(self, repo, tmp_path):
        names = entries_for(repo, tmp_path)
        assert backup.FEEDBACK_NAME in names
        assert backup.READ_ME_NAME in names

    def test_no_bundle_when_there_is_no_history_and_the_readme_says_so(self, repo, tmp_path):
        destination = tmp_path / "export.zip"
        backup.build_archive(destination)
        with zipfile.ZipFile(destination) as archive:
            assert backup.BUNDLE_NAME not in archive.namelist()
            readme = archive.read(backup.READ_ME_NAME).decode("utf-8")
        assert "no commits to bundle" in readme

    def test_the_readme_names_what_is_deliberately_absent(self, repo, tmp_path):
        destination = tmp_path / "export.zip"
        backup.build_archive(destination)
        with zipfile.ZipFile(destination) as archive:
            readme = archive.read(backup.READ_ME_NAME).decode("utf-8")
        for absent in ["password hash", "sessions", "API tokens", "preview links"]:
            assert absent in readme


class TestSummary:
    def test_counts_the_files_that_will_actually_go_in(self, repo):
        """_project.yml, _category.yml, install.md, assets/shot.png -- and
        NOT .git/config. `.git` is excluded from the count as well as from
        the archive; a size that counted it would over-promise on every
        instance that has a history."""
        assert backup.summary()["files"] == 4

    def test_is_stable_across_two_runs(self, repo, tmp_path):
        """Sorted entries, so two exports of an unchanged repo can be
        diffed against each other and say something."""
        assert entries_for(repo, tmp_path, "a.zip") == entries_for(repo, tmp_path, "b.zip")


class TestArchiveName:
    def test_sorts_by_date_and_says_what_it_is(self):
        name = backup.archive_name(datetime(2026, 9, 4, tzinfo=timezone.utc))
        assert name == "docuwaves-export-2026-09-04.zip"


def entries_for(repo, tmp_path, name="export.zip") -> list[str]:
    destination = tmp_path / name
    backup.build_archive(destination)
    return entries(destination)
