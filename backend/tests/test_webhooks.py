"""Webhooks: the right message format per destination, a verifiable
signature, never failing a save -- and announcing a change of STATE only,
because the editor calls "publish" after every save."""
import hashlib
import hmac
import json

import pytest
import requests

from app.services import pages_store, webhooks
from app.settings import settings

PAGE = {
    "id": 1, "title": "Installation", "slug": "installation", "language": "de", "version": "",
    "markdown_content": "So installierst du DocuWaves.\n\n## Weiter", "published": True,
    "project_id": 1, "category_id": 2, "sort_order": 0, "reviewed_by": "", "reviewed_at": "",
}
PROJECT = {"id": 1, "name": "Demo", "slug": "demo"}
CATEGORY = {"id": 2, "name": "Anleitungen", "slug": "anleitungen", "version": ""}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "webhook_urls", ("https://example.org/hook",))
    monkeypatch.setattr(settings, "webhook_events", frozenset({"published", "updated", "unpublished"}))
    monkeypatch.setattr(settings, "webhook_secret", "")
    monkeypatch.setattr(settings, "public_base_url", "https://docs.example.com")
    monkeypatch.setattr("app.services.site_languages.is_multilingual", lambda: False)
    monkeypatch.setattr("app.services.site_languages.default_language", lambda: "de")
    monkeypatch.setattr("app.services.content_versions.default_version", lambda slug: "")


def data(event="published"):
    return webhooks._event_data(event, PAGE, PROJECT, CATEGORY)


class TestFormats:
    def test_the_event_names_page_project_and_public_url(self):
        d = data()
        assert d["page"]["url"] == "https://docs.example.com/p/demo/pages/installation"
        assert d["page"]["summary"].startswith("So installierst du DocuWaves")
        assert d["project"] == {"name": "Demo", "slug": "demo"}

    def test_no_public_base_url_means_no_link(self, monkeypatch):
        monkeypatch.setattr(settings, "public_base_url", "")
        assert data()["page"]["url"] == ""

    def test_discord_gets_an_embed_and_pings_nobody(self):
        body = webhooks.build_body("https://discord.com/api/webhooks/1/abc", "published", data())
        assert body["embeds"][0]["title"] == "Installation"
        assert body["embeds"][0]["url"].endswith("/p/demo/pages/installation")
        assert body["allowed_mentions"] == {"parse": []}
        assert "Neu veröffentlicht" in body["content"]

    def test_slack_gets_a_linked_text_with_markup_escaped(self):
        d = data()
        d["page"]["title"] = "A <b> & C"
        body = webhooks.build_body("https://hooks.slack.com/services/x", "updated", d)
        assert body == {"text": "*Aktualisiert:* <https://docs.example.com/p/demo/pages/installation|A &lt;b&gt; &amp; C> (Demo)"}

    def test_anything_else_gets_the_json_event(self):
        body = webhooks.build_body("https://example.org/hook", "published", data())
        assert body["event"] == "published" and body["page"]["slug"] == "installation"


class TestDelivery:
    @pytest.fixture
    def posts(self, monkeypatch):
        sent = []

        class Response:
            def __init__(self, code):
                self.status_code = code

        codes = []

        def post(url, data, headers, timeout):
            sent.append({"url": url, "body": data, "headers": headers})
            return Response(codes.pop(0) if codes else 200)

        monkeypatch.setattr(webhooks.requests, "post", post)
        monkeypatch.setattr(webhooks.time, "sleep", lambda s: None)
        return sent, codes

    def test_json_deliveries_are_signed_when_a_secret_is_set(self, posts, monkeypatch):
        sent, _ = posts
        monkeypatch.setattr(settings, "webhook_secret", "s3cret")
        webhooks._deliver("https://example.org/hook", "published", data())
        body, headers = sent[0]["body"], sent[0]["headers"]
        expected = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
        assert headers["X-DocuWaves-Signature"] == f"sha256={expected}"
        assert headers["X-DocuWaves-Event"] == "published"
        assert json.loads(body)["page"]["title"] == "Installation"

    def test_a_server_error_is_retried_once(self, posts):
        sent, codes = posts
        codes += [502, 200]
        webhooks._deliver("https://example.org/hook", "published", data())
        assert len(sent) == 2

    def test_a_client_error_is_not_retried(self, posts):
        sent, codes = posts
        codes += [404]
        webhooks._deliver("https://example.org/hook", "published", data())
        assert len(sent) == 1

    def test_a_dead_endpoint_never_raises(self, monkeypatch):
        def refuse(*a, **k):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(webhooks.requests, "post", refuse)
        monkeypatch.setattr(webhooks.time, "sleep", lambda s: None)
        webhooks._deliver("https://example.org/hook", "published", data())  # no exception

    def test_the_log_names_the_host_not_the_secret_path(self):
        assert webhooks._redacted("https://discord.com/api/webhooks/123/SECRET") == "discord.com"


