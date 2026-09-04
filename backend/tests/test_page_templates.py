"""The four page skeletons.

Pure data and two lookups, so there is nothing here that needs a repo. What
IS worth pinning: an id that changes breaks nothing loudly (the picker just
stops offering that one), a missing language silently serves the wrong one,
and an empty body would replace an author's blank page with another blank
page while claiming to have inserted a structure.
"""
import pytest

from app.services import page_templates


class TestListing:
    def test_offers_every_id_in_order(self):
        listed = [entry["id"] for entry in page_templates.list_templates("en")]
        assert listed == list(page_templates.TEMPLATE_IDS)

    def test_every_template_has_a_name_a_description_and_a_body(self):
        for entry in page_templates.list_templates("en"):
            assert entry["name"].strip()
            assert entry["description"].strip()
            # A structure, not a blank: every one of them opens with a title
            # line and has sections under it.
            assert entry["markdown"].startswith("# ")
            assert entry["markdown"].count("\n## ") >= 2

    @pytest.mark.parametrize("language", ["en", "de"])
    def test_both_languages_are_complete(self, language):
        """A half-translated set would show German names over English
        bodies, which reads as a bug in the template rather than a missing
        translation."""
        for template_id in page_templates.TEMPLATE_IDS:
            entry = next(e for e in page_templates.list_templates(language) if e["id"] == template_id)
            assert entry["name"] and entry["description"] and entry["markdown"]

    def test_german_and_english_are_actually_different_texts(self):
        german = {e["id"]: e["markdown"] for e in page_templates.list_templates("de")}
        english = {e["id"]: e["markdown"] for e in page_templates.list_templates("en")}
        assert all(german[key] != english[key] for key in german)


class TestLanguageFallback:
    def test_an_unconfigured_language_gets_english(self):
        assert page_templates.get_template("handbook", "fr") == page_templates.get_template("handbook", "en")

    def test_a_single_language_instance_gets_english(self):
        """'' is the language on an instance that never configured
        `languages:` -- it is not a code, so it falls back like any other."""
        assert page_templates.get_template("handbook", "") == page_templates.get_template("handbook", "en")

    def test_a_configured_language_gets_its_own(self):
        assert page_templates.get_template("handbook", "de") != page_templates.get_template("handbook", "en")


class TestUnknownTemplate:
    def test_is_none_rather_than_an_empty_page(self):
        assert page_templates.get_template("no-such-template", "en") is None
