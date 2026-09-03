"""Which languages exist, and what a reader sees when their own is missing.

The fallback is the part worth pinning: a missing translation must show the
default language's text rather than a blank, and a single-language instance
must behave exactly as it did before the feature existed.
"""
from app.services import site_languages


class TestConfiguration:
    def test_no_languages_key_switches_the_whole_feature_off(self, content):
        content.site(name="Docs")
        assert site_languages.languages() == []
        assert site_languages.default_language() == ""

    def test_the_first_configured_language_is_the_default(self, content):
        content.site(name="Docs", languages=["de", "en"])
        assert site_languages.languages() == ["de", "en"]
        assert site_languages.default_language() == "de"

    def test_a_missing_site_file_is_not_an_error(self, content):
        assert site_languages.languages() == []
        assert site_languages.default_language() == ""


class TestPick:
    TEXT = "Installation"
    MAPPING = {"en": "Setup"}

    def test_uses_the_readers_language_when_it_is_there(self):
        assert site_languages.pick(self.TEXT, self.MAPPING, "en") == "Setup"

    def test_falls_back_to_the_default_text(self):
        assert site_languages.pick(self.TEXT, self.MAPPING, "fr") == "Installation"

    def test_an_empty_translation_falls_back_rather_than_blanking(self):
        """A name is structural -- an empty tile is worse than a tile in the
        wrong language."""
        assert site_languages.pick(self.TEXT, {"en": ""}, "en") == "Installation"

    def test_no_language_asked_for_means_the_default_text(self):
        assert site_languages.pick(self.TEXT, self.MAPPING, "") == "Installation"

    def test_no_mapping_at_all_means_the_default_text(self):
        assert site_languages.pick(self.TEXT, {}, "en") == "Installation"
