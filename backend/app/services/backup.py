"""One file that contains this instance's documentation, and enough of the
rest to put it back.

WHY THIS EXISTS. A local-only instance keeps its entire content in the /data
volume and nowhere else -- that is stated plainly in the docs, and it is the
one thing about this app that can go permanently wrong. "Back up the volume"
is correct advice and useless advice: an operator who has to arrange it will
not, and an operator who does cannot easily check that what came out is
readable. This produces one file, from a button, that can be opened.

WHAT IS IN IT

    content-repo/      the repository's working tree, laid out exactly as it
                       is on disk (so `content-repo/content/<project>/...`):
                       every project, category, page, image and _site.yml as
                       plain Markdown and YAML a person can read without
                       this app existing.
    history.bundle     the complete git history, as a `git bundle`. Restore
                       with `git clone history.bundle content-repo`.
    page-feedback.json every "was this page helpful?" answer. It lives in
                       the database rather than in the repo (an anonymous
                       vote must not become a commit), so it is the one
                       piece of content-ish state a clone would not bring
                       back.
    README-EXPORT.md   what the archive holds and how to restore it.

WHY A GIT BUNDLE AND NOT THE `.git` DIRECTORY. Because `.git/config` holds
the remote URL, and on a remote-backed instance that URL has the push token
embedded in it (see git_content_repo._authenticated_url). Zipping `.git`
would put a working credential into a file whose whole purpose is to be
emailed to yourself and dropped in cloud storage. A bundle carries the
objects and the refs and nothing else: no config, no remotes, no
credentials, and it clones exactly like a repository.

WHAT IS DELIBERATELY NOT IN IT: the admin's password hash, live sessions,
API tokens, and preview links. All four are credentials, an export is a file
that travels, and none of them is something a restore needs -- an instance
restored from this archive asks whoever opens it to set up an admin account,
which is the correct thing for it to do.
"""

import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import git

from app.services import git_content_repo, page_feedback_store
from app.settings import settings

log = logging.getLogger("docuwaves")

# The archive's top-level folder. Named after the REPOSITORY rather than
# after the `content/` directory inside it, so an entry reads
# `content-repo/content/demo/install.md` -- which is the path it has on disk,
# and the path the restore instructions can therefore name without
# explaining a rewrite.
CONTENT_DIRNAME = "content-repo"
BUNDLE_NAME = "history.bundle"
FEEDBACK_NAME = "page-feedback.json"
READ_ME_NAME = "README-EXPORT.md"

# Skipped on the way in. `.git` is replaced by the bundle (see the module
# docstring); the rest is noise a checkout re-creates.
_SKIP_DIRS = {".git", "__pycache__", ".DS_Store"}


