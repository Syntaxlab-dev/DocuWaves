"""Which address the rate limits count.

The rule worth pinning down: the address a reverse proxy VOUCHES for (the
rightmost X-Forwarded-For entry) and never the one a caller WRITES itself
(the leftmost). Getting this backwards is how every per-address limit in the
app -- sign-in, chat, feedback -- becomes one fresh bucket per request.
"""
import pytest
from starlette.requests import Request

from app.services.client_address import client_address
from app.settings import settings


def make_request(headers: dict[str, str] | None = None, peer: str = "10.0.0.2") -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (peer, 12345),
    })


@pytest.fixture(autouse=True)
def no_configured_header(monkeypatch):
    monkeypatch.setattr(settings, "client_ip_header", "")


class TestBehindOneProxy:
    def test_uses_the_entry_the_proxy_appended(self):
        # nginx: $proxy_add_x_forwarded_for = "<what the caller sent>, <peer>"
        request = make_request({"X-Forwarded-For": "1.2.3.4, 203.0.113.7"})
        assert client_address(request) == "203.0.113.7"

    def test_a_spoofed_first_entry_does_not_change_the_address(self):
        first = make_request({"X-Forwarded-For": "1.1.1.1, 203.0.113.7"})
        second = make_request({"X-Forwarded-For": "9.9.9.9, 203.0.113.7"})
        assert client_address(first) == client_address(second) == "203.0.113.7"

    def test_a_single_entry_is_used_as_is(self):
        # Caddy replaces the header instead of appending to it.
        assert client_address(make_request({"X-Forwarded-For": "203.0.113.7"})) == "203.0.113.7"

    def test_whitespace_and_trailing_commas_are_tolerated(self):
        assert client_address(make_request({"X-Forwarded-For": " 1.2.3.4 ,  203.0.113.7 "})) == "203.0.113.7"


class TestWithoutAProxy:
    def test_falls_back_to_the_connection_peer(self):
        assert client_address(make_request(peer="198.51.100.5")) == "198.51.100.5"


class TestConfiguredHeader:
    def test_a_configured_header_wins_over_x_forwarded_for(self, monkeypatch):
        monkeypatch.setattr(settings, "client_ip_header", "cf-connecting-ip")
        request = make_request({"CF-Connecting-IP": "192.0.2.44", "X-Forwarded-For": "1.2.3.4, 172.16.0.9"})
        assert client_address(request) == "192.0.2.44"

    def test_a_configured_but_missing_header_falls_back(self, monkeypatch):
        monkeypatch.setattr(settings, "client_ip_header", "cf-connecting-ip")
        assert client_address(make_request({"X-Forwarded-For": "1.2.3.4, 203.0.113.7"})) == "203.0.113.7"
