"""The installer's setup code (SETUP_TOKEN): with one configured, the first
admin account is only created by whoever has it -- neither by a setup request
without it nor by a first SSO sign-in."""
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.routers import auth
from app.services import login_throttle, oidc_client
from app.settings import settings

from tests.test_signin_hardening import callback_request, idp, location  # noqa: F401 (fixture)


def setup_request() -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/setup",
        "query_string": b"",
        "headers": [(b"host", b"docs.example.com")],
        "client": ("10.0.0.7", 1),
        "session": {},
    })


@pytest.fixture
def instance(monkeypatch):
    """An unconfigured instance; created lists the admin accounts made."""
    created: list[str] = []
    login_throttle.reset()
    monkeypatch.setattr(auth, "_refuse_cross_site", lambda request: None)
    monkeypatch.setattr(auth.users_store, "is_configured", lambda: bool(created))
    monkeypatch.setattr(auth.users_store, "create_first_admin", lambda u, p: created.append(u))
    monkeypatch.setattr(auth, "_start_session", lambda request, u: None)
    yield created
    login_throttle.reset()


def body(token: str = "") -> auth.SetupCredentials:
    return auth.SetupCredentials(username="admin", password="long enough", setup_token=token)


class TestWithoutACode:
    def test_setup_works_as_it_always_did(self, instance, monkeypatch):
        monkeypatch.setattr(settings, "setup_token", "")
        assert auth.auth_setup(body(), setup_request()) == {"ok": True}
        assert instance == ["admin"]

    def test_status_does_not_ask_for_one(self, instance, monkeypatch):
        monkeypatch.setattr(settings, "setup_token", "")
        assert auth.auth_status(setup_request())["setup_token_required"] is False


class TestWithACode:
    @pytest.fixture(autouse=True)
    def code(self, monkeypatch):
        monkeypatch.setattr(settings, "setup_token", "k3J9-correct-code")

    def test_status_asks_for_it(self, instance):
        assert auth.auth_status(setup_request())["setup_token_required"] is True

    def test_the_right_code_sets_up(self, instance):
        assert auth.auth_setup(body("k3J9-correct-code"), setup_request()) == {"ok": True}
        assert instance == ["admin"]

    def test_surrounding_spaces_from_a_paste_do_not_matter(self, instance):
        auth.auth_setup(body("  k3J9-correct-code \n"), setup_request())
        assert instance == ["admin"]

    @pytest.mark.parametrize("token", ["", "k3J9-wrong-code", "k3j9-correct-code"])
    def test_anything_else_is_refused(self, instance, token):
        with pytest.raises(HTTPException) as refused:
            auth.auth_setup(body(token), setup_request())
        assert refused.value.status_code == 403
        assert refused.value.detail == "setup_token_invalid"
        assert instance == []

    def test_guessing_is_throttled(self, instance):
        for _ in range(login_throttle.MAX_FAILURES_PER_ADDRESS):
            with pytest.raises(HTTPException):
                auth.auth_setup(body("guess"), setup_request())
        with pytest.raises(HTTPException) as refused:
            auth.auth_setup(body("k3J9-correct-code"), setup_request())
        assert refused.value.status_code == 429
        assert instance == []

    def test_a_first_sso_sign_in_does_not_claim_the_instance(self, idp):
        idp["claims"] = {"sub": "abc", "preferred_username": "michel"}
        assert location(auth.oidc_callback(callback_request())) == "/?oidc_login=setup_token"
        assert idp["accounts"] == {}
        assert idp["signed_in"] == []

    def test_once_set_up_sso_binds_as_usual(self, idp):
        idp["accounts"] = {"michel": ""}
        idp["claims"] = {"sub": "abc", "preferred_username": "michel"}
        assert location(auth.oidc_callback(callback_request())) == "/"
        assert idp["accounts"]["michel"] == "abc"
