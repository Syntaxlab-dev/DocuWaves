"""E-mail notifications (services/mail_notifications.py, services/mailer.py):
who gets which message, what a message says and never says, and the
account settings behind it."""
import importlib

import pytest
from fastapi.testclient import TestClient

from app.services import db, mail_notifications, mailer, session_secret, users_store, webhooks
from app.settings import settings

ORIGIN = {"Origin": "http://testserver"}
PAGE = {"title": "Installation", "slug": "installation", "published": False, "markdown_content": "SECRET DRAFT TEXT"}
PROJECT = {"name": "Handbuch", "slug": "handbuch", "private": True}


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_path", str(tmp_path / "index.db"))
    monkeypatch.setattr(settings, "public_base_url", "https://docs.example.com")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "DocuWaves <docs@example.com>")
    monkeypatch.setattr(settings, "webhook_urls", ())
    monkeypatch.setattr(session_secret, "_SECRET_PATH", tmp_path / ".session_secret")
    db.init_schema()
    users_store.create_first_admin("chef", "chef-passwort-123")
    users_store.create_user("anna", "anna-passwort-123", users_store.EDITOR)
    users_store.create_user("rolf", "rolf-passwort-123", users_store.VIEWER)
    users_store.create_user("lea", "lea-passwort-123", users_store.READER)
    every = list(mail_notifications.KINDS)
    for name in ("chef", "anna", "rolf", "lea"):
        users_store.set_notifications(name, f"{name}@example.com", every)
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, text: sent.append((to, subject, text)))
    return sent


def to(sent):
    return sorted(address for address, _, _ in sent)


class TestWhoGetsWhat:
    def test_a_review_request_goes_to_everyone_but_the_submitter_and_readers(self, accounts):
        webhooks.notify("review_requested", PAGE, PROJECT, None, {"kind": "new"}, actor="anna")
        assert to(accounts) == ["chef@example.com", "rolf@example.com"]

    def test_a_decision_goes_to_the_submitter_only(self, accounts):
        webhooks.notify(
            "review_decided", PAGE, PROJECT, None, {"decision": "changes_requested"},
            actor="rolf", submitter="anna", comment="Bitte Schritt 2 prüfen.",
        )
        assert to(accounts) == ["anna@example.com"]
        _, subject, text = accounts[0]
        assert subject.startswith("Changes requested") or subject.startswith("Änderungen angefordert")
        assert "Bitte Schritt 2 prüfen." in text

    def test_a_change_goes_to_everyone_but_who_made_it(self, accounts):
        webhooks.notify("published", {**PAGE, "published": True}, PROJECT, None, actor="chef")
        assert to(accounts) == ["anna@example.com", "rolf@example.com"]

    def test_only_what_was_chosen(self, accounts):
        users_store.set_notifications("rolf", "rolf@example.com", ["review_requested"])
        webhooks.notify("updated", {**PAGE, "published": True}, PROJECT, None, actor="chef")
        assert "rolf@example.com" not in to(accounts)

    def test_nothing_without_an_smtp_server(self, accounts, monkeypatch):
        monkeypatch.setattr(settings, "smtp_host", "")
        webhooks.notify("published", PAGE, PROJECT, None, actor="chef")
        assert accounts == []

    def test_a_failure_never_reaches_the_save(self, accounts, monkeypatch):
        def broken():
            raise RuntimeError("database gone")

        monkeypatch.setattr(users_store, "notification_accounts", broken)
        webhooks.notify("published", PAGE, PROJECT, None, actor="chef")  # does not raise


class TestWhatAMessageSays:
    def test_never_the_page_s_text(self, accounts):
        webhooks.notify("review_requested", PAGE, PROJECT, None, {"kind": "new"}, actor="anna")
        for _, subject, text in accounts:
            assert "SECRET DRAFT TEXT" not in subject + text
            assert "Installation" in subject
            assert "anna" in text

    def test_a_draft_links_to_the_admin_area_a_live_page_to_itself(self, accounts):
        webhooks.notify("review_requested", PAGE, PROJECT, None, {"kind": "new"}, actor="anna")
        assert "https://docs.example.com/admin" in accounts[0][2]

    def test_the_subject_is_one_line_whatever_the_title(self):
        message = mailer.build("a@example.com", "Neu: Zeile 1\r\nBcc: evil@example.com", "x")
        assert "\n" not in message["Subject"] and "\r" not in message["Subject"]
        assert message["Bcc"] is None
        assert message["Auto-Submitted"] == "auto-generated"


