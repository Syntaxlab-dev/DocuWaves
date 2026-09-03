"""Markdown -> prose, and the window a search result shows.

These are pure functions over strings, so they need no fixture at all.
"""
from app.services import prose

PAGE = """---
title: Ignored
---

# Installing with Docker

![badge](https://example.com/b.svg)

Three commands, and a [fourth step](/p/x) if you want a remote.

```bash
docker compose up -d --build
```

| Setting | Purpose |
|---|---|
| `SQLITE_PATH` | Where the index lives. |

> Back the volume up.
"""


class TestToProse:
    def test_drops_the_markup_and_keeps_the_words(self):
        text = prose.to_prose(PAGE)
        assert "Installing with Docker" in text  # heading text kept
        assert "#" not in text
        assert "fourth step" in text and "/p/x" not in text  # link text, not URL
        assert "badge" not in text and "b.svg" not in text  # images go entirely
        assert "title: Ignored" not in text  # frontmatter stripped
        assert "|" not in text and "---" not in text  # table pipes and divider
        assert "Back the volume up." in text  # blockquote marker only

    def test_keeps_code_because_people_search_for_identifiers(self):
        text = prose.to_prose(PAGE)
        assert "docker compose up -d --build" in text
        assert "SQLITE_PATH" in text
        assert "```" not in text and "bash" not in text.split("docker")[0][-8:]

    def test_is_one_line(self):
        assert "\n" not in prose.to_prose(PAGE)

    def test_survives_an_empty_page(self):
        assert prose.to_prose("") == ""
        assert prose.to_prose("```\n\n```") == ""


class TestFirstParagraph:
    def test_skips_what_a_page_opens_with_and_takes_the_prose(self):
        assert prose.first_paragraph(PAGE, 160).startswith("Three commands")

    def test_a_list_counts_as_a_paragraph(self):
        assert prose.first_paragraph("# Title\n\n- First item\n- Second", 160) == "First item Second"

    def test_nothing_but_scaffolding_yields_nothing(self):
        assert prose.first_paragraph("# Title\n\n| a | b |\n|---|---|\n", 160) == ""

    def test_clips_on_a_word_boundary(self):
        result = prose.first_paragraph("alpha beta gamma delta epsilon", 12)
        assert result == "alpha beta…"
        assert len(result) <= 13


class TestTermsOf:
    def test_longest_first_and_short_words_dropped(self):
        assert prose.terms_of("a reverse proxy") == ["reverse", "proxy"]

    def test_keeps_the_characters_identifiers_are_made_of(self):
        # Dots, slashes and dashes survive tokenising, so a path or a CLI
        # flag stays one term. Longest first: 16 characters before 15.
        assert prose.terms_of("CONTENT_REPO_URL ../assets/x.png") == [
            "content_repo_url",
            "../assets/x.png",
        ]

    def test_deduplicates(self):
        assert prose.terms_of("port port PORT") == ["port"]


class TestSnippet:
    #: Enough text that a window can be wrong in a visible way.
    TEXT = (
        "An opening sentence that mentions the port and nothing else of interest. "
        + "Filler that pushes the real content further down. " * 8
        + "The service listens on port 8091 inside the container and the proxy forwards there. "
        + "More filler afterwards. " * 8
    )

    def test_lands_on_the_match_not_the_opening(self):
        result = prose.snippet(self.TEXT, prose.terms_of("8091"))
        assert "8091" in result
        assert not result.startswith("An opening sentence")

    def test_prefers_the_window_holding_the_most_distinct_terms(self):
        # "port" appears in the opening too; the cluster with both words is
        # the one further down.
        result = prose.snippet(self.TEXT, prose.terms_of("port 8091"))
        assert "port 8091" in result

    def test_marks_both_ends_it_cut(self):
        result = prose.snippet(self.TEXT, prose.terms_of("8091"))
        assert result.startswith("…") and result.endswith("…")

    def test_falls_back_to_the_opening_when_nothing_matches(self):
        # A legitimate case: the index and this function do not tokenise
        # identically, so a true hit can have no literal match here.
        result = prose.snippet(self.TEXT, ["unfindable"])
        assert result.startswith("An opening sentence")

    def test_no_terms_is_the_same_fallback(self):
        assert prose.snippet(self.TEXT, []).startswith("An opening sentence")

    def test_short_text_comes_back_whole_and_unmarked(self):
        assert prose.snippet("Just this.", prose.terms_of("this")) == "Just this."

    def test_empty_text_stays_empty(self):
        assert prose.snippet("", prose.terms_of("anything")) == ""

    def test_respects_the_limit(self):
        result = prose.snippet(self.TEXT, prose.terms_of("8091"), limit=80)
        # The two ellipses are added outside the window.
        assert len(result) <= 80 + 2

    def test_a_match_at_the_very_start_opens_without_an_ellipsis(self):
        text = "8091 is the port. " + "Filler. " * 40
        assert not prose.snippet(text, prose.terms_of("8091")).startswith("…")
