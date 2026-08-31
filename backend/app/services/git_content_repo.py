"""Git operations for the content repo -- the local working clone under
CONTENT_REPO_PATH is the only thing every other content module (content_files.py,
content_sync.py, the *_store.py write paths) ever reads or writes; this module
is the sole place that talks to the actual `git` process (via GitPython) to
keep that clone in sync with its remote.

Auth: either an HTTPS URL + CONTENT_REPO_TOKEN (embedded into the remote URL
the same way CachePanel/DocuWaves' own CI embeds a token for a push, never
logged) or an SSH URL + CONTENT_REPO_SSH_KEY (written to a private key file
under /data with 0600 permissions, referenced via GIT_SSH_COMMAND). Exactly
one of the two is expected depending on CONTENT_REPO_URL's scheme.

Conflict handling (see this module's own test notes / commit message for how
this was verified against a real bare repo): a plain `git pull` on a modern
git refuses outright on diverged branches unless a reconciliation strategy is
configured -- `pull.rebase=false` is set once per clone so pulls always merge
(never rewrite the commit this process just made, which a rebase would).
Writing here always follows write -> commit -> push; if push is rejected
(remote has commits we don't), the sequence is pull (merge) -> push again.
If the merge itself conflicts (same file touched on both sides -- unlikely
given one file per project/category/page, but possible), the merge is
aborted immediately (never left half-merged) and a clear GitContentError is
raised instead of silently picking a side or losing content.
"""

import os
import stat
import threading
from pathlib import Path

import git

from app.settings import settings

_lock = threading.Lock()
_repo: git.Repo | None = None


class GitContentError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.content_repo_url)


def _ssh_key_path() -> Path:
    return Path(settings.content_repo_path).parent / "content_repo_ssh_key"


def _authenticated_url() -> str:
    url = settings.content_repo_url
    if url.startswith("https://") and settings.content_repo_token:
        # Token embedded directly in the URL -- the standard HTTPS PAT push
        # mechanism (same approach this project's own CI/deploy tooling
        # uses), scheme://<token>@host/... . Never logged: callers of this
        # module only ever see GitContentError messages, which are built
        # from git's own stderr -- git itself redacts credentials embedded
        # in a remote URL from its own error output.
        return url.replace("https://", f"https://{settings.content_repo_token}@", 1)
    return url


def _env() -> dict:
    env = dict(os.environ)
    if settings.content_repo_url.startswith("git@") or settings.content_repo_url.startswith("ssh://"):
        if settings.content_repo_ssh_key:
            key_path = _ssh_key_path()
            if not key_path.exists():
                key_path.parent.mkdir(parents=True, exist_ok=True)
                key_path.write_text(settings.content_repo_ssh_key.rstrip("\n") + "\n", encoding="utf-8")
                key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            env["GIT_SSH_COMMAND"] = f"ssh -i {key_path} -o StrictHostKeyChecking=accept-new"
    return env


def _configure_repo(repo: git.Repo) -> None:
    with repo.config_writer() as cw:
        cw.set_value("pull", "rebase", "false")
        cw.set_value("user", "name", "DocuWaves")
        cw.set_value("user", "email", "docuwaves@local")


def ensure_clone() -> git.Repo:
    """Idempotent: clones on first call, reuses the existing clone (after a
    pull) on every call after -- the working directory persists across app
    restarts via the same /data volume every other store's file lives under,
    so a fresh clone only happens once per install, not once per request."""
    global _repo
    if not is_configured():
        raise GitContentError("No content repo configured (CONTENT_REPO_URL is not set).")

    with _lock:
        path = Path(settings.content_repo_path)
        env = _env()
        if _repo is not None:
            return _repo
        if path.exists() and (path / ".git").exists():
            repo = git.Repo(path)
            _configure_repo(repo)
            _repo = repo
            return repo

        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            repo = git.Repo.clone_from(_authenticated_url(), path, branch=settings.content_repo_branch, env=env)
        except git.GitCommandError as exc:
            raise GitContentError(f"Could not clone the content repo: {exc}") from exc
        _configure_repo(repo)
        _repo = repo
        return repo


