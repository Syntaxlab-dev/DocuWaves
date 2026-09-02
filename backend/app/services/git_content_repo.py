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

Reading HISTORY (the bottom half of this module) is the other side of the
same fact: every page is a file in this repo, so a complete, attributed
history of every page already exists and only needs surfacing. Those
functions are strictly READ-ONLY -- `git log` and `git show`, nothing that
checks anything out, resets, reverts or rewrites. Putting an old version
back is not done here at all: pages_store.restore_page() reads the old bytes
through file_at() and then goes through the ordinary write path above, so a
restore is a NEW commit on top and the history it came from stays intact.
"""

import os
import re
import shutil
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
    """Idempotent: clones on first call, reuses the existing clone on every
    call after -- the working directory persists across app restarts via the
    same /data volume every other store's file lives under, so a fresh clone
    only happens once per install, not once per request.

    Reuse does NOT pull: callers that need the latest upstream state call
    sync_pull() themselves (startup, the periodic task, "Sync now"). Pulling
    from in here would have to happen while _lock is held, and sync_pull()
    calls back into this function -- a plain Lock, so that deadlocks."""
    global _repo
    if not is_configured():
        raise GitContentError("No content repo configured (CONTENT_REPO_URL is not set).")

    with _lock:
        path = Path(settings.content_repo_path)
        env = _env()
        if _repo is not None:
            return _repo

        if path.exists() and (path / ".git").exists():
            try:
                repo = git.Repo(path)
                _ = repo.head.commit  # touch it -- raises if this is a half-finished/corrupt clone
                _configure_repo(repo)
                # The clone stores whatever remote URL it was created with --
                # including the token that was embedded back then. Rotating
                # CONTENT_REPO_TOKEN (or moving the repo) would otherwise never
                # reach an existing clone, and every push would keep failing
                # with the old, possibly revoked credentials while fetches on a
                # public repo silently kept working. Re-point it on every start.
                try:
                    repo.remote("origin").set_url(_authenticated_url())
                except (ValueError, git.GitCommandError):
                    pass  # no origin (locally bootstrapped, never pushed) -- nothing to re-point
                _repo = repo
                return repo
            except Exception:
                # A previous clone attempt left a partial/broken directory
                # behind (git creates the destination before it can fail,
                # e.g. on the "branch doesn't exist yet" case below) --
                # discard it and start over rather than getting stuck
                # forever on the leftover.
                shutil.rmtree(path, ignore_errors=True)

        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            repo = git.Repo.clone_from(_authenticated_url(), path, branch=settings.content_repo_branch, env=env)
        except git.GitCommandError as exc:
            if "not found in upstream" in str(exc):
                # The remote repo exists but has no commits yet (a brand
                # new, genuinely empty content repo) -- clone_from can't
                # check out a branch that doesn't exist, so bootstrap it
                # instead: init locally on the configured branch, make an
                # empty first commit, push that as the branch's first ever
                # commit.
                shutil.rmtree(path, ignore_errors=True)
                _repo = _bootstrap_empty_remote(path, env)
                return _repo
            raise GitContentError(f"Could not clone the content repo: {exc}") from exc
        _configure_repo(repo)
        _repo = repo
        return repo


def _bootstrap_empty_remote(path: Path, env: dict) -> git.Repo:
    path.mkdir(parents=True, exist_ok=True)
    repo = git.Repo.init(path, initial_branch=settings.content_repo_branch)
    repo.create_remote("origin", _authenticated_url())
    _configure_repo(repo)
    keep_file = path / ".gitkeep"
    keep_file.write_text("")
    repo.index.add([".gitkeep"])
    repo.index.commit(
        "Initial commit (DocuWaves content repo bootstrap)",
        author=git.Actor("DocuWaves", "docuwaves@local"),
    )
    try:
        with repo.git.custom_environment(**env):
            # set_upstream=True: without it, this first push has nothing to
            # establish the branch's tracking relationship, and every LATER
            # plain `origin.push()` elsewhere in this module (no explicit
            # refspec) fails with "has no upstream branch" -- found by this
            # module's own end-to-end test against a genuinely empty repo.
            push_info = repo.remote("origin").push(settings.content_repo_branch, set_upstream=True)
            if any(r.flags & r.ERROR for r in push_info):
                raise git.GitCommandError("push", 1, str([r.summary for r in push_info]))
    except git.GitCommandError as exc:
        raise GitContentError(f"Could not initialize the empty content repo: {exc}") from exc
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


def _actor(author_name: str) -> git.Actor:
    """The git author for a write. `author_name` is whatever the write path
    passes: the logged-in admin's username for an admin write, and
    "Claude (API token: <name>)" for one made through the MCP endpoint (see
    api_tokens_store.author_name), so `git log` names exactly who -- or
    what -- changed a page.

    The email is DERIVED from the name rather than interpolated into it. It
    used to be f"{author_name}@local", which was fine while every author was
    a one-word username and produces "Claude (API token: notes-bot)@local"
    -- spaces, parentheses and a colon inside an address -- the moment one
    isn't. Git stores that verbatim and every tool downstream then has to
    cope with an address that is not one. Lowercased with runs of anything
    non-alphanumeric collapsed to a dash, so a plain username like `admin`
    still gets exactly the `admin@local` it always got."""
    name = author_name or "DocuWaves"
    local = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "docuwaves"
    return git.Actor(name, f"{local}@local")


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

        repo.index.commit(message, author=_actor(author_name), committer=git.Actor("DocuWaves", "docuwaves@local"))

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


# ---- History (read-only) ----
#
# Every function below answers a question about ONE file, addressed by its
# path relative to the repo root -- exactly the form content_files' write
# functions already return and commit_and_push() already stages, so nothing
# else has to learn a second way of naming a file.
#
# None of them raises. A history panel with nothing in it and a page with no
# "last updated" line are both perfectly good answers for an instance with no
# content repo, a clone that hasn't happened yet, a repo with no commits, or a
# file git has simply never seen -- and all four are ordinary states, not
# failures worth a 500 on a public page view.

# A page's history is a list a person reads, not a log to page through: past a
# few dozen entries nobody is scrolling. `limit` reaches page_history() from a
# query parameter, so it is capped here rather than trusted -- MAX_HISTORY is
# also how far back a restore can reach (see pages_store._history_entry),
# which is why the two are one number.
MAX_HISTORY = 100
DEFAULT_HISTORY = 25

# A commit-ish that arrived from a URL. Checked before it is ever handed to
# git, because everything after this point interpolates it into an argument:
# a bare hex abbreviation cannot be read as an option (`--upload-pack=...`),
# as a path, or as anything but a commit.
_SHA_RE = re.compile(r"^[0-9a-f]{4,40}$")

# One record per commit, one field per value. \x1e and \x1f cannot occur in a
# sha, an author name, an ISO date or a commit subject, so the output parses
# without having to guess where a multi-word subject ends -- unlike any
# separator a person might reasonably type into a commit message.
_LOG_FORMAT = "%x1e%h%x1f%an%x1f%aI%x1f%s"

# `git log` walks commit objects, and both the admin history panel and the
# public "last updated" line ask for one PER REQUEST. Neither answer can
# change while HEAD stands still, so both are memoized against HEAD's sha and
# the whole cache is dropped the moment a commit or a pull moves it. A page
# view on an unchanged repo therefore costs a dict lookup; the first one after
# a commit costs exactly one git call again.
#
# Not locked: these are plain dict operations, so the worst a race can do is
# compute the same read-only answer twice. Taking _lock here would instead put
# every public page view behind whatever write is in flight.
_read_cache: dict[tuple, object] = {}
_read_cache_head: str | None = None

# One entry per (file, question) and a repo can hold a great many files. The
# whole thing is dropped rather than one entry evicted, which keeps this a
# dict instead of a cache library: the next few requests pay one git call each
# and it fills back up.
_READ_CACHE_MAX = 2000


def _read_repo() -> git.Repo | None:
    """The clone, for a read that must never fail loudly -- None when there is
    nothing to read: no content repo configured, no clone (or a clone that
    can't be made right now), or a repo that holds no commits at all."""
    if not is_configured():
        return None
    try:
        repo = ensure_clone()
        _ = repo.head.commit  # an initialized but commit-less repo has no history to read
        return repo
    except (GitContentError, ValueError, git.GitError):
        return None


def _cached(repo: git.Repo, key: tuple, compute):
    global _read_cache_head
    head = repo.head.commit.hexsha
    if head != _read_cache_head:
        _read_cache.clear()
        _read_cache_head = head
    if key in _read_cache:
        return _read_cache[key]
    value = compute()
    if len(_read_cache) >= _READ_CACHE_MAX:
        _read_cache.clear()
    _read_cache[key] = value
    return value


def _name_status(block: str) -> dict:
    """The file line `--name-status` printed for one commit, as the path the
    file had AT that commit plus (on the commit that did it) the name it had
    before.

    --follow restricts the diff to the one file being followed, so there is
    exactly one line, and on a rename it reads `R100<TAB>old<TAB>new`. That
    line is the only place the old name is recorded, which makes it the only
    way the history can say "this commit moved the page" rather than showing
    a mystery gap where the file appears to start over."""
    for line in block.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0]:
            continue
        status = parts[0][0]
        if status == "R" and len(parts) >= 3:
            return {"status": status, "path": parts[2], "renamed_from": parts[1]}
        return {"status": status, "path": parts[1], "renamed_from": ""}
    return {"status": "", "path": "", "renamed_from": ""}


