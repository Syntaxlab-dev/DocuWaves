"""The two analytics fields, and everything they refuse.

This validator is the only place in the app where a value an operator typed
(or a contributor sent in a pull request to `_site.yml`) ends up inside a
`src` attribute in the head of every public page. So the interesting tests
are the rejections, not the acceptance.
"""
import pytest

from app.services import seo, site_branding


def analytics(url, website_id=None):
    payload = {"umami_url": url}
    if website_id is not None:
        payload["umami_website_id"] = website_id
    return site_branding._analytics({"analytics": payload})


VALID_URL = "https://umami.example.com/script.js"
VALID_ID = "2f4a1b0c-1111-2222-3333-444455556666"


class TestAccepted:
    def test_a_plain_umami_setup(self):
        assert analytics(VALID_URL, VALID_ID) == {"umami_url": VALID_URL, "umami_website_id": VALID_ID}

    @pytest.mark.parametrize(
        "url",
        [
            "http://umami.lan/script.js",              # a homelab instance on plain http
            "https://umami.example.com:3000/s.js",     # a port
            "https://example.com/stats/umami/x.js",    # a sub-path
        ],
    )
    def test_real_shapes_of_a_self_hosted_instance(self, url):
        assert analytics(url, VALID_ID)["umami_url"] == url

    def test_whitespace_is_trimmed_rather_than_refused(self):
        assert analytics(f"  {VALID_URL}  ", f" {VALID_ID} ")["umami_website_id"] == VALID_ID


class TestRejected:
    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)//x.js",                    # not a URL to a file
            "data:text/javascript,alert(1)//x.js",
            "//evil.example.com/x.js",                      # protocol-relative
            "https://umami.example.com/script.php",         # not a script file
            "https://umami.example.com/",                   # no file at all
            'https://a.example.com/x.js" onerror="alert(1)',  # attribute break-out
            "https://a.example.com/x.js onload=x",
            "ftp://example.com/x.js",
            "",
        ],
    )
    def test_a_url_that_is_not_a_script_url(self, url):
        assert analytics(url, VALID_ID) == {}

    @pytest.mark.parametrize(
        "website_id",
        ['a" onload="x', "short", "id with spaces", "<script>", "", "x" * 65],
    )
    def test_a_website_id_that_is_not_a_plain_token(self, website_id):
        assert analytics(VALID_URL, website_id) == {}

    def test_half_a_pair_is_no_pair(self):
        """A script URL with no id loads a counter that reports nowhere, and
        an id with no URL loads nothing -- either one would sit in the
        settings page looking configured."""
        assert analytics(VALID_URL) == {}
        assert site_branding._analytics({"analytics": {"umami_website_id": VALID_ID}}) == {}

    def test_a_wrong_type_in_the_file_degrades_to_off(self):
        """`_site.yml` is hand-editable and takes pull requests: nothing in
        it may raise, ever (see the module docstring)."""
        for raw in ["on", ["yes"], 42, None, {"umami_url": 1, "umami_website_id": 2}]:
            assert site_branding._analytics({"analytics": raw}) == {}


class TestTheTagItself:
    BRANDING = {"analytics": {"umami_url": VALID_URL, "umami_website_id": VALID_ID}}

    def test_carries_both_values_and_the_do_not_track_flag(self):
        tag = seo.render_analytics(self.BRANDING, "p/demo/pages/install")
        assert VALID_URL in tag and VALID_ID in tag
        assert 'data-do-not-track="true"' in tag
        assert tag.strip().startswith("<script defer")

    def test_nothing_at_all_when_unconfigured(self):
        assert seo.render_analytics({}, "p/demo") == ""
        assert seo.render_analytics({"analytics": {}}, "p/demo") == ""

    @pytest.mark.parametrize("path", ["preview/dwp_abc", "/preview/dwp_abc"])
    def test_a_preview_link_is_never_measured(self, path):
        """A preview link is a draft somebody was sent personally. Counting
        the view would put a private page's address, and the fact that it was
        read, into a dashboard -- neither of which is what the link is for."""
        assert seo.render_analytics(self.BRANDING, path) == ""

    def test_ordinary_reading_urls_are(self):
        for path in ["", "search", "p/demo", "de/p/demo/pages/x"]:
            assert seo.render_analytics(self.BRANDING, path) != ""
