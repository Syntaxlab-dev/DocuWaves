"""GitPython reads objects through one shared `git cat-file` process per
repository, and that process has no locking of its own (see _odb_lock in
services/git_content_repo.py). One unlocked read racing a page view wedges
the pipe, and from then on every git read in the instance hangs. So reads
of HEAD's object stay inside git_content_repo, behind the lock."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
UNLOCKED_READS = re.compile(r"\.head\.(?:commit\b|object\b|is_valid\()")


def test_head_objects_are_read_only_inside_git_content_repo():
    offenders = [
        f"{path.relative_to(APP)}:{number}"
        for path in APP.rglob("*.py")
        if path.name != "git_content_repo.py"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if UNLOCKED_READS.search(line) and not line.lstrip().startswith("#")
    ]
    assert offenders == [], f"use git_content_repo.head_sha() instead: {offenders}"
