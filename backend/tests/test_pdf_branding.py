"""The `pdf:` block of _site.yml: how a printed manual looks. Every key always
reads back, a bad hand-edit falls back to its default, and an untouched
instance's file gets no block at all."""
import yaml

from app.services import site_branding

DEFAULTS = {"template": "classic", "header": "", "footer": "", "page_numbers": True, "logo": True}


def test_nothing_configured_reads_as_the_defaults():
    assert site_branding._pdf({}) == DEFAULTS
    assert site_branding._pdf({"pdf": "nonsense"}) == DEFAULTS


def test_a_full_setup_reads_back():
    raw = {"template": "band", "header": "{project} {version}", "footer": "ACME GmbH", "page_numbers": False, "logo": False}
    assert site_branding._pdf({"pdf": raw}) == raw


def test_wrong_values_fall_back_one_by_one():
    got = site_branding._pdf({"pdf": {"template": "fancy", "header": 7, "page_numbers": "yes", "footer": "ok"}})
    assert got == {**DEFAULTS, "footer": "ok"}


def test_header_is_one_short_line():
    got = site_branding._pdf({"pdf": {"header": "a\n  b\tc" + "x" * 500}})
    assert got["header"].startswith("a b c")
    assert len(got["header"]) == 200


def test_only_changes_are_written():
    assert site_branding._pdf_to_file({}) == {}
    assert site_branding._pdf_to_file({"pdf": dict(DEFAULTS)}) == {}
    assert site_branding._pdf_to_file({"pdf": {**DEFAULTS, "footer": "Confidential"}}) == {"footer": "Confidential"}


def test_write_and_read_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(site_branding, "site_file", lambda: tmp_path / "_site.yml")
    monkeypatch.setattr(site_branding.settings, "content_repo_path", str(tmp_path))
    site_branding.write_branding({"name": "Docs", "pdf": {"template": "minimal", "footer": "ACME"}})
    written = yaml.safe_load((tmp_path / "_site.yml").read_text())
    assert written["pdf"] == {"template": "minimal", "footer": "ACME"}
    assert site_branding._pdf(written) == {**DEFAULTS, "template": "minimal", "footer": "ACME"}
