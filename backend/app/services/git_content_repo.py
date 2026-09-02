"""Git operations for the content repo -- the local working clone under
CONTENT_REPO_PATH is the only thing every other content module (content_files.py,
content_sync.py, the *_store.py write paths) ever reads or writes; this module
is the sole place that talks to the actual `git` process (via GitPython) to
keep that clone in sync with its remote.

LOCAL BY DEFAULT, and that is the whole shape of this module. Everything the
rest of the app gets out of git -- a full history, diffs, attribution,
restore, "the database is only a rebuildable index" -- comes from there
BEING a repository, not from that repository being hosted somewhere. So an
instance with no CONTENT_REPO_URL is not an unconfigured instance: it gets a
real repository, initialised at CONTENT_REPO_PATH with a first commit, and
every write commits into it exactly as it would with a remote. Nothing
pushes, because there is nowhere to push. That is the only difference, and
it is why nobody has to create a repository and mint a token before this
application will do anything at all.

CONTENT_REPO_URL is what gives that repository a remote -- on day one, or a
year later. See _reconcile_remote() for what happens on the restart that
adds one, removes one again, or points at a repository whose history has
nothing to do with this instance's.

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

import logging
import os
import re
import shutil
import stat
import threading
from pathlib import Path

import git

from app.settings import settings

log = logging.getLogger("docuwaves")

_lock = threading.Lock()
_repo: git.Repo | None = None

# What this repository's remote turned out to be, as far as the last
# reconciliation could work out (see _reconcile_remote). Read by status() for
# the admin panel, by commit_and_push() to decide whether a push is even a
# meaningful thing to attempt, and by sync_pull().
LOCAL = "local"  # no CONTENT_REPO_URL: versioned here, pushed nowhere
REMOTE = "remote"  # a remote is configured and this working copy belongs to it
UNRELATED = "unrelated"  # a remote is configured whose history is not this one's

_mode: str = LOCAL
# Why the remote isn't usable right now, in the operator's words -- "" when
# there is nothing wrong. Never a reason to stop writing: a commit is a local
# act, and it is the commit that makes a write durable.
_remote_error: str = ""


class GitContentError(RuntimeError):
    pass


def has_remote() -> bool:
    """Whether the repository has anywhere to push.

    This replaces the module's old is_configured(), and the rename is the
    whole change in one line: that function answered "is a CONTENT_REPO_URL
    set", and every caller then used it to mean "is there a content repo at
    all" -- which is why an instance without one refused every write. There
    is now always a content repo, so the question worth asking is the
    narrower one this asks, and only the three things that genuinely need a
    remote ask it (pulling, the background sync job, the status panel)."""
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


def _set_mode(mode: str, error: str = "") -> None:
    global _mode, _remote_error
    _mode, _remote_error = mode, error


def ensure_clone() -> git.Repo:
    """The content repository, made if it isn't there yet. Idempotent: the
    first call creates it, every call after reuses it -- the working
    directory persists across app restarts via the same /data volume every
    other store's file lives under, so this happens once per install rather
    than once per request.

    "Made" is one of three things, and the caller never has to know which:
    a clone of CONTENT_REPO_URL, a bootstrap of that remote if it is still
    empty, or -- with no remote configured at all -- a plain `git init` right
    here. All three hand back a repository whose working tree is
    CONTENT_REPO_PATH, which is the only thing any caller ever wanted.

    Reuse does NOT pull: callers that need the latest upstream state call
    sync_pull() themselves (startup, the periodic task, "Sync now"). Pulling
    from in here would have to happen while _lock is held, and sync_pull()
    calls back into this function -- a plain Lock, so that deadlocks."""
    global _repo
    with _lock:
        if _repo is not None:
            return _repo

        path = Path(settings.content_repo_path)
        repo = _open_existing(path)
        if repo is not None:
            # Set BEFORE reconciling: the repository is usable from this
            # point on, and a remote that can't be reached (or shouldn't be
            # touched) must never be able to take the local content with it.
            _repo = repo
            # An existing working copy is the one case where the remote may
            # have CHANGED since it was made -- newly added, removed again,
            # re-pointed, or its token rotated.
            _reconcile_remote(repo)
            return repo

        path.parent.mkdir(parents=True, exist_ok=True)
        if not has_remote():
            _repo = _init_local(path)
            _set_mode(LOCAL)
            return _repo

        _repo = _clone_remote(path)
        _set_mode(REMOTE)
        return _repo


def _open_existing(path: Path) -> git.Repo | None:
    """The working copy already on disk, or None when there is none to open.

    A directory that is there but unusable is discarded ONLY when a remote
    can supply it again -- that rmtree exists for the partial directory a
    failed clone leaves behind (git creates the destination before it can
    fail), and re-cloning costs nothing. Without a remote the very same call
    would be deleting the only copy of the instance's content, so a
    local-only working copy is never thrown away: a repository that holds no
    commits yet is an interrupted first start and gets its first commit
    here, and anything worse is reported instead of cleaned up."""
    if not path.exists() or not (path / ".git").exists():
        return None

    try:
        repo = git.Repo(path)
        _configure_repo(repo)
    except Exception as exc:
        if has_remote():
            shutil.rmtree(path, ignore_errors=True)
            return None
        raise GitContentError(
            f"The content repository at {path} could not be opened ({exc}). No CONTENT_REPO_URL is set, so "
            f"this is the only copy of this instance's content -- it was left exactly as it is rather than "
            f"discarded. Check the volume."
        ) from exc

    try:
        _ = repo.head.commit  # touch it -- raises on a half-finished clone or an empty repository
    except Exception:
        if has_remote():
            shutil.rmtree(path, ignore_errors=True)
            return None
        _initial_commit(repo)
    return repo


def _init_local(path: Path) -> git.Repo:
    """A brand new repository in the data volume: the configured branch, one
    commit so that HEAD exists (every history read below asks for HEAD, and
    a repository with no commits has none), and no remote. No account, no
    token, no network."""
    path.mkdir(parents=True, exist_ok=True)
    repo = git.Repo.init(path, initial_branch=settings.content_repo_branch)
    _configure_repo(repo)
    _initial_commit(repo)
    return repo


def _initial_commit(repo: git.Repo) -> None:
    keep_file = Path(repo.working_tree_dir) / ".gitkeep"
    keep_file.write_text("")
    repo.index.add([".gitkeep"])
    repo.index.commit(
        "Initial commit (DocuWaves content repository)",
        author=git.Actor("DocuWaves", "docuwaves@local"),
    )


def _clone_remote(path: Path) -> git.Repo:
    env = _env()
    try:
        repo = git.Repo.clone_from(_authenticated_url(), path, branch=settings.content_repo_branch, env=env)
    except git.GitCommandError as exc:
        if "not found in upstream" in str(exc):
            # The remote repo exists but has no commits yet (a brand new,
            # genuinely empty content repo) -- clone_from can't check out a
            # branch that doesn't exist, so bootstrap it instead: init
            # locally on the configured branch, make an empty first commit,
            # push that as the branch's first ever commit.
            shutil.rmtree(path, ignore_errors=True)
            return _bootstrap_empty_remote(path, env)
        raise GitContentError(f"Could not clone the content repo: {exc}") from exc
    _configure_repo(repo)
    return repo


def _bootstrap_empty_remote(path: Path, env: dict) -> git.Repo:
    """An empty remote, filled in from scratch. Exactly the local repository
    _init_local() makes, plus an origin and the push that gives the remote
    its first commit -- which is the same two steps _adopt() takes for a
    local instance that gains a remote later, only with no history to carry
    across yet."""
    repo = _init_local(path)
    repo.create_remote("origin", _authenticated_url())
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


# What the operator is told when the configured remote turns out to hold a
# history that is not this instance's. Written out here rather than at the
# one place it is raised because three different surfaces say it: the admin
# panel (through status()), "Sync now" (as a 409), and the log.
_UNRELATED_MESSAGE = (
    "The configured content repo remote ({url}, branch '{branch}') holds a history with nothing in common "
    "with this instance's -- not a single shared commit. Nothing was pushed, pulled or overwritten: merging "
    "two unrelated histories produces a tree neither side wrote, and either side could only win by "
    "destroying the other. This instance keeps working exactly as a local one and every change is still "
    "committed to {path}; nothing reaches that remote until this is settled. Two ways out: point "
    "CONTENT_REPO_URL at an EMPTY repository instead, and this instance's full history is pushed to it on "
    "the next restart -- or, if the remote's content is the one you want to keep, delete this instance's "
    "working copy at {path} so it is cloned fresh, which discards everything in it."
)


def _reconcile_remote(repo: git.Repo) -> None:
    """Line an EXISTING working copy up with whatever CONTENT_REPO_URL says
    now. Called on every start and, while it hasn't concluded cleanly, again
    from sync_pull() -- because the remote is a setting, and settings change.

    Four outcomes, and not one of them may cost the local work:

    * No remote configured. Any leftover `origin` is removed: the operator
      went back to local, and dropping it also takes the token that was
      embedded in it back out of .git/config. Writes keep committing here.
    * A remote whose branch does not exist yet -- the ordinary "ran locally
      for months, just made an empty repository for it" case. THE LOCAL
      HISTORY IS PUSHED TO IT, whole. Not re-cloned over, not discarded: the
      commits that are here are the ones that belong there.
    * A remote whose branch shares an ancestor with ours: business as usual.
      Pulls merge and pushes push, exactly as on an instance that had the
      remote from day one -- plus a fast-forward of anything the remote is
      simply missing, so commits made during a spell without a working
      remote don't have to wait for the next edit to travel.
    * A remote whose branch shares NO ancestor with ours. Nothing automatic
      can be right: merging needs --allow-unrelated-histories and invents a
      tree neither side wrote, force-pushing destroys the remote, and
      re-cloning destroys the local content. So this does none of the three.
      The instance carries on as a local one, the remote is left untouched,
      and the reason -- with both ways out -- goes where the operator will
      actually meet it. See _UNRELATED_MESSAGE."""
    if not has_remote():
        try:
            repo.delete_remote("origin")
        except (ValueError, git.GitCommandError):
            pass  # there was none: a repository that has only ever been local
        _set_mode(LOCAL)
        return

    # The working copy stores whatever remote URL it was created with --
    # including the token that was embedded back then. Rotating
    # CONTENT_REPO_TOKEN (or moving the repo) would otherwise never reach an
    # existing clone, and every push would keep failing with the old, possibly
    # revoked credentials while fetches on a public repo silently kept
    # working. Re-point it on every start.
    try:
        repo.remote("origin").set_url(_authenticated_url())
    except (ValueError, git.GitCommandError):
        repo.create_remote("origin", _authenticated_url())

    branch = settings.content_repo_branch
    origin = repo.remote("origin")
    try:
        with repo.git.custom_environment(**_env()):
            # ls-remote rather than a fetch, because the two answers have to
            # be told apart: a branch that isn't there yet exits 0 with empty
            # output (which is the adopt case below), while `fetch <branch>`
            # fails the same way for an absent branch as for an unreachable
            # host.
            listed = repo.git.ls_remote("--heads", "origin", branch)
    except git.GitCommandError as exc:
        _set_mode(REMOTE, f"Could not reach the content repo's remote: {exc}")
        return

    if not listed.strip():
        # The branch isn't there at all -- the whole local history becomes
        # the remote's, and that push is also what establishes tracking.
        _push_local_history(repo, origin, branch, set_upstream=True)
        return

    try:
        with repo.git.custom_environment(**_env()):
            origin.fetch(branch)
    except git.GitCommandError as exc:
        _set_mode(REMOTE, f"Could not fetch from the content repo's remote: {exc}")
        return

    try:
        # merge-base exits non-zero with no output when the two commits share
        # no ancestor at all -- which is the entire question being asked here.
        repo.git.merge_base(repo.head.commit.hexsha, "FETCH_HEAD")
    except git.GitCommandError:
        message = _UNRELATED_MESSAGE.format(
            url=settings.content_repo_url, branch=branch, path=settings.content_repo_path
        )
        # Only on the way IN to this state: sync_pull() re-runs this whole
        # function every time it is called while the remote hasn't settled,
        # and repeating a paragraph every five minutes buries the log it is
        # supposed to be findable in.
        if _mode != UNRELATED:
            log.warning("%s", message)
        _set_mode(UNRELATED, message)
        return

    _set_tracking(repo, branch)
    _set_mode(REMOTE)
    if _is_behind(repo):
        _push_local_history(repo, origin, branch, set_upstream=False)


def _is_behind(repo: git.Repo) -> bool:
    """Whether the remote's tip is an ANCESTOR of ours -- it is missing
    commits we have, and handing them over would fast-forward it rather than
    rewrite anything. False both for "in step" and for "diverged"."""
    try:
        remote_head = repo.git.rev_parse("FETCH_HEAD").strip()
        if remote_head == repo.head.commit.hexsha:
            return False
        repo.git.merge_base("--is-ancestor", remote_head, repo.head.commit.hexsha)
    except git.GitCommandError:
        return False
    return True


def _push_local_history(repo: git.Repo, origin, branch: str, set_upstream: bool) -> None:
    """Commits this instance holds and the remote does not, handed over.

    Two callers, one act, and it is the point of the whole local-first
    arrangement: months of local commits are what a newly configured remote
    gets, in full, rather than being flattened into a single import commit
    or lost to a fresh clone. A remote that does not have this branch at all
    gets the entire history and the tracking relationship with it; a remote
    that has the branch but sits strictly behind ours (the same instance one
    restart later, or after a spell where the remote was unreachable) gets
    the difference as a plain fast-forward.

    Never a force, and never onto a diverged branch -- a remote that has
    moved on independently is the ordinary pull-then-push case that
    sync_pull() and _push_with_retry() already handle."""
    try:
        with repo.git.custom_environment(**_env()):
            # An explicit `local:remote` refspec, not a bare branch name: the
            # local branch was named by CONTENT_REPO_BRANCH as it stood when
            # the repository was initialised, and the operator may well have
            # changed that in the same edit that added the remote.
            results = origin.push(f"{repo.head.ref.name}:{branch}", set_upstream=set_upstream)
        if any(r.flags & r.ERROR for r in results):
            raise git.GitCommandError("push", 1, str([r.summary for r in results]))
    except git.GitCommandError as exc:
        _set_mode(
            REMOTE,
            f"This instance's existing content history could not be pushed to the configured remote: {exc}. "
            f"Nothing was lost -- it is all still committed in {settings.content_repo_path}; 'Sync now' or a "
            f"restart tries again.",
        )
        log.warning("Could not push the existing content history to the configured remote: %s", exc)
        return
    log.info("Pushed this instance's content history to %s (branch %s).", settings.content_repo_url, branch)
    _set_mode(REMOTE)


def _set_tracking(repo: git.Repo, branch: str) -> None:
    """`origin.push()` and `origin.pull()` with no refspec (which is how
    _push_with_retry and sync_pull call them) need the checked-out branch to
    have an upstream. A clone comes with one; a working copy that was local
    until this restart does not, and _adopt()'s push is not the only way it
    can gain a remote -- an operator can point one at a repository that
    already holds this same history."""
    try:
        repo.git.branch("--set-upstream-to", f"origin/{branch}", repo.head.ref.name)
    except git.GitCommandError as exc:
        log.warning("Could not set the upstream branch for %s: %s", branch, exc)


def sync_pull() -> None:
    """Fetch + merge the configured branch -- used by both the manual 'sync
    now' button and the periodic background job. Raises GitContentError on
    any failure (network, or a real merge conflict against uncommitted
    local... which shouldn't exist between writes, since every write path
    below commits+pushes immediately, but a conflict against the remote's
    own history is still possible if two DocuWaves instances somehow shared
    one repo -- not a supported setup, but fails loudly rather than
    corrupting the clone if it happens).

    A local-only instance has nothing to fetch -- there is no second copy of
    this content anywhere -- so this returns quietly instead of failing:
    both callers run on every instance, and neither has anything useful to
    do with an error that only means "you have no remote"."""
    repo = ensure_clone()
    if not has_remote():
        return
    with _lock:
        if _mode != REMOTE or _remote_error:
            # The last attempt didn't conclude cleanly (unreachable host, a
            # push that didn't get through, an unrelated remote). Retry it:
            # this is exactly the call an operator makes after fixing it.
            _reconcile_remote(repo)
        if _mode == UNRELATED:
            # A pull here would need --allow-unrelated-histories, which is
            # the one thing that must not happen silently.
            raise GitContentError(_remote_error)
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
    than left to the caller to get right.

    "...and push" only when there is a remote to push to and it is one this
    working copy belongs to. On a local instance, and on one whose remote
    turned out to be unrelated (see _reconcile_remote), the write is
    COMPLETE at the commit: it is in the repository, in the history, in the
    diff, and restorable. Nothing about it is pending."""
    repo = ensure_clone()
    with _lock:
        repo.index.add([p for p in paths if (Path(repo.working_tree_dir) / p).exists()])
        missing = [p for p in paths if not (Path(repo.working_tree_dir) / p).exists()]
        if missing:
            repo.index.remove(missing, working_tree=False)

        if not repo.is_dirty(index=True, working_tree=False) and not repo.untracked_files:
            return  # nothing actually changed (e.g. re-saving identical content)

        repo.index.commit(message, author=_actor(author_name), committer=git.Actor("DocuWaves", "docuwaves@local"))

        if _mode == REMOTE:
            _push_with_retry(repo)


