"""The documentation chat: everything except the model call itself.

What is worth pinning here is the grounding, because that is the whole
feature. An answer that quietly invents a page, cites a source that was
never supplied, or reaches a model at all on an instance that configured
none, is not a smaller version of this feature -- it is the failure it
exists to avoid.
"""
import pytest

from app.services import doc_chat
from app.settings import settings


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "chat_api_base", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "chat_model", "llama3.1:8b")
    monkeypatch.setattr(settings, "chat_api_key", "ollama")


@pytest.fixture
def unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "chat_api_base", "")
    monkeypatch.setattr(settings, "chat_model", "")
    monkeypatch.setattr(settings, "chat_api_key", "")


class TestOffByDefault:
    def test_an_instance_that_configured_nothing_is_off(self, unconfigured):
        assert doc_chat.is_enabled() is False

    @pytest.mark.parametrize(
        "present", ["chat_api_base", "chat_model", "chat_api_key"]
    )
    def test_a_partial_configuration_is_off(self, unconfigured, monkeypatch, present):
        """Half a configuration would be a chat box that fails on every
        question -- a base URL with no model names nothing to call, and a
        model with no base URL has nowhere to call."""
        monkeypatch.setattr(settings, present, "something")
        assert doc_chat.is_enabled() is False

    def test_all_three_turns_it_on(self, configured):
        assert doc_chat.is_enabled() is True

    def test_the_status_never_carries_the_key(self, configured):
        status = doc_chat.status()
        assert settings.chat_api_key not in str(status.values()) or status["model"] != settings.chat_api_key
        assert "key" not in status
        assert status["model"] == "llama3.1:8b"

    def test_and_says_nothing_at_all_when_off(self, unconfigured):
        status = doc_chat.status()
        assert status["enabled"] is False
        assert status["model"] == "" and status["endpoint"] == ""

    def test_asking_an_unconfigured_instance_reaches_no_model(self, unconfigured, monkeypatch):
        monkeypatch.setattr(
            doc_chat, "_post_chat", lambda messages: pytest.fail("a model must not be called")
        )
        with pytest.raises(doc_chat.ChatError):
            doc_chat.ask("anything", "en")


class TestCitations:
    def test_keeps_the_ones_that_exist_in_order(self):
        assert doc_chat.cited_indexes("See [2] and also [1].", 3) == [2, 1]

    def test_drops_a_citation_that_was_never_supplied(self):
        """A model citing [7] when it was handed four sources has invented
        one. Dropping it is what stops that reaching a reader as a link to
        nowhere."""
        assert doc_chat.cited_indexes("As described in [7].", 4) == []

    def test_drops_zero_and_negatives(self):
        assert doc_chat.cited_indexes("[0] and [-1]", 3) == []

    def test_lists_each_source_once(self):
        assert doc_chat.cited_indexes("[1] ... [1] ... [2]", 2) == [1, 2]

    def test_an_answer_citing_nothing_cites_nothing(self):
        assert doc_chat.cited_indexes("I could not find that.", 3) == []


class TestNoSourcesMeansNoModelCall:
    def test_a_question_nothing_matches_never_reaches_the_model(self, configured, monkeypatch):
        """There is nothing for it to answer FROM, so asking it anyway is
        asking it to make something up -- at the operator's expense."""
        monkeypatch.setattr(doc_chat, "find_sources", lambda *args, **kwargs: [])
        monkeypatch.setattr(
            doc_chat, "_post_chat", lambda messages: pytest.fail("a model must not be called")
        )
        result = doc_chat.ask("something nobody documented", "en")
        assert result["no_sources"] is True
        assert result["answer"] == "" and result["sources"] == []


class TestThePrompt:
    def test_forbids_going_beyond_the_sources(self):
        prompt = doc_chat._SYSTEM_PROMPT
        assert "ONLY the numbered sources" in prompt
        assert "Never state anything the sources do not say" in prompt
        assert "never invent" in prompt.lower()

    def test_asks_for_the_reader_s_language_by_name(self):
        """A model follows "answer in German" more reliably than "answer in
        de"; an unconfigured code falls back to English."""
        assert doc_chat._language_name("de") == "German"
        assert doc_chat._language_name("") == "English"
        assert doc_chat._language_name("zz") == "English"

    def test_the_context_numbers_every_source(self, monkeypatch):
        monkeypatch.setattr(doc_chat, "_page_text", lambda hit: "The body of " + hit["title"])
        hits = [
            {"title": "Install", "project_name": "P", "category_name": "C"},
            {"title": "Upgrade", "project_name": "P", "category_name": "C"},
        ]
        context = doc_chat.build_context(hits)
        assert context.startswith("[1] Install")
        assert "[2] Upgrade" in context


class TestRateLimit:
    def test_lets_a_conversation_through_and_stops_a_script(self, monkeypatch):
        monkeypatch.setattr(doc_chat, "_rate_buckets", {})
        key = "203.0.113.7"
        allowed = [doc_chat.rate_limited(key) for _ in range(doc_chat._RATE_LIMIT_QUESTIONS)]
        assert not any(allowed)
        assert doc_chat.rate_limited(key) is True

    def test_counts_per_address(self, monkeypatch):
        monkeypatch.setattr(doc_chat, "_rate_buckets", {})
        for _ in range(doc_chat._RATE_LIMIT_QUESTIONS):
            doc_chat.rate_limited("a")
        assert doc_chat.rate_limited("a") is True
        assert doc_chat.rate_limited("b") is False

    def test_an_unknown_caller_is_not_limited_into_silence(self, monkeypatch):
        """No address at all (a test client, an odd proxy) must not become
        one shared bucket that locks everybody out at once."""
        monkeypatch.setattr(doc_chat, "_rate_buckets", {})
        assert all(doc_chat.rate_limited("") is False for _ in range(50))
