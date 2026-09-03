"""Broken links, and the anchor rule the checker shares with the renderer.

The slugifier here is a second implementation of
frontend/src/lib/headings.ts. If the two ever disagree the checker starts
reporting working links as broken, which is the failure that gets a checker
switched off -- so the cases below are the ones where two slugifiers most
easily drift apart.
"""
import pytest

from app.services import link_check


class TestHeadingIds:
    @pytest.mark.parametrize(
        "markdown,expected",
        [
            ("## Installation", {"installation"}),
            ("## Behind a reverse proxy", {"behind-a-reverse-proxy"}),
            # Punctuation dropped, not replaced -- "it's" must not become "it-s".
            ("## What it's for", {"what-its-for"}),
            # Inline code and emphasis flattened to the text a reader sees.
            # One run of [\s-]+ becomes ONE dash, so " --" collapses to "-".
            ("## Using `--force`", {"using-force"}),
            ("## **Bold** heading", {"bold-heading"}),
            # Non-ASCII letters kept: a German instance's deep links stay
            # readable, and a fragment is percent-encoded either way.
            ("## Fehlerbehebung für Umlaute", {"fehlerbehebung-für-umlaute"}),
            # h1 and h4 are not collected, so nothing links to them.
            ("# Title\n#### Deep", set()),
            # Underscore dropped, not kept: Python's \w would keep it and the
            # browser's \p{L}\p{N} would not, which is exactly where two
            # slugifiers drift apart.
            ("## snake_case_name", {"snakecasename"}),
            ("## Version 2.0 notes", {"version-20-notes"}),
        ],
    )
    def test_matches_the_renderers_rule(self, markdown, expected):
        assert link_check.heading_ids(markdown) == expected

    def test_duplicates_get_the_same_suffixes_the_renderer_hands_out(self):
        ids = link_check.heading_ids("## Setup\n## Setup\n## Setup")
        assert ids == {"setup", "setup-2", "setup-3"}

    def test_a_heading_inside_a_fence_is_code(self):
        assert link_check.heading_ids("```\n## Not a heading\n```") == set()

    def test_a_longer_fence_does_not_close_a_shorter_one(self):
        assert link_check.heading_ids("````\n```\n## Still code\n````\n## Real") == {"real"}


class TestTargets:
    def test_finds_links_and_images(self):
        found = link_check._targets("See [docs](/p/x/pages/y) and ![shot](../assets/a.png).")
        assert found == ["/p/x/pages/y", "../assets/a.png"]

    def test_ignores_a_url_inside_a_code_sample(self):
        assert link_check._targets("```\n[x](/p/gone)\n```") == []

    def test_tolerates_a_link_title(self):
        assert link_check._targets('[x](/p/a/pages/b "A title")') == ["/p/a/pages/b"]

    def test_tolerates_angle_brackets(self):
        assert link_check._targets("[x](</p/a/pages/b>)") == ["/p/a/pages/b"]