def _push_with_retry(repo: git.Repo) -> None:
    with repo.git.custom_environment(**_env()):
        origin = repo.remote("origin")
        try:
            results = origin.push()
        except git.GitCommandError as exc:
            # A REJECTED push comes back as ERROR-flagged results, which the
            # retry below handles. An UNREACHABLE remote raises instead --
            # and nothing caught it, so a save answered 500 with a traceback
            # while the commit had in fact succeeded locally. The operator
            # saw a crash and had no way to tell whether their work was
            # safe. It is: the commit is the durable act, the push is not.
            raise GitContentError(
                f"Your change was committed locally but could not be pushed to the content repo "
                f"({exc}). Nothing is lost -- it will go out with the next successful push, or "
                f"immediately when you use 'Sync now' once the remote is reachable again."
            ) from exc
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
    """For the admin 'content repo' panel -- never raises, a problem here is
    data to display, not an exception to propagate.

    `mode` is what the panel actually reads: "local" (versioned here, no
    remote -- a complete state, not a broken one), "remote", or "unrelated".
    `connected` is kept, and is strictly about a REMOTE being reachable, so
    it is false on a local instance; that is not a failure and `mode` is
    what says so."""
    try:
        repo = ensure_clone()
        head = repo.head.commit
        last_commit = {
            "sha": head.hexsha[:8],
            "message": head.message.strip().splitlines()[0],
            "date": head.committed_datetime.isoformat(),
        }
    except (GitContentError, ValueError, git.GitError) as exc:
        return {
            "configured": True,
            "mode": _mode,
            "has_remote": has_remote(),
            "connected": False,
            "branch": settings.content_repo_branch,
            "last_commit": None,
            "error": str(exc),
        }
    return {
        "configured": True,
        "mode": _mode,
        "has_remote": has_remote(),
        "connected": _mode == REMOTE and not _remote_error,
        "branch": settings.content_repo_branch,
        "last_commit": last_commit,
        "error": _remote_error or None,
    }


# ---- History (read-only) ----
#
# Every function below answers a question about ONE file, addressed by its
# path relative to the repo root -- exactly the form content_files' write
# functions already return and commit_and_push() already stages, so nothing
# else has to learn a second way of naming a file.
#
# None of them raises. A history panel with nothing in it and a page with no
# "last updated" line are both perfectly good answers for a clone that hasn't
# happened yet, a repo with no commits, or a file git has simply never seen --
# and all three are ordinary states, not failures worth a 500 on a public page
# view. What is NOT one of those cases any more is "no content repo": a local
# instance has a real repository, so its pages have real histories.

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
    """The repository, for a read that must never fail loudly -- None when
    there is nothing to read: no working copy (or one that can't be made
    right now), or a repo that holds no commits at all."""
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
