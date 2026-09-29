"""Cookie-authenticated changes must come from this site's own pages.

SameSite=Lax lets a sibling subdomain (same "site" to the browser) send the
admin cookie along, and a body-less POST such as publishing a page needs no
more than a form. The Origin header closes that; requests from non-browser
clients (no Origin, no Referer) carry no ambient cookie and pass.
"""
import pytest
from starlette.requests import Request

from app.services.same_origin import is_same_origin
from app.settings import settings


def make_request(headers: dict[str, str]) -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/admin/pages/1/publish",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    })


@pytest.fixture(autouse=True)
def no_base_url(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "")


def test_the_sites_own_page_is_allowed():
    assert is_same_origin(make_request({"Host": "docs.example.com", "Origin": "https://docs.example.com"}))


def test_another_site_is_refused():
    assert not is_same_origin(make_request({"Host": "docs.example.com", "Origin": "https://evil.example.net"}))


def test_a_sibling_subdomain_is_refused():
    # Same SITE to the browser (so the Lax cookie is sent), different origin.
    assert not is_same_origin(make_request({"Host": "docs.example.com", "Origin": "https://example.com"}))


def test_a_referer_is_used_when_there_is_no_origin():
    assert is_same_origin(make_request({"Host": "docs.example.com", "Referer": "https://docs.example.com/admin"}))
    assert not is_same_origin(make_request({"Host": "docs.example.com", "Referer": "https://evil.example.net/x"}))


def test_a_client_that_sends_neither_is_let_through():
    assert is_same_origin(make_request({"Host": "docs.example.com"}))


def test_the_null_origin_is_refused():
    assert not is_same_origin(make_request({"Host": "docs.example.com", "Origin": "null"}))


def test_the_forwarded_host_counts_behind_a_proxy():
    request = make_request({"Host": "127.0.0.1:3002", "X-Forwarded-Host": "docs.example.com", "Origin": "https://docs.example.com"})
    assert is_same_origin(request)


def test_the_configured_public_address_counts(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://docs.example.com")
    assert is_same_origin(make_request({"Host": "127.0.0.1:3002", "Origin": "https://docs.example.com"}))
