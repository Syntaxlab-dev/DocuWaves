"""The web app manifest (main.py) that makes the site installable."""
import importlib

from fastapi.testclient import TestClient

from tests.test_gap_drafts import world  # noqa: F401 -- the fixture


def test_the_manifest_names_the_site(world):
    c = TestClient(importlib.import_module("app.main").app)
    r = c.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    data = r.json()
    assert data["name"] and data["start_url"] == "/" and data["display"] == "standalone"
    assert {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"} in data["icons"]
    assert data["theme_color"].startswith("#")
