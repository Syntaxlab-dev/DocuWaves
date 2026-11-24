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

    @pytest.mark.parametrize("url", [
        "https://contoso.webhook.office.com/webhookb2/x/IncomingWebhook/y/z",
        "https://prod-12.westeurope.logic.azure.com:443/workflows/abc/triggers/manual/paths/invoke?sig=x",
        "https://default123.0a.environment.api.powerplatform.com:443/powerautomate/automations/direct/x",
        "https://example.org/teams-relay#teams",
    ])
    def test_teams_gets_an_adaptive_card(self, url):
        body = webhooks.build_body(url, "published", data())
        attachment = body["attachments"][0]
        assert body["type"] == "message"
        assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
        card = attachment["content"]
        texts = [b["text"] for b in card["body"]]
        assert texts[0] == "Neu veröffentlicht" and texts[1] == "Installation" and texts[-1] == "Demo"
        assert card["actions"][0] == {
            "type": "Action.OpenUrl", "title": "Seite öffnen",
            "url": "https://docs.example.com/p/demo/pages/installation",
        }

    def test_teams_without_a_link_has_no_button(self, monkeypatch):
        monkeypatch.setattr(settings, "public_base_url", "")
        body = webhooks.build_body("https://x.webhook.office.com/a", "published", data())
        assert "actions" not in body["attachments"][0]["content"]

    def test_matrix_gets_a_notice_with_escaped_html(self):
        d = data()
        d["page"]["title"] = "A <b> & C"
        body = webhooks.build_body("https://m.example.org/_matrix/client/v3/rooms/!r:x/send/m.room.message", "updated", d)
        assert body["msgtype"] == "m.notice" and body["format"] == "org.matrix.custom.html"
        assert body["body"].startswith("Aktualisiert: A <b> & C (Demo) https://docs.example.com/")
        assert '<a href="https://docs.example.com/p/demo/pages/installation">A &lt;b&gt; &amp; C</a>' in body["formatted_body"]
        assert body["text"] == body["body"] and body["html"] == body["formatted_body"]

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

        def request(method, url, data, headers, timeout):
            sent.append({"method": method, "url": url, "body": data, "headers": headers})
            return Response(codes.pop(0) if codes else 200)

        monkeypatch.setattr(webhooks.requests, "request", request)
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

        monkeypatch.setattr(webhooks.requests, "request", refuse)
        monkeypatch.setattr(webhooks.time, "sleep", lambda s: None)
        webhooks._deliver("https://example.org/hook", "published", data())  # no exception

    def test_the_log_names_the_host_not_the_secret_path(self):
        assert webhooks._redacted("https://discord.com/api/webhooks/123/SECRET") == "discord.com"

    def test_matrix_is_a_put_with_the_token_in_the_header(self, posts):
        sent, codes = posts
        codes += [502, 200]
        url = "https://matrix.example.org/_matrix/client/v3/rooms/!abc:example.org/send/m.room.message?access_token=TOK"
        webhooks._deliver(url, "published", data())
        first, second = sent
        assert first["method"] == "PUT"
        assert first["url"].startswith("https://matrix.example.org/_matrix/client/v3/rooms/!abc:example.org/send/m.room.message/")
        assert "access_token" not in first["url"] and "TOK" not in first["url"]
        assert first["headers"]["Authorization"] == "Bearer TOK"
        assert first["url"] == second["url"]  # one transaction id: the retry cannot post twice
        assert json.loads(first["body"])["msgtype"] == "m.notice"

    def test_a_format_fragment_is_not_sent(self, posts):
        sent, _ = posts
        webhooks._deliver("https://hookshot.example.org/webhook/abc#matrix", "published", data())
        assert sent[0]["method"] == "POST" and sent[0]["url"] == "https://hookshot.example.org/webhook/abc"
        assert "X-DocuWaves-Event" not in sent[0]["headers"]
        assert json.loads(sent[0]["body"])["text"].startswith("Neu veröffentlicht: Installation")


class TestWhenItFires:
    @pytest.fixture
    def fired(self, monkeypatch):
        events = []
        monkeypatch.setattr(pages_store.webhooks, "notify", lambda event, *a, **kw: events.append(event))
        state = {"page": dict(PAGE)}
        monkeypatch.setattr(pages_store, "get_page", lambda pid: dict(state["page"]))
        monkeypatch.setattr(pages_store, "get_page_by_slug", lambda *a: dict(state["page"]))
        monkeypatch.setattr(pages_store.projects_store, "get_project", lambda pid: PROJECT)
        monkeypatch.setattr(pages_store.categories_store, "get_category", lambda cid: CATEGORY)
        monkeypatch.setattr(pages_store.content_versions, "ensure_writable", lambda *a: None)
        monkeypatch.setattr(pages_store.content_versions, "ensure_editable", lambda *a: None)
        monkeypatch.setattr(pages_store.content_files, "write_page", lambda *a, **k: [])
        monkeypatch.setattr(pages_store.content_files, "relocate_page", lambda *a, **k: [])
        monkeypatch.setattr(pages_store.content_files, "delete_page", lambda *a, **k: ["x.md"])
        monkeypatch.setattr(pages_store.preview_links_store, "repoint_page", lambda *a: None)
        monkeypatch.setattr(pages_store.preview_links_store, "revoke_for_page", lambda *a: None)
        for name in ("repoint_page", "forget_page", "cancel"):
            monkeypatch.setattr(pages_store.scheduled_publish, name, lambda *a: None)
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


class TestReviewEvents:
    """review_requested / review_decided (services/page_review.py): off
    unless named, and never carrying unpublished text."""

    @pytest.fixture
    def submitted(self, monkeypatch):
        monkeypatch.setattr(
            settings, "webhook_events", frozenset({"published", "review_requested", "review_decided"})
        )
        queued = []
        monkeypatch.setattr(webhooks._pool, "submit", lambda fn, url, event, d: queued.append((event, d)))
        return queued

    def test_off_by_default(self, monkeypatch):
        monkeypatch.setattr(settings, "webhook_events", frozenset({"published"}))
        queued = []
        monkeypatch.setattr(webhooks._pool, "submit", lambda *a: queued.append(a))
        webhooks.notify("review_requested", PAGE, PROJECT, CATEGORY, {"kind": "new"})
        assert queued == []

    def test_a_request_for_a_draft_carries_no_text_and_no_public_link(self, submitted):
        draft = {**PAGE, "published": False}
        webhooks.notify("review_requested", draft, PROJECT, CATEGORY, {"kind": "new"})
        event, d = submitted[0]
        assert event == "review_requested"
        assert d["page"]["summary"] == "" and d["page"]["url"] == ""
        assert d["review"] == {"kind": "new"}
        assert d["admin_url"] == "https://docs.example.com/admin"
        assert "So installierst" not in json.dumps(d)

    def test_a_decision_is_labelled_by_its_outcome(self, submitted):
        webhooks.notify("review_decided", PAGE, PROJECT, CATEGORY, {"decision": "changes_requested"})
        _, d = submitted[0]
        body = webhooks.build_body("https://hooks.slack.com/services/x", "review_decided", d)
        assert body["text"].startswith("*Änderungen angefordert:*")
        discord = webhooks.build_body("https://discord.com/api/webhooks/1/abc", "review_decided", d)
        assert discord["embeds"][0]["color"] == 0xDC2626

    def test_never_about_a_private_project(self, submitted):
        webhooks.notify("review_requested", PAGE, {**PROJECT, "private": True}, CATEGORY, {"kind": "change"})
        assert submitted == []
