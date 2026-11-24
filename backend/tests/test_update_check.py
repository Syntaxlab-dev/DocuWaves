"""The admin area's "a newer DocuWaves exists" notice (services/update_check.py)."""
import pytest
import requests

from app import version
from app.services import update_check
from app.settings import settings


class FakeResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._data


@pytest.fixture
def github(monkeypatch):
    """Counts calls and answers with whatever `release` is set to."""
    state = {"calls": 0, "release": {"tag_name": "v1.2.0", "html_url": "https://github.com/x/releases/v1.2.0"}}

    def fake_get(url, **kwargs):
        state["calls"] += 1
        assert url == update_check.RELEASES_URL
        if isinstance(state["release"], Exception):
            raise state["release"]
        return FakeResponse(state["release"])

    monkeypatch.setattr(update_check.requests, "get", fake_get)
    monkeypatch.setattr(update_check, "_cache", {"at": 0.0, "ttl": 0, "release": None})
    monkeypatch.setattr(settings, "update_check_enabled", True)
    monkeypatch.setattr(version, "VERSION", "1.0.0")
    return state


def test_an_older_release_is_told(github):
    status = update_check.status()
    assert status["newer"] is True
    assert status["latest"] == "1.2.0"
    assert status["url"].endswith("v1.2.0")


def test_the_current_release_is_not(github, monkeypatch):
    monkeypatch.setattr(version, "VERSION", "1.2.0")
    assert update_check.status()["newer"] is False


def test_a_newer_than_released_build_is_not(github, monkeypatch):
    monkeypatch.setattr(version, "VERSION", "1.10.0")
    assert update_check.status()["newer"] is False


def test_github_is_asked_once_a_day(github):
    update_check.status()
    update_check.status()
    assert github["calls"] == 1


@pytest.mark.parametrize("current", ["dev", "latest"])
def test_builds_without_a_number_never_ask(github, monkeypatch, current):
    monkeypatch.setattr(version, "VERSION", current)
    assert update_check.status()["newer"] is False
    assert github["calls"] == 0


def test_switched_off_sends_nothing(github, monkeypatch):
    monkeypatch.setattr(settings, "update_check_enabled", False)
    status = update_check.status()
    assert status == {"enabled": False, "current": "1.0.0", "latest": None, "url": None, "newer": False}
    assert github["calls"] == 0


def test_no_internet_means_no_notice(github):
    github["release"] = requests.ConnectionError("offline")
    assert update_check.status()["newer"] is False


def test_a_pre_release_is_not_offered(github):
    github["release"] = {"tag_name": "v2.0.0-rc1", "html_url": "x"}
    assert update_check.status()["newer"] is False
