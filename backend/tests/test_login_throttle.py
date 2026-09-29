"""Brakes on password guessing.

Pinned down here: failures are counted per address AND per username, a
blocked caller is refused BEFORE the (deliberately slow) password check runs,
a correct password clears only its own account's count, and nothing is
blocked for longer than the window.
"""
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.routers import auth
from app.services import login_throttle
from app.settings import settings


@pytest.fixture(autouse=True)
def fresh_counters(monkeypatch):
    login_throttle.reset()
    monkeypatch.setattr(settings, "client_ip_header", "")
    yield
    login_throttle.reset()


def fail(times: int, address: str = "203.0.113.7", username: str = "admin") -> None:
    for _ in range(times):
        login_throttle.record_failure(address, username)


class TestCounting:
    def test_nothing_counted_means_go_ahead(self):
        assert login_throttle.retry_after("203.0.113.7", "admin") == 0

    def test_below_the_address_limit_is_still_allowed(self):
        fail(login_throttle.MAX_FAILURES_PER_ADDRESS - 1)
        assert login_throttle.retry_after("203.0.113.7", "admin") == 0

    def test_the_address_limit_blocks_that_address(self):
        fail(login_throttle.MAX_FAILURES_PER_ADDRESS, username="someone")
        assert login_throttle.retry_after("203.0.113.7", "anyone-else") > 0

    def test_another_address_is_not_affected(self):
        fail(login_throttle.MAX_FAILURES_PER_ADDRESS, username="someone")
        assert login_throttle.retry_after("198.51.100.5", "anyone-else") == 0

    def test_many_addresses_at_one_username_hit_the_username_limit(self):
        for i in range(login_throttle.MAX_FAILURES_PER_USERNAME):
            login_throttle.record_failure(f"10.0.{i // 250}.{i % 250}", "Admin")
        # Case and surrounding spaces do not make a different account.
        assert login_throttle.retry_after("198.51.100.5", " admin ") > 0

    def test_the_wait_never_exceeds_the_window(self):
        fail(login_throttle.MAX_FAILURES_PER_USERNAME)
        assert 0 < login_throttle.retry_after("203.0.113.7", "admin") <= login_throttle.WINDOW_SECONDS + 1

    def test_failures_age_out(self, monkeypatch):
        fail(login_throttle.MAX_FAILURES_PER_ADDRESS)
        real = login_throttle.time.monotonic
        monkeypatch.setattr(login_throttle.time, "monotonic", lambda: real() + login_throttle.WINDOW_SECONDS + 1)
        assert login_throttle.retry_after("203.0.113.7", "admin") == 0

    def test_success_clears_the_account_but_not_the_address(self):
        fail(login_throttle.MAX_FAILURES_PER_ADDRESS)
        login_throttle.record_success("admin")
        assert login_throttle._by_username.get("admin") is None
        assert login_throttle.retry_after("203.0.113.7", "other") > 0


def login_request(address: str = "203.0.113.7") -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "headers": [(b"x-forwarded-for", f"1.2.3.4, {address}".encode())],
        "client": ("10.0.2.2", 5555),
        "session": {},
    })


class TestLoginRoute:
    @pytest.fixture
    def accounts(self, monkeypatch):
        checked = []

        def verify(username, password):
            checked.append(username)
            return password == "correct horse"

        monkeypatch.setattr(auth.users_store, "verify_credentials", verify)
        monkeypatch.setattr(auth.users_store, "touch_login", lambda username: None)
        monkeypatch.setattr(auth.session_registry_store, "create", lambda *args: None)
        return checked

    def test_a_wrong_password_is_counted(self, accounts):
        with pytest.raises(HTTPException) as refused:
            auth.auth_login(auth.Credentials(username="admin", password="nope"), login_request())
        assert refused.value.status_code == 401
        assert len(login_throttle._by_address["203.0.113.7"]) == 1

    def test_a_blocked_caller_is_refused_before_the_password_is_checked(self, accounts):
        fail(login_throttle.MAX_FAILURES_PER_ADDRESS)
        with pytest.raises(HTTPException) as refused:
            auth.auth_login(auth.Credentials(username="admin", password="correct horse"), login_request())
        assert refused.value.status_code == 429
        assert int(refused.value.headers["Retry-After"]) > 0
        assert accounts == []  # bcrypt never ran

    def test_spoofing_x_forwarded_for_does_not_escape_the_limit(self, accounts):
        fail(login_throttle.MAX_FAILURES_PER_ADDRESS)
        request = login_request()
        request.scope["headers"] = [(b"x-forwarded-for", b"8.8.8.8, 203.0.113.7")]
        with pytest.raises(HTTPException) as refused:
            auth.auth_login(auth.Credentials(username="admin", password="nope"), request)
        assert refused.value.status_code == 429

    def test_a_correct_password_signs_in_and_clears_the_account_count(self, accounts):
        fail(3)
        request = login_request()
        assert auth.auth_login(auth.Credentials(username="admin", password="correct horse"), request) == {"ok": True}
        assert request.session["authenticated"] is True
        assert "admin" not in login_throttle._by_username
