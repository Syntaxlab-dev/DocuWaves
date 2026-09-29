"""The whole application has to import.

Most tests here import only the module they are about, so a broken import in
a router nobody's test touches -- a misplaced line, a name that no longer
exists -- passed the suite while the app itself could not start. Importing
app.main pulls in every router and service the server loads, which turns
that into a failing test instead of a container that will not boot.
"""
import importlib

import pytest

from app.services import session_secret


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    # main.py creates the session signing key at import time, under /data in
    # the container. Anywhere else that directory does not exist.
    monkeypatch.setattr(session_secret, "_SECRET_PATH", tmp_path / ".session_secret")
    return importlib.import_module("app.main")


def test_the_application_imports(app_module):
    assert app_module.app is not None


def test_every_router_is_registered(app_module):
    # The OpenAPI document lists every route of every included router -- one
    # endpoint from each router is enough to know it was mounted at all.
    paths = app_module.app.openapi()["paths"]
    for expected in ("/api/public/site", "/api/auth/login", "/api/admin/pages/{page_id}", "/api/mcp"):
        assert expected in paths, expected
