"""Search matches word beginnings, on both backends.

The quick search runs as the reader types, and nobody types a whole word
before looking: with exact tokens only, "instal" found nothing although a
page called "Installation" exists.
"""
import sqlite3

from app.services.pages_store import _fts5_query, _pg_prefix_query


def test_fts5_terms_are_prefixes():
    assert _fts5_query("instal docker") == '"instal"* OR "docker"*'


def test_fts5_a_single_character_stays_exact():
    assert _fts5_query("a install") == '"a" OR "install"*'


def test_fts5_quotes_cannot_break_out_of_a_term():
    assert _fts5_query('he"llo') == '"hello"*'


def test_fts5_prefix_query_really_matches_in_sqlite():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(title, body)")
    conn.execute("INSERT INTO t VALUES ('Installation', 'So installierst du DocuWaves')")
    conn.execute("INSERT INTO t VALUES ('Backup', 'Nichts Passendes')")
    hits = conn.execute("SELECT title FROM t WHERE t MATCH ?", (_fts5_query("instal"),)).fetchall()
    assert hits == [("Installation",)]


def test_pg_terms_are_prefixes_and_anded():
    assert _pg_prefix_query("Instal Docker") == "instal:* & docker:*"


def test_pg_query_keeps_only_word_characters():
    # Nothing a reader types can become tsquery syntax (&, |, !, :, parentheses).
    assert _pg_prefix_query("foo & !bar) | baz:*") == "foo:* & bar:* & baz:*"
    assert _pg_prefix_query("!!! ()") is None


def test_pg_handles_umlauts():
    assert _pg_prefix_query("Übersicht") == "übersicht:*"
