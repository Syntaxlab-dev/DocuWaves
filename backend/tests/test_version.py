"""Which DocuWaves an instance is: build arguments in, "dev" without them."""
import importlib

import pytest

from app import version


@pytest.fixture
def reload_version(monkeypatch):
    def load(**env):
        for name in ("DOCUWAVES_VERSION", "DOCUWAVES_REVISION"):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return importlib.reload(version)

    yield load
    monkeypatch.delenv("DOCUWAVES_VERSION", raising=False)
    monkeypatch.delenv("DOCUWAVES_REVISION", raising=False)
    importlib.reload(version)


def test_a_checkout_run_by_hand_says_dev(reload_version):
    v = reload_version()
    assert v.VERSION == "dev"
    assert v.REVISION == ""
    assert v.describe() == "dev"


def test_an_empty_build_argument_also_says_dev(reload_version):
    # `docker compose build` passes the ARG's empty default through to ENV.
    v = reload_version(DOCUWAVES_VERSION="", DOCUWAVES_REVISION="")
    assert v.describe() == "dev"


def test_a_release_build_names_its_version_and_commit(reload_version):
    v = reload_version(DOCUWAVES_VERSION="1.0.0", DOCUWAVES_REVISION="0f651bfbed76d403c1ab9ef417eed3bcd1601081")
    assert v.VERSION == "1.0.0"
    assert v.describe() == "1.0.0 (0f651bf)"


def test_diagnostics_report_the_version(reload_version, monkeypatch):
    reload_version(DOCUWAVES_VERSION="latest", DOCUWAVES_REVISION="a3ea77469938966f69e4576b36640450e8d9a834")
    from app.services import diagnostics

    # Only the instance section: the others need a database.
    instance = diagnostics._instance()
    assert instance["version"] == "latest"
    assert instance["revision"].startswith("a3ea774")
