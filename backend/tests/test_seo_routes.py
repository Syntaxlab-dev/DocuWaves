"""The server's copy of the frontend route table.

seo.parse_route mirrors frontend/src/App.tsx. The two have to agree in both
directions: a reading URL the server does not recognise gets the site's
default metadata plus a noindex -- a real page dropped from search results --
and a URL the server recognises that the app does not claims a page exists
where the reader will see a 404.
"""
import pytest

from app.services import seo


@pytest.fixture(autouse=True)
def isolated(content):
    """Every route decision reads the instance's configured languages, so
    each test needs its own content repo rather than whatever happens to sit
    at the default path."""
    return content


@pytest.fixture
def multilingual(content):
    content.site(name="Docs", languages=["de", "en"])
    return content


def kind_of(path: str) -> str:
    return seo.parse_route(path).kind


class TestRouteKinds:
    @pytest.mark.parametrize("path", ["/admin", "/admin/pages", "/admin/tokens"])
    def test_admin_gets_no_metadata(self, path):
        assert kind_of(path) == "admin"

    @pytest.mark.parametrize("path", ["/", ""])
    def test_the_home_page(self, path):
        assert kind_of(path) == "home"

    def test_a_language_prefix_is_still_the_home_page(self, multilingual):
        route = seo.parse_route("/de")
        assert route.kind == "home" and route.lang == "de"

    def test_a_project(self):
        route = seo.parse_route("/p/cachepanel")
        assert route.kind == "project" and route.project == "cachepanel"

    def test_a_category(self):
        route = seo.parse_route("/p/cachepanel/c/getting-started")
        assert route.kind == "category" and route.category == "getting-started"

    def test_a_page(self):
        route = seo.parse_route("/p/cachepanel/pages/installing")
        assert route.kind == "page" and route.page == "installing"

    def test_search_is_not_a_reading_url(self):
        assert kind_of("/search") == "other"

    def test_an_unknown_path_is_not_a_reading_url(self):
        assert kind_of("/nothing/here") == "other"


class TestVersionSegments:
    """A version id sits exactly where `c` and `pages` do, so telling them
    apart is a real ambiguity -- resolved by refusing those two as version
    ids on the way in."""

    def test_a_version_before_the_category(self):
        route = seo.parse_route("/p/cachepanel/v2.0/c/getting-started")
        assert route.kind == "category"
        assert route.version == "v2.0" and route.category == "getting-started"

    def test_a_version_before_the_page(self):
        route = seo.parse_route("/p/cachepanel/v2.0/pages/installing")
        assert route.kind == "page"
        assert route.version == "v2.0" and route.page == "installing"

    def test_a_version_on_its_own_is_the_projects_landing_page(self):
        route = seo.parse_route("/p/cachepanel/v2.0")
        assert route.kind == "project" and route.version == "v2.0"

    def test_a_dotted_version_is_not_mistaken_for_a_file(self):
        """`/p/cachepanel/v2.0` has a dot in its last segment; a rule that
        treated any dotted path as a static file would 404 a real page."""
        assert seo.parse_route("/p/cachepanel/v2.0").kind == "project"


class TestLanguagePrefix:
    def test_travels_with_every_reading_route(self, multilingual):
        route = seo.parse_route("/de/p/cachepanel/pages/installing")
        assert route.kind == "page"
        assert route.lang == "de" and route.page == "installing"

    def test_admin_is_never_prefixed(self, multilingual):
        assert kind_of("/de/admin") == "other"

    def test_only_a_CONFIGURED_code_counts(self, multilingual):
        """`/fr/...` on an instance with no French is a wrong URL, not an
        unprefixed one -- the app answers 404 there, so the metadata must not
        claim the page exists."""
        assert kind_of("/fr/p/cachepanel") == "other"

    def test_a_single_language_instance_has_no_prefixes_at_all(self, content):
        content.site(name="Docs", languages=["de"])
        assert kind_of("/de/p/cachepanel") == "other"


class TestAbsurdInput:
    def test_an_overlong_segment_is_refused_before_any_lookup(self):
        assert kind_of("/p/" + "a" * 5000) == "other"

    def test_repeated_slashes_do_not_shift_the_segments(self):
        assert seo.parse_route("//p//cachepanel//pages//installing").kind == "page"