def page_history(path: str, limit: int = DEFAULT_HISTORY) -> list[dict]:
    """The commits that touched this file, newest first: short sha, author
    name, ISO date, subject -- plus the path the file had at that commit and
    the name it was renamed from, if that is what the commit did.

    --follow, so the history SPANS A RENAME. A page rename moves its file
    (content_files.relocate_page), and without --follow the log would stop
    dead at the move and claim the page began life on the day it was renamed.
    That is also why each entry carries its own `path`: an older commit
    doesn't have this file under today's name, so reading that version back
    has to ask for the name it had then (see file_at)."""
    repo = _read_repo()
    if repo is None or not path:
        return []
    count = max(1, min(int(limit or DEFAULT_HISTORY), MAX_HISTORY))
    return _cached(repo, ("history", path, count), lambda: _page_history(repo, path, count))


def _page_history(repo: git.Repo, path: str, count: int) -> list[dict]:
    try:
        output = repo.git.log(
            f"--max-count={count}",
            "--follow",
            "--name-status",
            f"--format={_LOG_FORMAT}",
            "--no-color",
            "--",
            path,
        )
    except git.GitCommandError:
        return []

    entries: list[dict] = []
    for record in output.split("\x1e"):
        if not record.strip():
            continue
        header, _, names = record.strip("\n").partition("\n")
        fields = header.split("\x1f")
        if len(fields) < 4:
            continue
        parsed = _name_status(names)
        entries.append(
            {
                "sha": fields[0],
                "author": fields[1],
                "date": fields[2],
                "subject": fields[3],
                # A commit whose file line we couldn't read at all falls back
                # to the name the file has today -- the only other name there
                # is, and right for every commit since the last rename.
                "path": parsed["path"] or path,
                "renamed_from": parsed["renamed_from"],
                "status": parsed["status"],
            }
        )
    return entries


