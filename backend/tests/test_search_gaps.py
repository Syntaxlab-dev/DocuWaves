"""The gaps radar: searches that found nothing, tallied as words and never
as people -- and only where a tally is reader feedback (services/search_gaps.py)."""
import importlib

import git
import pytest
from fastapi.testclient import TestClient

from app.services import content_sync, db, git_content_repo, search_gaps, search_suggest, session_secret, users_store
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}
CHEF = ("chef", "chef-passwort-123")
CLARA = ("clara", "clara-passwort-123")


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def app(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    write(content, "offen/_project.yml", "name: Offen\n")
    write(content, "offen/guide/_category.yml", "name: Guide\n")
    write(content, "offen/guide/start.md", "---\norder: 1\npublished: true\ntitle: Start\n---\n\nInstallation mit Docker.\n")
    write(content, "intern/_project.yml", "name: Intern\nvisibility: private\n")
    write(content, "intern/guide/_category.yml", "name: Guide\n")
    write(content, "intern/guide/plan.md", "---\norder: 1\npublished: true\ntitle: Plan\n---\n\nGeheim.\n")
    repository = git.Repo.init(repo_dir)
    repository.index.add([str(p.relative_to(repo_dir)) for p in content.rglob("*") if p.is_file()])
    actor = git.Actor("Test", "t@example.com")
    repository.index.commit("Inhalt", author=actor, committer=actor)

    monkeypatch.setattr(settings, "content_repo_path", str(repo_dir))
    monkeypatch.setattr(settings, "content_repo_url", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "index.db"))
    monkeypatch.setattr(settings, "search_gaps_enabled", True)
    monkeypatch.setattr(session_secret, "_SECRET_PATH", tmp_path / ".session_secret")
    monkeypatch.setattr(git_content_repo, "_read_repo", lambda: repository)
    git_content_repo._read_cache.clear()
    monkeypatch.setattr(search_suggest, "_cached", None)
    search_suggest._correct_word.cache_clear()
    search_gaps.reset_rate_limits()

    db.init_schema()
    content_sync.full_sync()
    users_store.create_first_admin(*CHEF)
    users_store.create_user(*CLARA, users_store.VIEWER)
    return importlib.import_module("app.main").app


def client(app, user=None):
    c = TestClient(app)
    if user:
        assert c.post("/api/auth/login", json={"username": user[0], "password": user[1]}, headers=ORIGIN).status_code == 200
    return c


def search(c, q, **params):
    query = "&".join(f"{k}={v}" for k, v in {"q": q, "record": "true", **params}.items())
    return c.get(f"/api/public/search?{query}").json()


def gaps():
    return {g["query"]: g["hits"] for g in search_gaps.top()}


class TestWhatCounts:
    def test_a_results_page_search_that_finds_nothing_is_counted(self, app):
        c = client(app)
        assert search(c, "Kubernetes  Helm")["results"] == []
        search(c, "kubernetes helm")
        assert gaps() == {"kubernetes helm": 2}

    def test_a_search_that_finds_something_is_not(self, app):
        search(client(app), "docker")
        assert gaps() == {}

    def test_search_as_you_type_is_not(self, app):
        client(app).get("/api/public/search?q=kube")
        assert gaps() == {}

    def test_signed_in_searches_are_not(self, app):
        search(client(app, CLARA), "kubernetes")
        assert gaps() == {}

    def test_searches_in_a_private_project_are_not(self, app):
        search(client(app), "kubernetes", project="intern")
        assert gaps() == {}

    @pytest.mark.parametrize("q", ["max@example.com", "Kunde 4711234", "0171 2345678", "x"])
    def test_what_looks_personal_or_is_too_short_is_not(self, app, q):
        search(client(app), q)
        assert gaps() == {}

    def test_switched_off_nothing_is_written(self, app, monkeypatch):
        monkeypatch.setattr(settings, "search_gaps_enabled", False)
        search(client(app), "kubernetes")
        assert gaps() == {}

    def test_one_client_cannot_flood_the_list(self, app):
        c = client(app)
        for i in range(40):
            search(c, f"wort{chr(97 + i % 26)}{chr(97 + i // 26)}")
        assert len(gaps()) == 30


class TestStorage:
    def test_only_words_and_counts_are_kept(self, app):
        search(client(app), "Kubernetes")
        with db.get_connection() as conn:
            columns = [r[1] for r in conn.execute("PRAGMA table_info(search_gaps)").fetchall()]
        assert set(columns) == {"id", "query", "language", "project_slug", "hits", "first_seen", "last_seen"}

    def test_old_entries_expire(self, app):
        search(client(app), "kubernetes")
        with db.get_connection() as conn:
            conn.execute("UPDATE search_gaps SET last_seen = '2000-01-01'")
        assert gaps() == {}

    def test_a_reindex_does_not_touch_it(self, app):
        search(client(app), "kubernetes")
        content_sync.full_sync()
        assert gaps() == {"kubernetes": 1}


class TestAdmin:
    def test_listed_forgotten_and_cleared(self, app):
        search(client(app), "kubernetes")
        search(client(app), "helm chart")
        chef = client(app, CHEF)
        listing = chef.get("/api/admin/search-gaps").json()
        assert listing["enabled"] is True and len(listing["gaps"]) == 2
        first = listing["gaps"][0]["id"]
        assert chef.delete(f"/api/admin/search-gaps/{first}", headers=ORIGIN).json() == {"cleared": 1}
        assert chef.delete("/api/admin/search-gaps", headers=ORIGIN).json() == {"cleared": 1}

    def test_a_read_only_account_reads_but_does_not_clear(self, app):
        search(client(app), "kubernetes")
        clara = client(app, CLARA)
        assert len(clara.get("/api/admin/search-gaps").json()["gaps"]) == 1
        assert clara.delete("/api/admin/search-gaps", headers=ORIGIN).status_code == 403

    def test_strangers_see_nothing(self, app):
        assert client(app).get("/api/admin/search-gaps").status_code == 401
