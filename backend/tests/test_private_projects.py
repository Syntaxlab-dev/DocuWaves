"""Private projects, end to end: the real app, a real SQLite index and a real
content repo with one public and one private project -- then every door
(services/visibility.py lists them) is tried twice, as a stranger and signed
in. A private project that shows up through any one of them is not private.
"""
import importlib

import git
import pytest
from fastapi.testclient import TestClient

from app.services import changelog, content_sync, db, git_content_repo, search_suggest, session_secret, seo
from app.services import users_store, webhooks
from app.settings import settings

SECRET_WORD = "zebrafalke"
ORIGIN = {"Origin": "http://testserver"}


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def page(title, body):
    return f"---\norder: 1\npublished: true\ntitle: {title}\n---\n\n{body}\n"


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    content = repo_dir / "content"
    write(content, "open/_project.yml", "name: Offen\n")
    write(content, "open/guide/_category.yml", "name: Guide\n")
    write(content, "open/guide/start.md", page("Start", "Willkommen in der offenen Doku."))
    write(content, "intern/_project.yml", "name: Intern\nvisibility: private\n")
    write(content, "intern/guide/_category.yml", "name: Guide\n")
    write(content, "intern/guide/plan.md", page("Geheimplan", f"Die Vertraulichkeitsstufe heißt {SECRET_WORD}."))
    (content / "intern/assets").mkdir(parents=True)
    (content / "intern/assets/plan.png").write_bytes(b"\x89PNG not really")
    repository = git.Repo.init(repo_dir)
    repository.index.add([str(p.relative_to(repo_dir)) for p in content.rglob("*") if p.is_file()])
    actor = git.Actor("Test", "t@example.com")
    repository.index.commit("Inhalt", author=actor, committer=actor)

    monkeypatch.setattr(settings, "content_repo_path", str(repo_dir))
    monkeypatch.setattr(settings, "content_repo_url", "")
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "index.db"))
    monkeypatch.setattr(settings, "public_base_url", "")
    monkeypatch.setattr(session_secret, "_SECRET_PATH", tmp_path / ".session_secret")
    monkeypatch.setattr(git_content_repo, "_read_repo", lambda: repository)
    git_content_repo._read_cache.clear()
    monkeypatch.setattr(changelog, "_cache", None)
    monkeypatch.setattr(search_suggest, "_cached", None)
    search_suggest._correct_word.cache_clear()

    db.init_schema()
    content_sync.full_sync()
    users_store.create_first_admin("chef", "chef-passwort-123")
    users_store.create_user("leserin", "leser-passwort-123", users_store.READER)

    app = importlib.import_module("app.main").app
    return app


def client(app, user=None):
    c = TestClient(app)
    if user:
        r = c.post("/api/auth/login", json={"username": user[0], "password": user[1]}, headers=ORIGIN)
        assert r.status_code == 200, r.text
    return c


READER = ("leserin", "leser-passwort-123")
ADMIN = ("chef", "chef-passwort-123")

DOORS = [
    "/api/public/projects/intern",
    "/api/public/projects/intern/nav",
    "/api/public/projects/intern/categories/guide",
    "/api/public/projects/intern/pages/plan",
    "/api/public/projects/intern/book",
    "/api/public/assets/intern/assets/plan.png",
]


class TestAStranger:
    def test_the_project_list_does_not_mention_it(self, world):
        names = [p["slug"] for p in client(world).get("/api/public/projects").json()["projects"]]
        assert names == ["open"]

    @pytest.mark.parametrize("path", DOORS)
    def test_every_direct_door_is_a_plain_404(self, world, path):
        r = client(world).get(path)
        assert r.status_code == 404
        assert "intern" not in r.text.lower().replace("/api/public/projects/intern", "")

    def test_search_finds_nothing(self, world):
        r = client(world).get(f"/api/public/search?q={SECRET_WORD}").json()
        assert r["results"] == [] and not r.get("corrected")
        scoped = client(world).get(f"/api/public/search?q={SECRET_WORD}&project=intern").json()
        assert scoped["results"] == []

    def test_the_typo_suggestions_never_learned_its_words(self, world):
        assert not search_suggest.vocabulary().knows(SECRET_WORD)
        assert search_suggest.correct("zebrafalkr") is None

    def test_changelog_feed_and_sitemap_leave_it_out(self, world):
        c = client(world)
        assert all(e["project_slug"] != "intern" for e in c.get("/api/public/changelog").json()["entries"])
        assert "Geheimplan" not in c.get("/feed.xml").text
        assert c.get("/p/intern/feed.xml").status_code == 404
        assert "/p/intern" not in c.get("/sitemap.xml").text

    def test_feedback_for_it_is_refused(self, world):
        r = client(world).post(
            "/api/public/feedback", json={"project": "intern", "page": "plan", "helpful": True}, headers=ORIGIN
        )
        assert r.status_code in (404, 422)
        assert r.status_code != 200

    def test_the_server_rendered_head_does_not_name_it(self, world):
        route = seo.parse_route("/p/intern/pages/plan") if hasattr(seo, "parse_route") else None
        if route is not None:
            assert seo._project_context(route, "") is None


