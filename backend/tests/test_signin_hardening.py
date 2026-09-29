"""Sign-in hardening: SSO accounts bound to the provider's `sub`, a password
change that signs the other sessions out, the session cookie's Secure flag,
and a public site that does not name the chat's model or endpoint."""
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.routers import auth
from app.services import doc_chat, oidc_client
from app.settings import _cookie_secure


# ---- Which claims pick an account ----

class TestClaims:
    def test_subject_is_the_sub_claim(self):
        assert oidc_client.subject_from_claims({"sub": " 1234 "}) == "1234"
        assert oidc_client.subject_from_claims({"preferred_username": "admin"}) is None

    def test_preferred_username_first(self):
        claims = {"preferred_username": "michel", "email": "m@example.com", "email_verified": True}
        assert oidc_client.username_from_claims(claims) == "michel"

    def test_an_unverified_email_is_not_a_username(self):
        assert oidc_client.username_from_claims({"email": "admin@example.com"}) is None
        assert oidc_client.username_from_claims({"email": "admin@example.com", "email_verified": False}) is None

    def test_a_verified_email_is(self):
        assert oidc_client.username_from_claims({"email": "m@example.com", "email_verified": True}) == "m@example.com"


# ---- The callback ----

def callback_request() -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/auth/oidc/callback",
        "query_string": urlencode({"code": "c", "state": "s"}).encode(),
        "headers": [(b"host", b"docs.example.com")],
        "client": ("10.0.0.1", 1),
        "session": {"oidc_state": "s", "oidc_nonce": "n", "oidc_code_verifier": "v"},
    })


@pytest.fixture
def idp(monkeypatch):
    """A fake provider and a fake account table: accounts maps username ->
    bound subject ('' = never signed in via SSO)."""
    state = {"claims": {}, "accounts": {}, "signed_in": []}
    monkeypatch.setattr(oidc_client, "complete_login", lambda *a: state["claims"])
    monkeypatch.setattr(auth.users_store, "is_configured", lambda: bool(state["accounts"]))
    monkeypatch.setattr(auth.users_store, "get_user", lambda u: {"username": u} if u in state["accounts"] else None)
    monkeypatch.setattr(auth.users_store, "oidc_subject", lambda u: state["accounts"].get(u, ""))
    monkeypatch.setattr(auth.users_store, "bind_oidc_subject", lambda u, s: state["accounts"].__setitem__(u, s))
    monkeypatch.setattr(
        auth.users_store, "get_user_by_oidc_subject",
        lambda s: next(({"username": u} for u, b in state["accounts"].items() if b == s), None),
    )
    monkeypatch.setattr(auth.users_store, "create_first_admin", lambda u, p: state["accounts"].__setitem__(u, ""))
    monkeypatch.setattr(auth, "_start_session", lambda request, u: state["signed_in"].append(u))
    return state


def location(response) -> str:
    return response.headers["location"]


class TestCallback:
    def test_first_sso_sign_in_binds_the_account(self, idp):
        idp["accounts"] = {"michel": ""}
        idp["claims"] = {"sub": "abc", "preferred_username": "michel"}
        assert location(auth.oidc_callback(callback_request())) == "/"
        assert idp["accounts"]["michel"] == "abc"
        assert idp["signed_in"] == ["michel"]

    def test_later_sign_ins_go_by_sub_even_if_the_username_changed(self, idp):
        idp["accounts"] = {"michel": "abc"}
        idp["claims"] = {"sub": "abc", "preferred_username": "renamed-at-the-provider"}
        auth.oidc_callback(callback_request())
        assert idp["signed_in"] == ["michel"]

    def test_the_same_username_from_another_identity_does_not_take_the_account(self, idp):
        idp["accounts"] = {"admin": "real-admin-sub"}
        idp["claims"] = {"sub": "attacker-sub", "preferred_username": "admin"}
        assert "oidc_login=failed" in location(auth.oidc_callback(callback_request()))
        assert idp["signed_in"] == []
        assert idp["accounts"]["admin"] == "real-admin-sub"

    def test_an_unverified_email_matches_nothing(self, idp):
        idp["accounts"] = {"admin@example.com": ""}
        idp["claims"] = {"sub": "x", "email": "admin@example.com"}
        assert "oidc_login=failed" in location(auth.oidc_callback(callback_request()))
        assert idp["accounts"]["admin@example.com"] == ""

    def test_no_account_is_still_no_account(self, idp):
        idp["accounts"] = {"someone": ""}
        idp["claims"] = {"sub": "x", "preferred_username": "stranger"}
        assert "oidc_login=no_account" in location(auth.oidc_callback(callback_request()))

    def test_first_run_bootstrap_binds_the_new_admin(self, idp):
        idp["claims"] = {"sub": "first", "preferred_username": "michel"}
        auth.oidc_callback(callback_request())
        assert idp["accounts"] == {"michel": "first"}


# ---- Password change ----

def password_request(origin: str = "https://docs.example.com") -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/password",
        "headers": [(b"host", b"docs.example.com"), (b"origin", origin.encode())],
        "client": ("10.0.0.1", 1),
        "session": {"username": "michel", "session_id": "current"},
    })


class TestPasswordChange:
    @pytest.fixture
    def stores(self, monkeypatch):
        calls = {"revoked": None}
        monkeypatch.setattr(auth.session_registry_store, "exists", lambda sid: sid == "current")
        monkeypatch.setattr(auth.users_store, "verify_credentials", lambda u, p: p == "old password")
        monkeypatch.setattr(auth.users_store, "set_password", lambda u, p: None)
        monkeypatch.setattr(auth.login_throttle, "retry_after", lambda *a: 0)

        def revoke_others(username, keep):
            calls["revoked"] = (username, keep)
            return 2

        monkeypatch.setattr(auth.session_registry_store, "revoke_others", revoke_others)
        return calls

    def test_the_other_sessions_are_signed_out_and_this_one_kept(self, stores):
        body = auth.PasswordChange(current_password="old password", new_password="a new password")
        result = auth.change_password(body, password_request())
        assert stores["revoked"] == ("michel", "current")
        assert result["other_sessions_signed_out"] == 2

    def test_from_another_site_it_is_refused(self, stores):
        body = auth.PasswordChange(current_password="old password", new_password="a new password")
        with pytest.raises(HTTPException) as refused:
            auth.change_password(body, password_request(origin="https://evil.example.net"))
        assert refused.value.status_code == 403
        assert stores["revoked"] is None

    def test_a_revoked_session_cannot_change_it(self, stores, monkeypatch):
        monkeypatch.setattr(auth.session_registry_store, "exists", lambda sid: False)
        body = auth.PasswordChange(current_password="old password", new_password="a new password")
        with pytest.raises(HTTPException) as refused:
            auth.change_password(body, password_request())
        assert refused.value.status_code == 401


# ---- Cookie and public chat status ----

class TestCookieSecure:
    def test_explicit_setting_wins(self):
        assert _cookie_secure("true", "http://lan.local") is True
        assert _cookie_secure("false", "https://docs.example.com") is False

    def test_otherwise_follows_the_public_address(self):
        assert _cookie_secure("", "https://docs.example.com") is True
        assert _cookie_secure("", "http://10.0.0.5:8091") is False
        assert _cookie_secure("", "") is False


def test_the_public_chat_status_names_no_model_or_endpoint(monkeypatch):
    monkeypatch.setattr(doc_chat, "is_enabled", lambda: True)
    public = doc_chat.public_status()
    assert public["enabled"] is True
    assert "model" not in public and "endpoint" not in public
