"""Footer columns, the "Made with DocuWaves" line and the announcement bar in
_site.yml: each reads back, degrades on a bad hand-edit, and only what was
set is written."""
import yaml

from app.services import site_branding


def test_footer_links_keep_their_column():
    got = site_branding._footer_links(
        {"footer_links": [{"label": "Blog", "url": "https://x.dev/blog", "column": " Company "}, {"label": "Imprint", "url": "/imprint"}]}
    )
    assert got == [{"label": "Blog", "url": "https://x.dev/blog", "column": "Company"}, {"label": "Imprint", "url": "/imprint"}]


def test_powered_by_is_on_unless_explicitly_off():
    assert site_branding._powered_by({}) is True
    assert site_branding._powered_by({"powered_by": "no"}) is True
    assert site_branding._powered_by({"powered_by": False}) is False


def test_announcement_reads_text_and_a_safe_link_only():
    assert site_branding._announcement({}) == {}
    assert site_branding._announcement({"announcement": {"text": "  "}}) == {}
    got = site_branding._announcement({"announcement": {"text": "v3 is out", "link": "javascript:alert(1)"}})
    assert got == {"text": "v3 is out", "text_i18n": {}, "link": ""}
    got = site_branding._announcement({"announcement": {"text": "v3 is out", "link": "/changes"}})
    assert got["link"] == "/changes"


def test_write_and_read_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(site_branding, "site_file", lambda: tmp_path / "_site.yml")
    monkeypatch.setattr(site_branding.settings, "content_repo_path", str(tmp_path))
    site_branding.write_branding(
        {
            "name": "Docs",
            "powered_by": False,
            "announcement": {"text": "Maintenance on Friday", "link": "https://status.example.com"},
            "footer_links": [{"label": "Status", "url": "https://status.example.com", "column": "Help"}],
        }
    )
    written = yaml.safe_load((tmp_path / "_site.yml").read_text())
    assert written["powered_by"] is False
    assert written["announcement"] == {"text": "Maintenance on Friday", "link": "https://status.example.com"}
    assert written["footer_links"][0]["column"] == "Help"
    # Untouched defaults leave no trace in the file.
    site_branding.write_branding({"name": "Docs", "powered_by": True, "announcement": {"text": ""}})
    written = yaml.safe_load((tmp_path / "_site.yml").read_text())
    assert "powered_by" not in written and "announcement" not in written


def test_appearance_defaults_and_bad_values():
    assert site_branding._appearance({}) == {"surface": "cool", "radius": "medium", "header": "plain"}
    got = site_branding._appearance({"appearance": {"surface": "warm", "radius": "huge", "header": "accent"}})
    assert got == {"surface": "warm", "radius": "medium", "header": "accent"}
    assert site_branding._appearance_to_file({"appearance": {"surface": "cool", "radius": "round"}}) == {"radius": "round"}


def test_custom_css_is_kept_and_capped():
    assert site_branding._custom_css({}) == ""
    assert site_branding._custom_css({"custom_css": 3}) == ""
    assert len(site_branding._custom_css({"custom_css": "a" * 50_000})) == 20_000