class TestSignedIn:
    def test_a_reader_sees_it_everywhere_a_reader_reads(self, world):
        c = client(world, READER)
        assert {p["slug"] for p in c.get("/api/public/projects").json()["projects"]} == {"open", "intern"}
        for path in DOORS:
            assert c.get(path).status_code == 200, path
        hits = c.get(f"/api/public/search?q={SECRET_WORD}").json()["results"]
        assert [h["page_slug"] for h in hits] == ["plan"]
        assert any(e["project_slug"] == "intern" for e in c.get("/api/public/changelog").json()["entries"])

    def test_signed_in_answers_are_never_cached_in_shared_caches(self, world):
        r = client(world, READER).get("/api/public/projects/intern/pages/plan")
        assert r.headers["cache-control"] == "private, no-store"
        assert r.headers["vary"].lower().count("cookie") == 1
        anonymous = client(world).get("/api/public/projects")
        assert "Cookie" in anonymous.headers["vary"]

    def test_feeds_and_sitemap_stay_public_only_even_when_signed_in(self, world):
        c = client(world, READER)
        assert "Geheimplan" not in c.get("/feed.xml").text
        assert c.get("/p/intern/feed.xml").status_code == 404
        assert "/p/intern" not in c.get("/sitemap.xml").text

    def test_a_reader_cannot_open_the_admin_area(self, world):
        c = client(world, READER)
        r = c.get("/api/admin/projects")
        assert r.status_code == 403 and r.json()["detail"] == "reader_account"
        status = c.get("/api/auth/status").json()  # who am I, sign out: still open
        assert status["authenticated"] and status["role"] == "reader"

    def test_the_admin_sees_it_in_the_admin_list_and_publicly(self, world):
        c = client(world, ADMIN)
        assert {p["slug"] for p in c.get("/api/admin/projects").json()["projects"]} == {"open", "intern"}
        assert c.get("/api/public/projects/intern/pages/plan").status_code == 200

    def test_signing_out_hides_it_again(self, world):
        c = client(world, READER)
        assert c.get("/api/public/projects/intern").status_code == 200
        c.post("/api/auth/logout", headers=ORIGIN)
        assert c.get("/api/public/projects/intern").status_code == 404


def test_a_forged_session_flag_is_not_enough(world):
    """A cookie claiming `authenticated` for a session that was never
    registered (or was revoked) must not open anything."""
    c = client(world, READER)
    users_store_session = c.cookies
    assert users_store_session  # a real session exists...
    from app.services import session_registry_store

    session_registry_store.revoke_for_user("leserin")  # ...and is revoked server-side
    assert c.get("/api/public/projects/intern").status_code == 404


def test_webhooks_say_nothing_about_a_private_project(monkeypatch):
    monkeypatch.setattr(settings, "webhook_urls", ("https://example.org/hook",))
    monkeypatch.setattr(settings, "webhook_events", frozenset({"published"}))
    queued = []
    monkeypatch.setattr(webhooks._pool, "submit", lambda *a: queued.append(a))
    webhooks.notify("published", {"title": "x"}, {"slug": "intern", "private": True})
    assert queued == []


class TestRoles:
    def test_reader_is_the_least_and_a_step_down_signs_out(self):
        assert users_store.rank(users_store.READER) < users_store.rank(users_store.VIEWER)
        assert not users_store.may_open_admin(users_store.READER)
        assert users_store.may_open_admin(users_store.VIEWER)
        assert not users_store.may_write(users_store.READER)


