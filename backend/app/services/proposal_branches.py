"""Proposed changes as Git branches (REVIEW_BRANCHES=on).

In a project that needs approval, an edit of a live page is kept as a
proposal in `<category>/_pending/<page>.md` until a reviewer approves it
(services/page_review.py). That stays the one source of truth. This module
only MIRRORS each proposal as a branch, so a team that already reviews in
GitHub or GitLab can see it there as an ordinary diff and open a pull
request for it:

    docuwaves/proposal/<project>/[<version>/]<category>/<page>[.<lang>]

The branch is one commit on top of the commit that wrote the proposal. It
changes the live page to the proposed title and text and removes the
`_pending/` file, so merging it does exactly what "Approve" does to the
text. Nothing in the working tree is touched: the commit is built in a
temporary index.

Every proposal write goes through git_content_repo.commit_and_push(), which
calls mirror() with the paths it just committed: a `_pending/` file that
exists afterwards gets its branch (re)written and force-pushed, one that is
gone (approved, discarded, moved) gets its branch deleted, locally and on
the remote. A branch is a convenience, never the record, so a failure here
is logged and the save it belongs to stands."""

import logging
import os
import re
import tempfile

import frontmatter
import git

from app.services import site_languages
from app.settings import settings

log = logging.getLogger("docuwaves")

PREFIX = "docuwaves/proposal/"
_PENDING = "_pending"


def enabled() -> bool:
    return settings.review_branches


def branch_name(pending_path: str) -> str | None:
    """The branch for a `_pending/` file, or None when the path is not one.
    `content/proj/guide/_pending/install.de.md` -> `docuwaves/proposal/proj/guide/install.de`."""
    parts = pending_path.split("/")
    if len(parts) < 3 or parts[-2] != _PENDING or not parts[-1].endswith(".md"):
        return None
    parts = parts[1:] if parts[0] == site_languages.CONTENT_DIRNAME else parts
    name = "/".join(parts[:-2] + [parts[-1][: -len(".md")]])
    # Slugs are already ref-safe; this only guards hand-written file names.
    name = re.sub(r"[^A-Za-z0-9._/-]+", "-", name)
    name = re.sub(r"\.\.+", ".", name)
    name = "/".join(p.strip(".") or "-" for p in name.split("/"))
    if name.endswith(".lock"):
        name = name[: -len(".lock")] + "-lock"
    return PREFIX + name


def live_path(repo: git.Repo, head: str, pending_path: str) -> str | None:
    """The live file a proposal replaces, as it is in `head`: the same file
    name one directory up, or the unsuffixed `<slug>.md` an older repo uses
    for the default language (content_files._page_paths)."""
    directory, name = pending_path.rsplit("/", 1)
    parent = directory.rsplit("/", 1)[0]
    candidates = [f"{parent}/{name}"]
    stem = name[: -len(".md")]
    if "." in stem:
        candidates.append(f"{parent}/{stem.split('.', 1)[0]}.md")
    for candidate in candidates:
        try:
            repo.git.cat_file("-e", f"{head}:{candidate}")
            return candidate
        except git.GitCommandError:
            continue
    return None


def _proposed_file(live_text: str, pending_text: str) -> str:
    """The live file with the proposed title and body: everything else in
    its frontmatter (order, published, review notes) stays as it is."""
    live = frontmatter.loads(live_text)
    proposal = frontmatter.loads(pending_text)
    live.content = proposal.content
    if proposal.metadata.get("title"):
        live.metadata["title"] = proposal.metadata["title"]
    return frontmatter.dumps(live) + "\n"


def _ref_exists(repo: git.Repo, branch: str) -> bool:
    try:
        repo.git.rev_parse("--verify", "--quiet", f"refs/heads/{branch}")
        return True
    except git.GitCommandError:
        return False


def _write_branch(repo: git.Repo, pending_path: str, branch: str, actor: git.Actor) -> bool:
    head = repo.git.rev_parse("HEAD")
    target = live_path(repo, head, pending_path)
    if target is None:
        return False  # a proposal for a page that is not live (yet): nothing to diff against
    live_text = repo.git.show(f"{head}:{target}")
    pending_text = repo.git.show(f"{head}:{pending_path}")
    title = str(frontmatter.loads(pending_text).metadata.get("title") or target)
    content = _proposed_file(live_text, pending_text)

    fd, index_file = tempfile.mkstemp(prefix="docuwaves-proposal-", suffix=".index")
    os.close(fd)
    os.unlink(index_file)  # git wants to create it itself
    env = {
        "GIT_INDEX_FILE": index_file,
        "GIT_AUTHOR_NAME": actor.name,
        "GIT_AUTHOR_EMAIL": actor.email,
        "GIT_COMMITTER_NAME": "DocuWaves",
        "GIT_COMMITTER_EMAIL": "docuwaves@local",
    }
    try:
        with repo.git.custom_environment(**env):
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
                handle.write(content)
            try:
                blob = repo.git.hash_object("-w", "--path", target, handle.name)
            finally:
                os.unlink(handle.name)
            repo.git.read_tree(head)
            repo.git.update_index("--add", "--cacheinfo", f"100644,{blob},{target}")
            repo.git.update_index("--force-remove", pending_path)
            tree = repo.git.write_tree()
            message = (
                f"Proposed: {title}\n\n"
                f"The change waiting for approval in DocuWaves ({pending_path}), applied to the live page. "
                f"Merging this branch publishes it, like 'Approve' in the editor."
            )
            commit = repo.git.commit_tree(tree, "-p", head, "-m", message)
    finally:
        if os.path.exists(index_file):
            os.unlink(index_file)
    repo.git.update_ref(f"refs/heads/{branch}", commit)
    return True


def mirror(repo: git.Repo, paths: list[str], actor: git.Actor, push_env: dict | None) -> None:
    """Brings the proposal branches for `paths` in line with what was just
    committed. `push_env` is None on an instance without a remote: the
    branches then only exist in the local repository."""
    if not enabled():
        return
    root = repo.working_tree_dir
    written: list[str] = []
    deleted: list[str] = []
    for path in dict.fromkeys(paths):
        branch = branch_name(path)
        if branch is None:
            continue
        try:
            if os.path.exists(os.path.join(root, path)):
                if _write_branch(repo, path, branch, actor):
                    written.append(branch)
            elif _ref_exists(repo, branch):
                repo.git.update_ref("-d", f"refs/heads/{branch}")
                deleted.append(branch)
        except (git.GitCommandError, OSError, ValueError) as exc:
            log.warning("Could not update proposal branch %s: %s", branch, exc)
    if push_env is None or not (written or deleted):
        return
    refspecs = [f"+refs/heads/{b}:refs/heads/{b}" for b in written] + [f":refs/heads/{b}" for b in deleted]
    try:
        with repo.git.custom_environment(**push_env):
            repo.git.push("origin", *refspecs)
    except git.GitCommandError as exc:
        # Deleting a branch somebody already removed (GitHub's "delete
        # branch after merge") is refused; push the rest one by one.
        for spec in refspecs:
            try:
                with repo.git.custom_environment(**push_env):
                    repo.git.push("origin", spec)
            except git.GitCommandError:
                if not spec.startswith(":"):
                    log.warning("Could not push proposal branch %s: %s", spec, exc)


def branch_for(project_slug: str, category_slug: str, slug: str, language: str, version: str = "") -> str:
    """The branch name the editor shows for a page's proposal ("" when off)."""
    if not enabled():
        return ""
    from app.services import content_files

    path = content_files.pending_path(project_slug, category_slug, slug, language, version)
    return branch_name(content_files._rel(path)) or ""
