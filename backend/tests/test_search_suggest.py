"""Typo-tolerant search: a misspelled word is corrected to one that exists
in the published docs, and nothing else is touched."""
import sqlite3
from collections import Counter
from contextlib import contextmanager

import pytest

from app.routers import public_content
from app.services import search_suggest
from app.services.search_suggest import Vocabulary, _distance

WORDS = Counter(
    {
        "installation": 12, "installieren": 5, "prüfen": 4, "backup": 9, "backups": 2,
        "docker": 7, "konfiguration": 3, "docuwaves": 20, "storage": 4, "update": 6,
    }
)


@pytest.fixture
def vocab(monkeypatch):
    built = Vocabulary(WORDS)
    monkeypatch.setattr(search_suggest, "_fingerprint", lambda: ("fixed",))
    monkeypatch.setattr(search_suggest, "_build", lambda: built)
    monkeypatch.setattr(search_suggest, "_cached", None)
    search_suggest._correct_word.cache_clear()
    return built


class TestDistance:
    def test_a_swap_is_one_edit(self):
        assert _distance("dokcer", "docker", 2) == 1

    def test_gives_up_past_the_limit(self):
        assert _distance("abcdef", "uvwxyz", 1) == 2


class TestCorrect:
    @pytest.mark.parametrize(
        "typed, expected",
        [
            ("instalation", "installation"),  # a letter missing
            ("dokcer", "docker"),  # two letters swapped
            ("backpu", "backup"),
            ("konfigration", "konfiguration"),
            ("instalat", "installation"),  # still typing, and already wrong
        ],
    )
    def test_a_typo_is_corrected(self, vocab, typed, expected):
        assert search_suggest.correct(typed) == expected

    def test_only_the_wrong_word_changes(self, vocab):
        assert search_suggest.correct("Docker instalation") == "Docker installation"

    @pytest.mark.parametrize("query", ["installation", "instal", "Docker", "prufen", "Prüfen", "4711", "api"])
    def test_what_exists_is_left_alone(self, vocab, query):
        # Whole words, beginnings of words, accents the index ignores anyway,
        # numbers, and words too short to guess at.
        assert search_suggest.correct(query) is None

    def test_nothing_close_means_no_correction(self, vocab):
        assert search_suggest.correct("kubernetes") is None

    def test_the_more_common_word_wins_a_tie(self, vocab):
        # "backupx" is one edit from both; "backup" is used far more.
        assert search_suggest.correct("backupx") == "backup"


def test_drafts_are_not_in_the_vocabulary(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE pages (id INTEGER, title TEXT, markdown_content TEXT, published INTEGER, updated_at TEXT)")
    conn.execute("INSERT INTO pages VALUES (1, 'Installation', 'Öffentlich', 1, 'a')")
    conn.execute("INSERT INTO pages VALUES (2, 'Geheimprojekt', 'Unveröffentlicht', 0, 'b')")

    @contextmanager
    def connection():
        yield conn

    monkeypatch.setattr(search_suggest.db, "get_connection", connection)
    monkeypatch.setattr(search_suggest.db, "is_postgres", lambda: False)
    built = search_suggest._build()
    assert built.knows("installation")
    assert not built.knows("geheimprojekt")


class TestRoute:
    @pytest.fixture
    def searched(self, monkeypatch):
        queries = []

        def search(q, **kw):
            queries.append(q)
            return [{"title": "Installation"}] if "installation" in q else []

        monkeypatch.setattr(public_content.pages_store, "search", search)
        monkeypatch.setattr(public_content.search_suggest, "correct", lambda q: q.replace("instalation", "installation") if "instalation" in q else None)
        return queries

    def test_the_corrected_query_is_searched_and_named(self, searched):
        result = public_content.public_search(q="instalation", lang=None, project=None, version=None)
        assert result == {"results": [{"title": "Installation"}], "corrected": "installation"}

    def test_a_correct_query_is_searched_once(self, searched):
        result = public_content.public_search(q="installation", lang=None, project=None, version=None)
        assert result["corrected"] is None and searched == ["installation"]
