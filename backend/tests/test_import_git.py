"""Import from a Git repository URL (services/import_git.py). No network:
the clone itself is replaced by writing the files it would have produced."""
import io
import subprocess
import zipfile

import pytest

from app.services import import_git


@pytest.mark.parametrize(
    "url, message",
    [
        ("http://github.com/org/repo.git", "https://"),
        ("file:///etc", "https://"),
        ("git@github.com:org/repo.git", "https://"),
        ("ssh://git@github.com/org/repo.git", "https://"),
        ("https://user:pw@github.com/org/repo.git", "token in its own field"),
        ("https://localhost/repo.git", "does not clone from"),
        ("https://127.0.0.1/repo.git", "does not clone from"),
        ("https://169.254.169.254/latest", "does not clone from"),
        ("https://[::1]/repo.git", "does not clone from"),
    ],
)
def test_only_https_to_somewhere_else(url, message):
    with pytest.raises(import_git.GitImportError, match=message):
        import_git.archive(url)


@pytest.mark.parametrize("path", ["../etc", "/../x", "docs/../../x"])
def test_the_folder_stays_inside_the_repository(path):
    with pytest.raises(import_git.GitImportError, match="inside the repository"):
        import_git._clean_subdir(path)


def test_a_branch_cannot_be_an_option():
    with pytest.raises(import_git.GitImportError):
        import_git.archive("https://10.0.0.5/repo.git", branch="--upload-pack=x")


def fake_clone(files: dict[str, str], seen: list):
    def run(command, **kwargs):
        seen.append((command, kwargs["env"]))
        from pathlib import Path

        target = Path(command[-1])
        for name, text in files.items():
            (target / name).parent.mkdir(parents=True, exist_ok=True)
            (target / name).write_text(text)
        (target / ".git").mkdir(exist_ok=True)
        (target / ".git" / "config").write_text("secret")
        return subprocess.CompletedProcess(command, 0, "", "")

    return run


def test_the_clone_becomes_the_archive_the_importer_reads(monkeypatch):
    seen = []
    monkeypatch.setattr(
        import_git.subprocess,
        "run",
        fake_clone({"mkdocs.yml": "nav: []\n", "docs/index.md": "# Hi\n", "src/app.py": "print()\n"}, seen),
    )
    data = import_git.archive("https://10.0.0.5/org/repo.git", branch="main", token="s3cret")
    names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
    assert names == {"mkdocs.yml", "docs/index.md"}  # no .git, no source code
    command, env = seen[0]
    assert "--depth" in command and "--branch" in command and "main" in command
    assert "https://x-access-token:s3cret@10.0.0.5/org/repo.git" in command
    assert env["GIT_ALLOW_PROTOCOL"] == "https" and env["GIT_TERMINAL_PROMPT"] == "0"


def test_one_folder_only(monkeypatch):
    monkeypatch.setattr(
        import_git.subprocess, "run", fake_clone({"README.md": "x", "docs/a.md": "# A\n", "docs/b/c.md": "# C\n"}, [])
    )
    data = import_git.archive("https://10.0.0.5/r.git", subdir="docs")
    assert set(zipfile.ZipFile(io.BytesIO(data)).namelist()) == {"a.md", "b/c.md"}


def test_a_failed_clone_does_not_echo_the_token(monkeypatch):
    def fail(command, **kwargs):
        return subprocess.CompletedProcess(command, 128, "", "fatal: could not read from https://x-access-token:s3cret@h/r")

    monkeypatch.setattr(import_git.subprocess, "run", fail)
    with pytest.raises(import_git.GitImportError) as info:
        import_git.archive("https://10.0.0.5/r.git", token="s3cret")
    assert "s3cret" not in str(info.value) and "could not be cloned" in str(info.value)