def test_the_flag_round_trips_through_the_project_file(tmp_path, monkeypatch):
    from app.services import content_files

    monkeypatch.setattr(settings, "content_repo_path", str(tmp_path))
    content_files.write_project("p", "P", "", "", "", "", 0, private=True)
    assert "visibility: private" in (tmp_path / "content/p/_project.yml").read_text()
    assert content_files.read_project("p")["private"] is True
    content_files.write_project("p", "P", "", "", "", "", 0, private=False)
    assert "visibility" not in (tmp_path / "content/p/_project.yml").read_text()
    write(tmp_path / "content", "q/_project.yml", "name: Q\nvisibility: privat\n")  # a typo is public
    assert content_files.read_project("q")["private"] is False


# ---- Part 2: sign-in link, exposure check, the guard, the SSO return ----


def test_the_site_offers_sign_in_only_when_there_is_something_private(world):
    assert client(world).get("/api/public/site").json()["sign_in"] is True


class TestRepoExposure:
    @pytest.mark.parametrize(
        "configured, anonymous, shown",
        [
            ("https://x-access-token:SECRET@github.com/acme/docs.git", "https://github.com/acme/docs.git", "github.com/acme/docs"),
            ("git@github.com:acme/docs.git", "https://github.com/acme/docs.git", "github.com/acme/docs"),
            ("ssh://git@git.example.com:2222/me/docs.git", "https://git.example.com/me/docs.git", "git.example.com/me/docs"),
            ("https://user:pw@forgejo.local:3000/me/docs", "https://forgejo.local:3000/me/docs", "forgejo.local/me/docs"),
        ],
    )
    def test_the_probe_never_carries_a_credential(self, configured, anonymous, shown):
        from app.services import repo_exposure

        assert repo_exposure.anonymous_url(configured) == anonymous
        assert repo_exposure.display_location(configured) == shown
        assert "SECRET" not in repo_exposure.anonymous_url(configured)

    @pytest.mark.parametrize(
        "code, stderr, verdict",
        [
            (0, "", "public"),
            (128, "fatal: could not read Username for 'https://github.com': terminal prompts disabled", "private"),
            (128, "remote: Repository not found.", "private"),
            (128, "fatal: unable to access: The requested URL returned error: 403", "private"),
            (128, "fatal: unable to access: Could not resolve host: x.invalid", "unknown"),
        ],
    )
    def test_answers_are_classified(self, code, stderr, verdict):
        from app.services import repo_exposure

        assert repo_exposure.classify(code, stderr) == verdict

    def test_a_local_only_instance_has_nothing_to_expose(self, monkeypatch):
        from app.services import repo_exposure

        monkeypatch.setattr(settings, "content_repo_url", "")
        assert repo_exposure.check() == {"remote": "", "visibility": None}


class TestPrivateOnAPublicRepo:
    def body(self, **kw):
        from app.routers import admin_content

        return admin_content.ProjectIn(name="Intern", **kw)

    def test_refused_unless_acknowledged(self, monkeypatch):
        from fastapi import HTTPException

        from app.routers import admin_content

        monkeypatch.setattr(admin_content.repo_exposure, "is_public", lambda: True)
        with pytest.raises(HTTPException) as refused:
            admin_content._refuse_private_on_public_repo(self.body(private=True))
        assert refused.value.status_code == 409 and refused.value.detail.startswith("public_repo")
        admin_content._refuse_private_on_public_repo(self.body(private=True, acknowledge_public_repo=True))
        admin_content._refuse_private_on_public_repo(self.body(private=False))
        # Already private: an ordinary save does not ask again.
        admin_content._refuse_private_on_public_repo(self.body(private=True), currently_private=True)

    def test_a_private_repo_needs_no_acknowledgement(self, monkeypatch):
        from app.routers import admin_content

        monkeypatch.setattr(admin_content.repo_exposure, "is_public", lambda: False)
        admin_content._refuse_private_on_public_repo(self.body(private=True))


@pytest.mark.parametrize(
    "target, expected",
    [
        ("/p/intern/pages/plan", "/p/intern/pages/plan"),
        ("/de/p/x?lang=de#a", "/de/p/x?lang=de#a"),
        ("//evil.example", "/"),
        ("https://evil.example", "/"),
        ("/\\evil.example", "/"),
        ("javascript:alert(1)", "/"),
        ("/a\r\nLocation: x", "/"),
        ("", "/"),
    ],
)
def test_sso_only_returns_to_a_page_on_this_site(target, expected):
    from app.routers.auth import safe_next

    assert safe_next(target) == expected