def archive_name(now: datetime | None = None) -> str:
    """Sorts chronologically in a downloads folder, and says what it is
    without being opened."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    return f"docuwaves-export-{stamp}.zip"


def _content_files() -> list[Path]:
    """Every file that goes into `content/`, in a stable order.

    Sorted rather than left in walk order so two exports of an unchanged
    repo produce archives with the same entries in the same sequence -- a
    diff between two backups then says something."""
    root = Path(settings.content_repo_path)
    if not root.is_dir():
        return []
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and not any(part in _SKIP_DIRS for part in path.relative_to(root).parts)
    ]
    return sorted(files)


def summary() -> dict:
    """What an export would contain, without building one -- so the admin
    card can say how big the download is before it is a download.

    Never raises, and measured in three independent pieces so one of them
    failing does not zero the other two: this is a line of text on a page,
    and "we could not count the votes" is no reason to stop saying how big
    the documentation is."""
    try:
        files = _content_files()
        measured = {"files": len(files), "bytes": sum(path.stat().st_size for path in files)}
    except OSError as exc:
        log.warning("Could not measure the content repo for export: %s", exc)
        measured = {"files": 0, "bytes": 0}
    try:
        votes = page_feedback_store.count()
    except Exception as exc:  # noqa: BLE001 -- any database trouble, see above
        log.warning("Could not count reader feedback for export: %s", exc)
        votes = 0
    return {**measured, "feedback_votes": votes, "history": _has_history()}


def _has_history() -> bool:
    """False for a repository with no commits yet -- a fresh install before
    anything has been written. The archive is still worth making; it just
    has no bundle in it, and says so."""
    try:
        repo = git_content_repo.ensure_clone()
        return bool(repo.head.is_valid())
    except (git_content_repo.GitContentError, git.GitError, ValueError):
        return False


def _write_bundle(destination: Path) -> bool:
    """`git bundle create --all`, or False when there is nothing to bundle.

    --all rather than the branch: a bundle is the backup of the history, and
    a tag or a second branch somebody made in the repo is part of that."""
    try:
        repo = git_content_repo.ensure_clone()
        if not repo.head.is_valid():
            return False
        repo.git.bundle("create", str(destination), "--all")
        return destination.is_file()
    except (git_content_repo.GitContentError, git.GitError, ValueError, OSError) as exc:
        # An archive with the readable content in it and no history is a
        # much better answer than a failed download. The README inside says
        # which of the two this is.
        log.warning("Could not bundle the content repo history for export: %s", exc)
        return False


def _readme(has_history: bool, votes: int) -> str:
    lines = [
        "# DocuWaves export",
        "",
        f"Made {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC.",
        "",
        "## What is in here",
        "",
        f"- `{CONTENT_DIRNAME}/` -- the content repository's working tree, exactly as it",
        f"  is on disk: `{CONTENT_DIRNAME}/content/<project>/<category>/<page>.md` and so on,",
        "  plus every image and `_site.yml`. Readable, and editable, without DocuWaves.",
    ]
    if has_history:
        lines += [
            f"- `{BUNDLE_NAME}` -- the complete version history as a git bundle.",
            "",
            "  ```",
            f"  git clone {BUNDLE_NAME} content-repo",
            "  ```",
        ]
    else:
        lines.append(f"- No `{BUNDLE_NAME}`: this instance's repository had no commits to bundle.")
    lines += [
        f"- `{FEEDBACK_NAME}` -- {votes} reader answer(s) to \"was this page helpful?\".",
        "  These live in the database rather than in the repository (an anonymous vote",
        "  must not become a commit), so a clone alone would not bring them back.",
        "",
        "## What is deliberately NOT in here",
        "",
        "The admin password hash, live sessions, API tokens and draft preview links.",
        "All four are credentials, and this file is made to be copied somewhere else.",
        "A restored instance asks whoever opens it to create an admin account, which",
        "is the right thing for it to do.",
        "",
        "## Restoring",
        "",
        "1. Start a DocuWaves instance with an empty `/data` volume.",
        f"2. Copy `{CONTENT_DIRNAME}/` over its content repository directory",
        "   (`CONTENT_REPO_PATH`, `/data/content-repo` by default) -- or clone the",
        "   bundle there instead, which also restores the history.",
        "3. Restart it. The database is only ever an index over those files and is",
        "   rebuilt from them at startup.",
        "",
        "The reverse also works without this app at all: the Markdown is the content.",
        "",
    ]
    return "\n".join(lines)


def build_archive(destination: Path) -> dict:
    """Writes the archive to `destination` and answers what went into it.

    Written to a real file rather than assembled in memory: a documentation
    repo with screenshots in it is tens of megabytes, and holding one in RAM
    per concurrent download is a way to lose the whole instance to a click.

    NOT a snapshot. Files are read one at a time while the instance keeps
    running, so an export taken during a save can catch the repo mid-write.
    In practice a save is one commit of a handful of files and an export is
    seconds long; the failure mode is one page in the archive being a
    version older or newer than its neighbours, which is worth knowing and
    not worth locking every write in the app to avoid."""
    root = Path(settings.content_repo_path)
    files = _content_files()
    votes = page_feedback_store.export_all()
    bundle = destination.parent / f"{destination.name}.bundle.tmp"
    has_history = _write_bundle(bundle)
    try:
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in files:
                archive.write(path, f"{CONTENT_DIRNAME}/{path.relative_to(root).as_posix()}")
            if has_history:
                archive.write(bundle, BUNDLE_NAME)
            archive.writestr(FEEDBACK_NAME, json.dumps(votes, indent=2, ensure_ascii=False))
            archive.writestr(READ_ME_NAME, _readme(has_history, len(votes)))
    finally:
        bundle.unlink(missing_ok=True)
    return {
        "files": len(files),
        "bytes": destination.stat().st_size,
        "feedback_votes": len(votes),
        "history": has_history,
    }
