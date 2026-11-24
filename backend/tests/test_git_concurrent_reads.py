"""Page views run in a thread pool and all share one GitPython Repo, whose
object reads go through a single `git cat-file --batch` pipe. Unguarded, two
threads reading at once interleave on that pipe and hang for good -- the
whole server stops answering. This drives many concurrent reads through the
public helpers and fails (instead of hanging) if any of them doesn't return."""
from concurrent.futures import ThreadPoolExecutor, wait

import git
import pytest

from app.services import git_content_repo


@pytest.fixture
def repository(tmp_path, monkeypatch):
    repo = git.Repo.init(tmp_path)
    actor = git.Actor("A", "a@example.com")
    for n in range(20):
        target = tmp_path / f"content/p{n}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"page {n}\n" * 50, encoding="utf-8")
        repo.index.add([f"content/p{n}.md"])
    repo.index.commit("pages", author=actor, committer=actor)
    monkeypatch.setattr(git_content_repo, "ensure_clone", lambda: repo)
    git_content_repo._read_cache.clear()
    return repo


def test_concurrent_reads_do_not_hang(repository):
    sha = repository.head.commit.hexsha

    def read(n: int):
        path = f"content/p{n % 20}.md"
        git_content_repo._read_cache.clear()  # make every call reach the object database
        assert git_content_repo.head_sha() == sha
        assert git_content_repo.blob_text(sha, path).startswith(f"page {n % 20}")
        git_content_repo.last_modified(path)

    pool = ThreadPoolExecutor(max_workers=16)
    futures = [pool.submit(read, n) for n in range(400)]
    done, not_done = wait(futures, timeout=60)
    pool.shutdown(wait=False, cancel_futures=True)
    assert not not_done, "concurrent repository reads hung"
    for future in done:
        future.result()
