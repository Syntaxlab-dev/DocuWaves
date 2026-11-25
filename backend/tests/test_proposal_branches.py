"""Proposed changes mirrored as Git branches (REVIEW_BRANCHES=on): each
`_pending/` proposal gets a branch that applies it to the live page, kept in
step with every write and removed once the proposal is gone. Off, nothing
changes."""
import subprocess

import frontmatter
import git
import pytest

from app.services import git_content_repo, proposal_branches
from app.settings import settings
from tests.test_page_review import ANNA, BEN, client, page_id, post, save, world  # noqa: F401

BRANCH = "docuwaves/proposal/handbuch/guide/start"


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(settings, "review_branches", True)


def branches(repo):
    return {h.name for h in repo.heads if h.name.startswith(proposal_branches.PREFIX)}


def file_on(repo, ref, path):
    try:
        return repo.git.show(f"{ref}:{path}")
    except git.GitCommandError:
        return None


class TestNames:
    def test_a_pending_file_names_its_branch(self):
        assert proposal_branches.branch_name("content/handbuch/guide/_pending/start.md") == BRANCH
        assert (proposal_branches.branch_name("content/handbuch/v2/guide/_pending/start.de.md")
                == "docuwaves/proposal/handbuch/v2/guide/start.de")

    def test_anything_else_has_none(self):
        assert proposal_branches.branch_name("content/handbuch/guide/start.md") is None
        assert proposal_branches.branch_name("content/handbuch/guide/_pending/notes.txt") is None

    def test_odd_file_names_still_make_a_valid_ref(self):
        name = proposal_branches.branch_name("content/p/c/_pending/a b..c.lock.md")
        assert subprocess.run(["git", "check-ref-format", f"refs/heads/{name}"]).returncode == 0


class TestOff:
    def test_no_branch_by_default(self, world):  # noqa: F811
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Der neue Text.")
        assert branches(world["repo"]) == set()
        assert "branch" not in anna.get(f"/api/admin/pages/{pid}").json()["review"]


class TestOn:
    def test_an_edit_becomes_a_branch_that_applies_it(self, world, on):  # noqa: F811
        repo = world["repo"]
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Der neue Text.")
        assert branches(repo) == {BRANCH}
        tip = repo.commit(BRANCH)
        assert tip.parents[0].hexsha == repo.head.commit.hexsha
        assert tip.author.name == "anna"
        live = frontmatter.loads(file_on(repo, BRANCH, "content/handbuch/guide/start.md"))
        assert live.content.strip() == "Der neue Text."
        assert live["title"] == "Start" and live["published"] is True
        # Merging it is approving it: the proposal file is gone there.
        assert file_on(repo, BRANCH, "content/handbuch/guide/_pending/start.md") is None
        # The working copy is untouched, and still on main.
        assert not repo.is_dirty(untracked_files=True)
        assert repo.active_branch.name != BRANCH
        assert "Der freigegebene Text." in (world["content"] / "handbuch/guide/start.md").read_text()
        assert anna.get(f"/api/admin/pages/{pid}").json()["review"]["branch"] == BRANCH

    def test_the_next_edit_moves_the_branch(self, world, on):  # noqa: F811
        repo = world["repo"]
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Erster Wurf.")
        save(anna, pid, "Start", "Zweiter Wurf.")
        assert "Zweiter Wurf." in file_on(repo, BRANCH, "content/handbuch/guide/start.md")
        assert repo.commit(BRANCH).parents[0].hexsha == repo.head.commit.hexsha

    def test_approval_removes_it(self, world, on):  # noqa: F811
        anna, ben = client(world, ANNA), client(world, BEN)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Der neue Text.")
        post(anna, f"/api/admin/pages/{pid}/review/submit")
        assert post(ben, f"/api/admin/pages/{pid}/review/approve").status_code == 200
        assert branches(world["repo"]) == set()

    def test_discarding_removes_it(self, world, on):  # noqa: F811
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Lieber doch nicht.")
        assert post(anna, f"/api/admin/pages/{pid}/review/discard").status_code == 200
        assert branches(world["repo"]) == set()

    def test_a_rename_renames_the_branch(self, world, on):  # noqa: F811
        repo = world["repo"]
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Text.")
        save(anna, pid, "Erste Schritte", "Text.")
        renamed = "docuwaves/proposal/handbuch/guide/erste-schritte"
        assert branches(repo) == {renamed}
        # The proposed title, on the live file that main already renamed.
        assert frontmatter.loads(file_on(repo, renamed, "content/handbuch/guide/erste-schritte.md"))["title"] \
            == "Erste Schritte"

    def test_a_failure_never_fails_the_save(self, world, on, monkeypatch):  # noqa: F811
        def boom(*a, **k):
            raise git.GitCommandError("write-tree", 1)

        monkeypatch.setattr(proposal_branches, "_write_branch", boom)
        anna = client(world, ANNA)
        save(anna, page_id("handbuch", "start"), "Start", "Trotzdem gespeichert.")
        assert (world["content"] / "handbuch/guide/_pending/start.md").is_file()


class TestWithARemote:
    @pytest.fixture
    def remote(self, world, on, tmp_path, monkeypatch):  # noqa: F811
        origin = git.Repo.init(tmp_path / "origin.git", bare=True)
        repo = world["repo"]
        repo.create_remote("origin", str(tmp_path / "origin.git"))
        branch = repo.active_branch.name
        repo.git.push("-u", "origin", branch)
        monkeypatch.setattr(git_content_repo, "_mode", git_content_repo.REMOTE)
        return origin

    def test_the_branch_is_pushed_and_removed_there_too(self, world, remote):
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Der neue Text.")
        assert BRANCH in {h.name for h in remote.heads}
        assert remote.commit(BRANCH).hexsha == world["repo"].commit(BRANCH).hexsha
        post(anna, f"/api/admin/pages/{pid}/review/discard")
        assert BRANCH not in {h.name for h in remote.heads}

    def test_a_branch_already_deleted_there_is_fine(self, world, remote):
        anna = client(world, ANNA)
        pid = page_id("handbuch", "start")
        save(anna, pid, "Start", "Der neue Text.")
        remote.git.branch("-D", BRANCH)  # "delete branch after merge" on the host
        assert post(anna, f"/api/admin/pages/{pid}/review/discard").status_code == 200
        assert branches(world["repo"]) == set()
