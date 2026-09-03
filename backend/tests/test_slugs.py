"""Slug allocation.

A slug is a page's public URL, and unique_slug is the one place that decides
it -- for the admin editor and for the MCP endpoint alike. It has already
been the source of one real bug: the rename paths passed the excluded row id
positionally, which put it where the slug belongs and pushed the slug into
`exclude_id`, so a rename could overwrite another project's file. Hence the
keyword-only parameter, and hence these tests.
"""
import pytest

from app.services import content_files


def taken_from(*slugs: str):
    """A taken_fn matching the stores' shape: (project_id, slug, ...) with
    the excluded row id last."""
    recorded: list[tuple] = []

    def taken(project_id, slug, *rest):
        recorded.append((project_id, slug, *rest))
        return slug in slugs

    taken.calls = recorded  # type: ignore[attr-defined]
    return taken


class TestMakeSlug:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Installing with Docker", "installing-with-docker"),
            ("Behind a Reverse Proxy!", "behind-a-reverse-proxy"),
            ("Über Umlaute", "uber-umlaute"),
            ("  spaced  out  ", "spaced-out"),
        ],
    )
    def test_derives_a_url_safe_slug(self, title, expected):
        assert content_files.make_slug(title) == expected


class TestUniqueSlug:
    def test_uses_the_plain_slug_when_it_is_free(self):
        assert content_files.unique_slug("Installation", taken_from(), 1) == "installation"

    def test_suffixes_on_a_collision(self):
        assert content_files.unique_slug("Installation", taken_from("installation"), 1) == "installation-2"

    def test_keeps_counting(self):
        taken = taken_from("installation", "installation-2", "installation-3")
        assert content_files.unique_slug("Installation", taken, 1) == "installation-4"

    def test_passes_the_leading_arguments_through_unchanged(self):
        """The call is taken_fn(*args, slug, exclude_id): whatever the store
        needs first, then the candidate, then the row to ignore."""
        taken = taken_from()
        content_files.unique_slug("Installation", taken, 7, "current")
        assert taken.calls[0] == (7, "current", "installation", None)

    def test_the_excluded_id_goes_last_and_is_keyword_only(self):
        """The positional form is what caused the rename bug: passed that
        way, the id landed where the slug belongs and the slug became
        exclude_id, so taken_fn always answered "free"."""
        taken = taken_from()
        content_files.unique_slug("Installation", taken, 7, exclude_id=42)
        assert taken.calls[0] == (7, "installation", 42)

        # Passed positionally it is an ARGUMENT, not the excluded id -- the
        # shape that used to be silently wrong is now visibly different.
        positional = taken_from()
        content_files.unique_slug("Installation", positional, 7, 42)
        assert positional.calls[0] == (7, 42, "installation", None)

    def test_a_page_keeps_its_own_slug_when_renamed_to_its_own_title(self):
        # taken_fn is told to ignore row 42, so "installation" reads as free.
        def taken(project_id, slug, exclude_id=None):
            return slug == "installation" and exclude_id != 42

        assert content_files.unique_slug("Installation", taken, 1, exclude_id=42) == "installation"