def file_at(path: str, sha: str) -> str | None:
    """This file's full contents at `sha` -- frontmatter and body, exactly the
    bytes that were committed. None when the commit or the path isn't there.

    `path` is the name the file had AT that commit (page_history()'s own
    `path` field), not necessarily its name today: a page renamed since simply
    does not exist under today's name back then, and asking for it there is a
    git error rather than an older version of anything."""
    repo = _read_repo()
    if repo is None or not path or not _SHA_RE.match(sha or ""):
        return None
    try:
        # strip_newline_in_stdout=False: GitPython trims a trailing newline
        # from command output by default, and here the output IS the file --
        # every text file this app writes ends in one.
        return repo.git.show(f"{sha}:{path}", strip_newline_in_stdout=False)
    except git.GitCommandError:
        return None


def diff(path: str, sha: str) -> str:
    """What `sha` did to this file, as a unified diff. "" when git has nothing
    to say about it.

    `git log -1 --patch <sha>` rather than `git show <sha>`, for one reason:
    pathspec-limiting a `git show` throws away the other half of a rename
    before rename detection runs, so the commit that moved a page renders as
    a brand-new file with every line added. Following the file instead makes
    that same commit read as `rename from`/`rename to` with only the real
    change in the hunks.

    The FIRST commit for a file has no predecessor, and needs no special case
    here: its diff is the whole file as additions, which is what git says and
    what actually happened. Callers tell that case apart by the entry's
    `status` being "A"."""
    repo = _read_repo()
    if repo is None or not path or not _SHA_RE.match(sha or ""):
        return ""
    try:
        return repo.git.log(
            "-1",
            "--patch",
            "--follow",
            "--no-color",
            "--format=",
            sha,
            "--",
            path,
            strip_newline_in_stdout=False,
        )
    except git.GitCommandError:
        return ""


