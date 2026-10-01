"""The print view's data: every published page of a project in sidebar
order, with snippets resolved -- and nothing that isn't published."""
import pytest
from fastapi import HTTPException

from app.routers import public_content as pc

PAGES = {
    1: {"id": 1, "title": "Install", "slug": "install", "language": "", "version": "", "published": True,
        "markdown_content": "Get {{product}}."},
    2: {"id": 2, "title": "Draft", "slug": "draft", "language": "", "version": "", "published": False,
        "markdown_content": "secret"},
    3: {"id": 3, "title": "Backup", "slug": "backup", "language": "", "version": "", "published": True,
        "markdown_content": "Back up."},
}


@pytest.fixture(autouse=True)
def stores(monkeypatch):
    monkeypatch.setattr(pc, "_language", lambda lang: "")
    monkeypatch.setattr(pc, "_version", lambda slug, version: "")
    monkeypatch.setattr(pc, "_versions_payload", lambda slug, version: None)
    monkeypatch.setattr(pc.projects_store, "get_project_by_slug", lambda slug, lang=None: {"id": 7, "slug": slug, "name": "Demo"} if slug == "demo" else None)
    monkeypatch.setattr(pc.categories_store, "list_categories", lambda pid, lang, version: [
        {"id": 10, "name": "Start", "slug": "start", "icon": ""},
        {"id": 11, "name": "Ops", "slug": "ops", "icon": ""},
        {"id": 12, "name": "Empty", "slug": "empty", "icon": ""},
    ])
    # The index's published listing: page 2 is a draft and never listed.
    monkeypatch.setattr(pc.pages_store, "list_project_pages", lambda *a, **k: [
        {"id": 1, "category_id": 10}, {"id": 3, "category_id": 11},
    ])
    monkeypatch.setattr(pc.pages_store, "get_page", lambda pid: dict(PAGES[pid]))
    monkeypatch.setattr(pc.snippets, "resolve", lambda md, *a, **k: md.replace("{{product}}", "DocuWaves"))


def book(**kw):
    return pc.public_get_book(None, "demo", lang=None, version=None, category=kw.get("category"))


def test_chapters_in_order_with_resolved_text_and_no_empty_chapter():
    result = book()
    assert [c["slug"] for c in result["categories"]] == ["start", "ops"]
    assert result["categories"][0]["pages"][0]["markdown_content"] == "Get DocuWaves."


def test_one_category():
    assert [c["slug"] for c in book(category="ops")["categories"]] == ["ops"]


def test_unknown_project_or_category_is_a_404():
    with pytest.raises(HTTPException):
        pc.public_get_book(None, "nope", lang=None, version=None, category=None)
    with pytest.raises(HTTPException):
        book(category="nope")


def test_a_page_unpublished_since_the_listing_is_left_out(monkeypatch):
    monkeypatch.setattr(pc.pages_store, "list_project_pages", lambda *a, **k: [{"id": 2, "category_id": 10}])
    assert book()["categories"] == []
