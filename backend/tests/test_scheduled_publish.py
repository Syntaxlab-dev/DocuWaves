"""Scheduled publishing (services/scheduled_publish.py), end to end: a real
content repo, a real index, the real endpoints and the scheduler's tick."""
import importlib
from datetime import datetime, timedelta, timezone

import git
import pytest
from fastapi.testclient import TestClient

from app.services import (
    content_sync,
    content_versions,
    db,
    git_content_repo,
    pages_store,
    scheduled_publish,
    session_secret,
    users_store,
)
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def page(title, published):
    return f"---\norder: 1\npublished: {'true' if published else 'false'}\ntitle: {title}\n---\n\nText.\n"


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    write(content, "docs/_project.yml", "name: Docs\n")
    write(content, "docs/guide/_category.yml", "name: Guide\n")
    write(content, "docs/guide/launch.md", page("Launch", False))
    write(content, "docs/guide/live.md", page("Live", True))
    write(content, "strict/_project.yml", "name: Strict\nreview: required\n")
    write(content, "strict/guide/_category.yml", "name: Guide\n")
    write(content, "strict/guide/draft.md", page("Draft", False))
    repository = git.Repo.init(repo_dir)
    repository.index.add([str(p.relative_to(repo_dir)) for p in content.rglob("*") if p.is_file()])
    actor = git.Actor("Test", "t@example.com")
    repository.index.commit("Inhalt", author=actor, committer=actor)

    monkeypatch.setattr(settings, "content_repo_path", str(repo_dir))
    monkeypatch.setattr(settings, "content_repo_url", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "index.db"))
    monkeypatch.setattr(settings, "webhook_urls", ())
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(session_secret, "_SECRET_PATH", tmp_path / ".session_secret")
    monkeypatch.setattr(git_content_repo, "_read_repo", lambda: repository)
    monkeypatch.setattr(git_content_repo, "_repo", repository)
    monkeypatch.setattr(git_content_repo, "_mode", git_content_repo.LOCAL)
    monkeypatch.setattr(content_versions, "_cache", {})
    git_content_repo._read_cache.clear()

    db.init_schema()
    content_sync.full_sync()
    users_store.create_first_admin("chef", "chef-passwort-123")
    app = importlib.import_module("app.main").app
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-123"}, headers=ORIGIN).status_code == 200
    return c


def page_id(slug, project="docs"):
    project_row = next(p for p in __import__("app.services.projects_store", fromlist=["x"]).list_projects() if p["slug"] == project)
    return pages_store.get_page_by_slug(project_row["id"], slug, "", "")["id"]


def soon(minutes=30):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def schedule(c, pid, when):
    return c.put(f"/api/admin/pages/{pid}/schedule", json={"publish_at": when}, headers=ORIGIN)


class TestScheduling:
    def test_a_draft_is_scheduled_and_read_back(self, world):
        pid = page_id("launch")
        r = schedule(world, pid, soon())
        assert r.status_code == 200, r.text
        got = world.get(f"/api/admin/pages/{pid}/schedule").json()["schedule"]
        assert got["scheduled_by"] == "chef" and got["publish_at"].endswith("+00:00")
        assert [s["page_slug"] for s in world.get("/api/admin/schedule").json()["scheduled"]] == ["launch"]

    @pytest.mark.parametrize("when", ["2026-12-01T09:00:00", "morgen", "2020-01-01T00:00:00+00:00"])
    def test_refused_without_an_offset_or_in_the_past(self, world, when):
        assert schedule(world, page_id("launch"), when).status_code == 400

    def test_a_live_page_cannot_be_scheduled(self, world):
        assert schedule(world, page_id("live"), soon()).status_code == 409

    def test_not_where_publishing_needs_approval(self, world):
        r = schedule(world, page_id("draft", "strict"), soon())
        assert r.status_code == 409 and r.json()["detail"] == "review_required"

    def test_cancelling(self, world):
        pid = page_id("launch")
        schedule(world, pid, soon())
        assert world.delete(f"/api/admin/pages/{pid}/schedule", headers=ORIGIN).json() == {"cancelled": True}
        assert world.get(f"/api/admin/pages/{pid}/schedule").json()["schedule"] is None


class TestTheScheduler:
    def test_nothing_happens_before_the_time(self, world):
        schedule(world, page_id("launch"), soon())
        assert scheduled_publish.run_due() == 0
        assert not pages_store.get_page(page_id("launch"))["published"]

    def test_the_page_goes_live_once_due_in_the_scheduler_s_name(self, world):
        schedule(world, page_id("launch"), soon())
        later = datetime.now(timezone.utc) + timedelta(hours=1)
        assert scheduled_publish.run_due(later) == 1
        assert pages_store.get_page(page_id("launch"))["published"]
        assert scheduled_publish.upcoming() == []
        assert git_content_repo._repo.head.commit.author.name == "chef"

    def test_publishing_by_hand_first_clears_it(self, world):
        pid = page_id("launch")
        schedule(world, pid, soon())
        assert world.post(f"/api/admin/pages/{pid}/publish?published=true", headers=ORIGIN).status_code == 200
        assert scheduled_publish.upcoming() == []

    def test_a_project_that_starts_requiring_approval_drops_it(self, world, monkeypatch):
        schedule(world, page_id("launch"), soon())
        monkeypatch.setattr(pages_store, "review_required", lambda project: True)
        assert scheduled_publish.run_due(datetime.now(timezone.utc) + timedelta(hours=1)) == 0
        assert scheduled_publish.upcoming() == []

    def test_a_renamed_page_keeps_its_schedule(self, world):
        pid = page_id("launch")
        schedule(world, pid, soon())
        category = pages_store.get_page(pid)["category_id"]
        r = world.put(
            f"/api/admin/pages/{pid}",
            json={"title": "Big Launch", "category_id": category, "markdown_content": "Text."},
            headers=ORIGIN,
        )
        assert r.status_code == 200, r.text
        assert [s["page_slug"] for s in scheduled_publish.upcoming()] == [r.json()["slug"]]

    def test_a_deleted_page_takes_its_schedule_with_it(self, world):
        pid = page_id("launch")
        schedule(world, pid, soon())
        assert world.delete(f"/api/admin/pages/{pid}", headers=ORIGIN).status_code == 200
        assert scheduled_publish.upcoming() == []


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2026-12-01T09:00:00+01:00", "2026-12-01T08:00:00+00:00"),
        ("2026-12-01T08:00:00Z", "2026-12-01T08:00:00+00:00"),
    ],
)
def test_times_are_stored_in_utc(value, expected):
    assert scheduled_publish.parse(value).isoformat() == expected