def last_modified(path: str) -> str:
    """The ISO date of the newest commit touching this file, or "" when that
    isn't knowable. This is what the public site's "last updated" line is
    built from -- and it is a git fact rather than a database one on purpose,
    see pages_store.last_updated().

    No --follow here, deliberately: the newest commit touching the file under
    its CURRENT name is at or after the rename that gave it that name, so
    following the rename cannot turn up a newer one and would only pay git for
    rename detection on the path of every page view."""
    repo = _read_repo()
    if repo is None or not path:
        return ""
    return _cached(repo, ("last_modified", path), lambda: _last_modified(repo, path))


def _last_modified(repo: git.Repo, path: str) -> str:
    try:
        # A path git has never seen is not an error: `git log` exits 0 with no
        # output, which is exactly the "" this returns.
        return repo.git.log("-1", "--format=%aI", "--", path).strip()
    except git.GitCommandError:
        return ""


# The marker that tells a date line apart from a filename in the walk below.
# \x01 can't begin a path (git would have to quote it, and quoting is turned
# off), so the parse needs no heuristics.
_LOG_MARKER = "\x01"


def last_modified_map() -> dict[str, str]:
    """`{repo-relative path: ISO timestamp}` for every file the history has
    touched, in ONE git invocation.

    This exists for the sitemap, which needs a date for every published page
    at once. last_modified() above is a `git log -1` per file, which is right
    on a page view (one file, and the answer is then cached) and wrong here:
    an instance with a thousand pages would spawn a thousand git processes to
    build one document, on a URL a crawler is free to request whenever it
    likes.

    One `git log --name-only` walks the whole history instead, newest commit
    first, so the FIRST time a path appears is its newest change -- setdefault
    is the entire algorithm. Cached by HEAD like every other read here, so the
    walk happens once per commit rather than once per request, and an empty
    dict is a perfectly ordinary answer (no repo, no commits, nothing
    committed yet)."""
    repo = _read_repo()
    if repo is None:
        return {}
    return _cached(repo, ("last_modified_map",), lambda: _last_modified_map(repo))


def _last_modified_map(repo: git.Repo) -> dict[str, str]:
    try:
        # core.quotePath=false: git otherwise C-quotes any path with a
        # non-ASCII byte in it ("caf\303\251.md"), which would never match
        # the real path and would silently cost those pages their lastmod.
        # --no-renames: rename detection is pure cost here -- a renamed file
        # is listed under the name it has now either way, which is the name
        # being looked up.
        output = repo.git.execute(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "log",
                f"--pretty=format:{_LOG_MARKER}%aI",
                "--name-only",
                "--no-renames",
            ],
        )
    except git.GitCommandError:
        return {}

    dates: dict[str, str] = {}
    current = ""
    for line in output.splitlines():
        if line.startswith(_LOG_MARKER):
            current = line[1:].strip()
        elif line and current:
            dates.setdefault(line, current)
    return dates
