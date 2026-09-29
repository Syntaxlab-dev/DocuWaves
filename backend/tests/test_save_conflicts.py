"""Two people, one page: a save must not silently replace a change it never saw.

Pinned down here: the revision is a fingerprint of exactly what an editor
sees (title + body), a save naming a stale revision is refused BEFORE anything
is written, the route turns that into 409 `page_changed`, and a save that
names no revision (MCP tools, older tabs) behaves as it always did.
"""
import pytest
from fastapi import HTTPException

from app.routers import admin_content
from app.services import pages_store

PAGE = {
    "id": 7,
    "title": "Installation",
    "markdown_content": "# Install\n\nRun it.",
    "slug": "installation",
    "language": "en",
    "project_id": 1,
    "category_id": 2,
    "version": "",
}


class TestRevision:
    def test_same_text_same_revision(self):
        assert pages_store.page_revision(PAGE) == pages_store.page_revision(dict(PAGE))

    def test_a_changed_body_changes_it(self):
        assert pages_store.page_revision(PAGE) != pages_store.page_revision({**PAGE, "markdown_content": "# Install\n\nRun it!"})

    def test_a_changed_title_changes_it(self):
        assert pages_store.page_revision(PAGE) != pages_store.page_revision({**PAGE, "title": "Setup"})

    def test_title_and_body_cannot_be_traded_against_each_other(self):
        a = {**PAGE, "title": "ab", "markdown_content": "c"}
        b = {**PAGE, "title": "a", "markdown_content": "bc"}
        assert pages_store.page_revision(a) != pages_store.page_revision(b)


class TestStore:
    @pytest.fixture
    def nothing_written(self, monkeypatch):
        writes = []
        monkeypatch.setattr(pages_store, "get_page", lambda page_id: dict(PAGE))
        # If the check did not stop the save, the first thing it would reach
        # is looking up the project -- record that as "a write was attempted".
        monkeypatch.setattr(pages_store.projects_store, "get_project", lambda *a: writes.append("project") or None)
        # ...and stop it right there: with no category either, update_page
        # returns None before touching a file or the database.
        monkeypatch.setattr(pages_store.categories_store, "get_category", lambda *a: None)
        return writes

    def test_a_stale_revision_is_refused_before_anything_is_written(self, nothing_written):
        with pytest.raises(pages_store.PageChangedError) as refused:
            pages_store.update_page(7, "Installation", "installation", "mine", 2, "alice", expected_revision="stale")
        assert refused.value.current_revision == pages_store.page_revision(PAGE)
        assert nothing_written == []

    def test_the_current_revision_goes_through_to_the_write(self, nothing_written):
        pages_store.update_page(7, "Installation", "installation", "mine", 2, "alice",
                                expected_revision=pages_store.page_revision(PAGE))
        assert nothing_written == ["project"]

    def test_no_revision_means_no_check(self, nothing_written):
        pages_store.update_page(7, "Installation", "installation", "mine", 2, "alice")
        assert nothing_written == ["project"]


class TestRoute:
    def test_a_conflict_is_a_409_page_changed(self, monkeypatch):
        monkeypatch.setattr(admin_content, "_require_content_repo", lambda: None)
        monkeypatch.setattr(admin_content.pages_store, "get_page", lambda page_id: dict(PAGE))
        monkeypatch.setattr(admin_content.categories_store, "get_category", lambda cid: {"id": cid})
        monkeypatch.setattr(admin_content, "_author", lambda request: "alice")

        def refuse(*args, **kwargs):
            raise pages_store.PageChangedError("abc123")

        monkeypatch.setattr(admin_content.pages_store, "update_page", refuse)
        body = admin_content.PageIn(title="Installation", markdown_content="mine", category_id=2, base_revision="old")
        with pytest.raises(HTTPException) as refused:
            admin_content.admin_update_page(7, body, request=None)
        assert refused.value.status_code == 409
        assert refused.value.detail == "page_changed"
        assert refused.value.headers["X-Current-Revision"] == "abc123"
