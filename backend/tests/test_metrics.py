"""The Prometheus endpoint (services/metrics.py): off without a token, only
for the bearer of the token, and the content numbers it reports."""
import importlib

from fastapi.testclient import TestClient

from app.services import metrics
from app.settings import settings

from tests.test_gap_drafts import world  # noqa: F401 -- the fixture


def client() -> TestClient:
    return TestClient(importlib.import_module("app.main").app)


def test_off_without_a_token(world, monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", "")
    assert client().get("/metrics", headers={"Authorization": "Bearer x"}).status_code == 404


def test_only_for_the_token(world, monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", "geheim-123")
    c = client()
    assert c.get("/metrics").status_code == 404
    assert c.get("/metrics", headers={"Authorization": "Bearer falsch"}).status_code == 404
    assert c.get("/metrics", headers={"Authorization": "Basic geheim-123"}).status_code == 404
    assert c.get("/metrics", headers={"Authorization": "Bearer geheim-123"}).status_code == 200


def test_the_numbers(world, monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", "geheim-123")
    c = client()
    c.get("/health")
    c.get("/api/public/site")
    response = c.get("/metrics", headers={"Authorization": "Bearer geheim-123"})
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    text = response.text
    assert "# TYPE docuwaves_http_requests_total counter" in text
    assert 'docuwaves_http_requests_total{method="GET",status="200"}' in text
    assert "docuwaves_projects 1" in text
    assert 'docuwaves_pages{state="published"} 1' in text
    assert 'docuwaves_pages{state="draft"} 0' in text
    assert 'docuwaves_accounts{role="admin"} 1' in text
    assert "docuwaves_content_index_last_rebuild_seconds " in text
    assert "docuwaves_http_request_duration_seconds_count " in text
    assert 'docuwaves_info{version="' in text


def test_label_values_are_escaped():
    assert metrics._labels({"a": 'x"y\\z\n'}) == '{a="x\\"y\\\\z\\n"}'


def test_unknown_methods_are_one_label(monkeypatch):
    monkeypatch.setattr(metrics, "_requests", {})
    metrics.record("BREW", 418, 0.1)
    assert metrics._requests == {("OTHER", "418"): 1}
