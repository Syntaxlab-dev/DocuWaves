"""Frozen versions, and where a version's content lives.

ensure_writable is the guard every write path goes through. If it ever
stopped raising, a released version's documentation could be rewritten
through the API while the admin UI still hid the controls -- the failure
would be silent, and it would change what a shipped release says.
"""
import pytest

from app.services import content_versions
from app.services.content_versions import FrozenVersionError


class TestUnversionedProject:
    def test_has_no_versions(self, content):
        content.project("demo")
        assert content_versions.is_versioned("demo") is False
        assert content_versions.version_ids("demo") == []

    def test_default_and_writable_are_both_the_project_itself(self, content):
        content.project("demo")
        assert content_versions.default_version("demo") == ""
        assert content_versions.writable_version("demo") == ""
        assert content_versions.content_dir("demo") == content.content_dir("demo")

    def test_its_single_implicit_version_is_never_frozen(self, content):
        content.project("demo")
        assert content_versions.is_frozen("demo", "") is False
        content_versions.ensure_writable("demo", "")  # must not raise


class TestVersionedProject:
    @pytest.fixture
    def demo(self, content):
        content.project("demo")
        content.versions("demo", default="current", frozen=["v2.0", "v1.0"])
        return content

    def test_writes_go_to_current(self, demo):
        assert content_versions.writable_version("demo") == "current"

    def test_content_dir_descends_into_the_version(self, demo):
        assert content_versions.content_dir("demo", "v1.0") == demo.content_dir("demo", "v1.0")

    def test_a_blank_version_means_the_default(self, demo):
        assert content_versions.content_dir("demo") == demo.content_dir("demo", "current")

    def test_current_is_writable(self, demo):
        assert content_versions.is_frozen("demo", "current") is False
        content_versions.ensure_writable("demo", "current")  # must not raise

    def test_a_released_version_is_frozen(self, demo):
        assert content_versions.is_frozen("demo", "v1.0") is True

    def test_writing_to_a_frozen_version_raises_and_says_where_to_edit(self, demo):
        with pytest.raises(FrozenVersionError) as caught:
            content_versions.ensure_writable("demo", "v1.0")
        message = str(caught.value)
        assert "frozen" in message
        assert "content/demo/v1.0/" in message  # the path to edit by hand

    def test_a_version_that_does_not_exist_is_not_treated_as_frozen(self, demo):
        # Not frozen, because it is not a version at all -- the caller's own
        # lookup is what refuses it, not this guard.
        assert content_versions.is_frozen("demo", "v9.9") is False


class TestVersionIds:
    def test_normalizes_a_reasonable_id(self):
        assert content_versions.normalize_id("  V2.0  ") == "v2.0"

    @pytest.mark.parametrize("reserved", ["c", "pages"])
    def test_refuses_the_segments_a_url_already_uses(self, content, reserved):
        """`/p/demo/c/...` and `/p/demo/pages/...` are fixed URL segments, so
        a version with either id could not be told apart from them."""
        content.project("demo")
        assert content_versions.rejection_reason("demo", reserved, "Label") is not None

    def test_refuses_an_id_that_already_exists(self, content):
        content.project("demo").category("demo", "guide", version="current")
        content.versions("demo", default="current", frozen=["v1.0"])
        assert content_versions.rejection_reason("demo", "v1.0", "Label") is not None

    def test_refuses_a_project_with_nothing_in_it(self, content):
        """A freeze snapshots the working version's content; with none there
        is nothing to snapshot, and an empty frozen version would only look
        like a release that lost its documentation."""
        content.project("demo")
        assert content_versions.rejection_reason("demo", "v1.0", "Label") is not None

    def test_accepts_a_fresh_id(self, content):
        content.project("demo").category("demo", "guide", version="current")
        content.versions("demo", default="current", frozen=["v1.0"])
        assert content_versions.rejection_reason("demo", "v2.0", "Label") is None