def test_the_webhook_payload_never_carries_who_or_the_comment(accounts, monkeypatch):
    monkeypatch.setattr(settings, "webhook_urls", ("https://hooks.example.com/x",))
    monkeypatch.setattr(settings, "webhook_events", frozenset({"review_decided"}))
    queued = []
    monkeypatch.setattr(webhooks._pool, "submit", lambda fn, url, event, data: queued.append(data))
    public = {**PROJECT, "private": False}
    webhooks.notify(
        "review_decided", PAGE, public, None, {"decision": "changes_requested"},
        actor="rolf", submitter="anna", comment="intern",
    )
    assert queued and "rolf" not in str(queued[0]) and "anna" not in str(queued[0]) and "intern" not in str(queued[0])


class TestDelivery:
    @pytest.fixture
    def server(self, monkeypatch):
        calls = []

        class FakeSMTP:
            def __init__(self, host, port, timeout=None, context=None):
                calls.append(("connect", host, port))

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def starttls(self, context=None):
                calls.append(("starttls",))

            def login(self, user, password):
                calls.append(("login", user))

            def send_message(self, message):
                calls.append(("send", message["To"]))

        monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
        monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", 0)
        monkeypatch.setattr(settings, "smtp_username", "docs@example.com")
        monkeypatch.setattr(settings, "smtp_password", "pw")
        monkeypatch.setattr(settings, "smtp_from", "")
        return calls

    def test_starttls_on_587_by_default(self, server, monkeypatch):
        monkeypatch.setattr(settings, "smtp_security", "starttls")
        mailer.deliver(mailer.build("a@example.com", "s", "t"))
        assert server == [("connect", "smtp.example.com", 587), ("starttls",), ("login", "docs@example.com"), ("send", "a@example.com")]

    def test_ssl_on_465_and_no_starttls(self, server, monkeypatch):
        monkeypatch.setattr(settings, "smtp_security", "ssl")
        mailer.deliver(mailer.build("a@example.com", "s", "t"))
        assert server[0] == ("connect", "smtp.example.com", 465)
        assert ("starttls",) not in server

    def test_the_username_is_the_sender_when_none_is_set(self, server):
        assert mailer.sender() == "docs@example.com"
        assert mailer.is_enabled()


class TestAccountSettings:
    @pytest.fixture
    def app(self, accounts):
        return importlib.import_module("app.main").app

    def signed_in(self, app, name="rolf", password="rolf-passwort-123"):
        c = TestClient(app)
        assert c.post("/api/auth/login", json={"username": name, "password": password}, headers=ORIGIN).status_code == 200
        return c

    def test_read_and_write_your_own(self, app):
        c = self.signed_in(app)
        r = c.put("/api/auth/notifications", json={"email": "r@example.com", "notify": ["changed"]}, headers=ORIGIN)
        assert r.status_code == 200, r.text
        got = c.get("/api/auth/notifications").json()
        assert got["email"] == "r@example.com" and got["notify"] == ["changed"] and got["enabled"] is True

    @pytest.mark.parametrize(
        "body",
        [
            {"email": "not-an-address", "notify": []},
            {"email": "a@example.com\r\nBcc: x@example.com", "notify": []},
            {"email": "", "notify": ["changed"]},
            {"email": "a@example.com", "notify": ["everything"]},
        ],
    )
    def test_refused(self, app, body):
        c = self.signed_in(app)
        assert c.put("/api/auth/notifications", json=body, headers=ORIGIN).status_code == 400

    def test_not_without_signing_in(self, app):
        assert TestClient(app).get("/api/auth/notifications").status_code == 401

    def test_not_from_another_site(self, app):
        c = self.signed_in(app)
        r = c.put("/api/auth/notifications", json={"email": "", "notify": []}, headers={"Origin": "https://evil.example"})
        assert r.status_code == 403

    def test_the_test_mail_reports_a_refusal_by_kind(self, app, monkeypatch):
        c = self.signed_in(app)

        def refuse(message):
            raise mailer.smtplib.SMTPAuthenticationError(535, b"bad password pw")

        monkeypatch.setattr(mailer, "deliver", refuse)
        r = c.post("/api/auth/notifications/test", headers=ORIGIN)
        assert r.status_code == 502
        assert r.json()["detail"].endswith("SMTPAuthenticationError")