def sync_pull() -> None:
    """Fetch + merge the configured branch -- used by both the manual 'sync
    now' button and the periodic background job. Raises GitContentError on
    any failure (network, or a real merge conflict against uncommitted
    local... which shouldn't exist between writes, since every write path
    below commits+pushes immediately, but a conflict against the remote's
    own history is still possible if two DocuWaves instances somehow shared
    one repo -- not a supported setup, but fails loudly rather than
    corrupting the clone if it happens)."""
    repo = ensure_clone()
    with _lock:
        try:
            with repo.git.custom_environment(**_env()):
                repo.remote("origin").pull()
        except git.GitCommandError as exc:
            try:
                repo.git.merge("--abort")
            except git.GitCommandError:
                pass
            raise GitContentError(f"Could not sync with the content repo: {exc}") from exc


def commit_and_push(paths: list[str], message: str, author_name: str) -> None:
    """Stages exactly `paths` (relative to the repo root). A path that still
    exists on disk is staged normally via `index.add`; a path that's gone
    (the caller just deleted a page/category/project directory) is staged
    as a deletion via `index.remove` instead -- `index.add` on a path that
    no longer exists on disk raises, so the two cases are split here rather
    than left to the caller to get right."""
    repo = ensure_clone()
    with _lock:
        repo.index.add([p for p in paths if (Path(repo.working_tree_dir) / p).exists()])
        missing = [p for p in paths if not (Path(repo.working_tree_dir) / p).exists()]
        if missing:
            repo.index.remove(missing, working_tree=False)

        if not repo.is_dirty(index=True, working_tree=False) and not repo.untracked_files:
            return  # nothing actually changed (e.g. re-saving identical content)

        actor = git.Actor(author_name or "DocuWaves", f"{author_name or 'docuwaves'}@local")
        repo.index.commit(message, author=actor, committer=git.Actor("DocuWaves", "docuwaves@local"))

        _push_with_retry(repo)


def _push_with_retry(repo: git.Repo) -> None:
    with repo.git.custom_environment(**_env()):
        origin = repo.remote("origin")
        results = origin.push()
        if not any(r.flags & r.ERROR for r in results):
            return

        # Rejected -- remote has commits we don't. Pull (merge) once, then
        # retry the push exactly once. Two independent failure classes from
        # here on, both surfaced as GitContentError:
        try:
            origin.pull()
        except git.GitCommandError as exc:
            try:
                repo.git.merge("--abort")
            except git.GitCommandError:
                pass
            raise GitContentError(
                f"Your change was saved locally but conflicts with a newer version in the content repo "
                f"(same file changed on both sides). It was NOT pushed -- resolve the conflict manually "
                f"in the repo, then use 'Sync now'. Details: {exc}"
            ) from exc

        results2 = origin.push()
        if any(r.flags & r.ERROR for r in results2):
            raise GitContentError(
                "Your change was committed locally but could not be pushed to the content repo "
                "(pushed again after syncing, still rejected). Try 'Sync now' and saving again."
            )


def status() -> dict:
    """For the admin 'content repo connection' panel -- never raises, a
    connection problem is data to display, not an exception to propagate."""
    if not is_configured():
        return {"configured": False, "connected": False, "branch": None, "last_commit": None, "error": None}
    try:
        repo = ensure_clone()
        head = repo.head.commit
        return {
            "configured": True,
            "connected": True,
            "branch": settings.content_repo_branch,
            "last_commit": {"sha": head.hexsha[:8], "message": head.message.strip().splitlines()[0], "date": head.committed_datetime.isoformat()},
            "error": None,
        }
    except GitContentError as exc:
        return {"configured": True, "connected": False, "branch": settings.content_repo_branch, "last_commit": None, "error": str(exc)}