class TestWhenItFires:
    @pytest.fixture
    def fired(self, monkeypatch):
        events = []
        monkeypatch.setattr(pages_store.webhooks, "notify", lambda event, *a: events.append(event))
        state = {"page": dict(PAGE)}
        monkeypatch.setattr(pages_store, "get_page", lambda pid: dict(state["page"]))
        monkeypatch.setattr(pages_store, "get_page_by_slug", lambda *a: dict(state["page"]))
        monkeypatch.setattr(pages_store.projects_store, "get_project", lambda pid: PROJECT)
        monkeypatch.setattr(pages_store.categories_store, "get_category", lambda cid: CATEGORY)
        monkeypatch.setattr(pages_store.content_versions, "ensure_writable", lambda *a: None)
        monkeypatch.setattr(pages_store.content_files, "write_page", lambda *a, **k: [])
        monkeypatch.setattr(pages_store.content_files, "relocate_page", lambda *a, **k: [])
        monkeypatch.setattr(pages_store.content_files, "delete_page", lambda *a, **k: ["x.md"])
        monkeypatch.setattr(pages_store.preview_links_store, "repoint_page", lambda *a: None)
        monkeypatch.setattr(pages_store.preview_links_store, "revoke_for_page", lambda *a: None)
        monkeypatch.setattr(pages_store.git_content_repo, "commit_and_push", lambda *a, **k: None)
        monkeypatch.setattr(pages_store.content_sync, "full_sync", lambda: None)
        return events, state

    def test_publishing_a_draft_announces_it(self, fired):
        events, state = fired
        state["page"]["published"] = False
        pages_store.set_published(1, True, "a")
        assert events == ["published"]

    def test_publishing_what_is_already_published_says_nothing(self, fired):
        events, _ = fired
        pages_store.set_published(1, True, "a")  # what the editor does after every save
        assert events == []

    def test_unpublishing_announces_it(self, fired):
        events, _ = fired
        pages_store.set_published(1, False, "a")
        assert events == ["unpublished"]

    def test_editing_a_published_page_announces_an_update(self, fired):
        events, _ = fired
        pages_store.update_page(1, "Installation", "installation", "Neuer Text", 2, "a")
        assert events == ["updated"]

    def test_saving_it_unchanged_says_nothing(self, fired):
        events, _ = fired
        pages_store.update_page(1, PAGE["title"], PAGE["slug"], PAGE["markdown_content"], 2, "a")
        assert events == []

    def test_editing_a_draft_says_nothing(self, fired):
        events, state = fired
        state["page"]["published"] = False
        pages_store.update_page(1, "Installation", "installation", "Neuer Text", 2, "a")
        assert events == []

    def test_deleting_a_published_page_announces_it(self, fired):
        events, _ = fired
        pages_store.delete_page(1, "a")
        assert events == ["unpublished"]


def test_events_that_are_not_switched_on_are_not_sent(monkeypatch):
    monkeypatch.setattr(settings, "webhook_events", frozenset({"published"}))
    submitted = []
    monkeypatch.setattr(webhooks._pool, "submit", lambda *a: submitted.append(a))
    webhooks.notify("updated", PAGE, PROJECT, CATEGORY)
    assert submitted == []
    webhooks.notify("published", PAGE, PROJECT, CATEGORY)
    assert len(submitted) == 1


def test_nothing_is_sent_without_urls(monkeypatch):
    monkeypatch.setattr(settings, "webhook_urls", ())
    submitted = []
    monkeypatch.setattr(webhooks._pool, "submit", lambda *a: submitted.append(a))
    webhooks.notify("published", PAGE, PROJECT, CATEGORY)
    assert submitted == []
