"""The search widget (frontend/public/widget.js) calls the public search from
other sites; SEARCH_WIDGET_ORIGINS says which may read the answer. Never with
credentials, so another site only ever sees what an anonymous reader sees."""
import pytest
from fastapi import Response
from starlette.requests import Request

from app.routers import public_content
from app.settings import settings


def headers(origin: str | None, allowed: str, monkeypatch) -> dict:
    monkeypatch.setattr(settings, "search_widget_origins", allowed)
    raw = [(b"origin", origin.encode())] if origin else []
    request = Request({"type": "http", "method": "GET", "path": "/api/public/search", "headers": raw})
    response = Response()
    public_content._allow_widget(request, response)
    return dict(response.headers)


def test_any_site_by_default(monkeypatch):
    h = headers("https://www.example.com", "*", monkeypatch)
    assert h["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in h


def test_same_origin_requests_get_no_header(monkeypatch):
    assert "access-control-allow-origin" not in headers(None, "*", monkeypatch)


@pytest.mark.parametrize("allowed", ["off", "OFF", ""])
def test_off_answers_no_other_site(monkeypatch, allowed):
    assert "access-control-allow-origin" not in headers("https://www.example.com", allowed, monkeypatch)


def test_a_list_names_the_sites(monkeypatch):
    allowed = "https://www.example.com, https://shop.example.com/"
    assert headers("https://shop.example.com", allowed, monkeypatch)["access-control-allow-origin"] == "https://shop.example.com"
    other = headers("https://evil.example.net", allowed, monkeypatch)
    assert "access-control-allow-origin" not in other
    assert other["vary"] == "Origin"
