"""`python -m app.cli preview-site`: a docs folder built into a static site
in a throwaway instance, with the sync's warnings (app/cli.py)."""
import json
import zipfile

from app import cli
from app.services import changelog, content_versions, git_content_repo, session_secret
from app.settings import settings


def test_a_docs_folder_becomes_a_site(tmp_path, monkeypatch):
    # Everything preview_site points elsewhere is put back after the test.
    for name in ("content_repo_path", "content_repo_url", "database_url", "sqlite_path", "webhook_urls", "smtp_host"):
        monkeypatch.setattr(settings, name, getattr(settings, name))
    monkeypatch.setattr(session_secret, "_SECRET_PATH", session_secret._SECRET_PATH)
    monkeypatch.setattr(content_versions, "_cache", {})
    monkeypatch.setattr(changelog, "_cache", None)
    monkeypatch.setattr(git_content_repo, "_repo", None)
    monkeypatch.setattr(git_content_repo, "_mode", git_content_repo._mode)
    git_content_repo._read_cache.clear()

    docs = tmp_path / "docs"
    (docs / "guide").mkdir(parents=True)
    (docs / "index.md").write_text("# Start\n\nRead the [guide](guide/setup.md) and [this](nowhere.md).\n")
    (docs / "guide" / "setup.md").write_text("# Setup\n\n```bash\nmake\n```\n")
    target = tmp_path / "out" / "site.zip"
    summary = tmp_path / "summary.json"

    assert cli.main(["preview-site", str(docs), str(target), "--name", "Handbook", "--summary", str(summary)]) == 0
    names = zipfile.ZipFile(target).namelist()
    assert "index.html" in names and any(n.endswith("/setup.html") for n in names)
    report = json.loads(summary.read_text())
    assert report["pages"] == 2
    assert any("nowhere.md" in w["message"] for w in report["warnings"])
    git_content_repo._read_cache.clear()


def test_a_missing_folder_is_said(tmp_path, capsys):
    assert cli.main(["preview-site", str(tmp_path / "nope"), str(tmp_path / "x.zip")]) == 1
    assert "not a folder" in capsys.readouterr().err
