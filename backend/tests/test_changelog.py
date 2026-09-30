"""The changelog: news is a page going live or its text changing -- not a
reorder, not a draft, not a commit message -- and the feed says it as RSS."""
import git
import pytest
from fastapi import HTTPException

from app.routers import feeds
from app.services import changelog, git_content_repo

PATH = "content/demo/guide/install.md"


def page(title="Install", body="Text.", published=True, order=1) -> str:
    return f"---\norder: {order}\npublished: {str(published).lower()}\ntitle: {title}\n---\n\n{body}\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A real repository; each commit() writes the file and commits it."""
    repository = git.Repo.init(tmp_path)
    actor = git.Actor("Author Name", "a@example.com")
    monkeypatch.setattr(git_content_repo, "_read_repo", lambda: repository)
    git_content_repo._read_cache.clear()

    def commit(text: str | None, message: str = "secret commit message", path: str = PATH):
        target = tmp_path / path
        if text is None:
            target.unlink()
            repository.index.remove([path])
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            repository.index.add([path])
        repository.index.commit(message, author=actor, committer=actor)

    return commit


@pytest.fixture
def published(monkeypatch):
    """The index's view: which files are published pages now."""
    pages = {
        PATH: {
            "title": "Install", "slug": "install", "language": "", "version": "", "markdown_content": "Text.",
            "project_slug": "demo", "project_name": "Demo", "project_name_i18n": "",
            "category_slug": "guide", "category_name": "Guide", "category_name_i18n": "",
        }
    }
    monkeypatch.setattr(changelog, "_published_pages", lambda: pages)
    monkeypatch.setattr(changelog.snippets, "resolve", lambda markdown, *a, **k: markdown)
    monkeypatch.setattr(changelog, "_cache", None)
    return pages


def kinds() -> list[str]:
    changelog._cache = None
    return [e["kind"] for e in changelog.entries()]


class TestWhatCounts:
    def test_a_page_created_published_is_new(self, repo, published):
        repo(page())
        assert kinds() == ["new"]

    def test_a_draft_is_not_news_until_it_goes_live(self, repo, published):
        repo(page(published=False))
        assert kinds() == []
        repo(page(published=True))
        assert kinds() == ["new"]

    def test_changing_the_text_is_an_update(self, repo, published):
        repo(page())
        repo(page(body="Better text."))
        assert kinds() == ["updated"]

    def test_a_reorder_is_not_news(self, repo, published):
        repo(page())
        repo(page(order=5))
        # Still the page going live -- the reorder did not replace it.
        assert kinds() == ["new"]

    def test_a_page_published_now_is_listed_once(self, repo, published):
        repo(page())
        repo(page(body="Two."))
        repo(page(body="Three."))
        assert kinds() == ["updated"]

    def test_a_page_not_published_now_is_not_listed(self, repo, published):
        repo(page())
        published.clear()  # withdrawn since
        assert kinds() == []

    def test_no_author_or_commit_message_leaves(self, repo, published):
        repo(page())
        entry = changelog.entries()[0]
        assert "secret commit message" not in str(entry) and "Author Name" not in str(entry)
        assert set(entry) == {
            "kind", "date", "timestamp", "title", "summary", "page_slug", "language",
            "project_slug", "project_name", "category_name",
        }


def test_other_languages_are_not_in_a_readers_changelog(repo, published):
    published[PATH]["language"] = "en"
    repo(page())
    changelog._cache = None
    assert changelog.entries(language="de") == []
    assert len(changelog.entries(language="en")) == 1


class TestFeed:
    def test_rss_escapes_titles_and_makes_updates_new_items(self, repo, published, monkeypatch):
        published[PATH]["title"] = "Install <fast> & easy"
        repo(page())
        monkeypatch.setattr(feeds.site_branding, "read_branding", lambda: {"name": "Docs", "name_i18n": {}})
        monkeypatch.setattr(feeds.site_languages, "is_multilingual", lambda: False)
        monkeypatch.setattr(feeds.content_versions, "default_version", lambda slug: "")
        changelog._cache = None
        xml = feeds.feed_xml("https://docs.example.com", "de", None)
        assert "<title>Neu: Install &lt;fast&gt; &amp; easy</title>" in xml
        assert "<link>https://docs.example.com/p/demo/pages/install</link>" in xml
        assert 'isPermaLink="false">https://docs.example.com/p/demo/pages/install#new-' in xml

    def test_an_unknown_project_is_a_404(self, monkeypatch):
        monkeypatch.setattr(feeds.projects_store, "get_project_by_slug", lambda slug, lang: None)
        monkeypatch.setattr(feeds.site_languages, "languages", lambda: [])
        monkeypatch.setattr(feeds.site_languages, "default_language", lambda: "")
        with pytest.raises(HTTPException) as missing:
            feeds.project_feed("nope", request=None, lang=None)
        assert missing.value.status_code == 404
