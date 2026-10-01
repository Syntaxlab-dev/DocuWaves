"""Typo tolerance for search: "instalation" finds "Installation".

Neither full-text backend forgives a typo -- both match whole terms or
prefixes (see pages_store's docstring) -- so a misspelled word simply matches
nothing: on Postgres, where terms are AND'ed, it empties the whole result.

What this does instead of changing either index: it keeps a VOCABULARY of
the words in published pages, and before a search it checks each word of the
query against it. A word that exists (or starts a word that does -- search
matches prefixes, and the quick search runs while someone is still typing) is
left alone. A word that doesn't is replaced by the closest one there is,
within one edit for a short word and two for a longer one -- a swapped pair
of letters counts as one edit, being the most common typo there is. The
search then runs on the corrected text, and the response says so, so the
reader sees "results for Installation" rather than wondering why their word
isn't highlighted anywhere.

PUBLISHED pages of PUBLIC projects only. A suggestion is text from the docs;
drawn from drafts or from a private project, it would put words on the public
site that are not meant for it.

The vocabulary is rebuilt when the pages change (a cheap fingerprint of the
table is checked per search) and otherwise kept in memory: a few thousand
distinct words, built in well under a second even for a large site.
"""
import re
import threading
import unicodedata
from bisect import bisect_left
from collections import Counter
from functools import lru_cache

from app.services import db

_WORD_RE = re.compile(r"\w+")
_MIN_LENGTH = 4  # "mit", "und", "the": too short to correct without guessing
_MAX_LENGTH = 40


def fold(word: str) -> str:
    """Lowercase without accents -- what FTS5's default tokenizer matches on
    too, so "prufen" already finds "prüfen" and must not be "corrected"."""
    decomposed = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class Vocabulary:
    def __init__(self, counts: Counter):
        # folded form -> (display form, frequency). The display form is the
        # most frequent spelling, so "prufen" is corrected to "prüfen".
        spellings: dict[str, Counter] = {}
        for word, count in counts.items():
            spellings.setdefault(fold(word), Counter())[word] += count
        self.words = {key: (forms.most_common(1)[0][0], sum(forms.values())) for key, forms in spellings.items()}
        self.sorted = sorted(self.words)
        self.by_initial: dict[str, list[str]] = {}
        for key in self.sorted:
            self.by_initial.setdefault(key[0], []).append(key)

    def knows(self, folded: str) -> bool:
        """The word, or a word it is the beginning of."""
        index = bisect_left(self.sorted, folded)
        return index < len(self.sorted) and self.sorted[index].startswith(folded)

    def closest(self, folded: str) -> str | None:
        limit = 1 if len(folded) <= 5 else 2
        best: tuple[int, int, str] | None = None
        # Same first letter only. Typos at the very start of a word are the
        # rare kind, and this cuts the candidates to a fraction.
        for candidate in self.by_initial.get(folded[0], ()):
            if len(candidate) < len(folded) - limit:
                continue
            # Against the whole word and against its beginning: someone who
            # has typed "instalat" so far means "installation".
            distance = min(
                _distance(folded, candidate, limit),
                _distance(folded, candidate[: len(folded)], limit),
                _distance(folded, candidate[: len(folded) + 1], limit),
            )
            if distance > limit:
                continue
            key = (distance, -self.words[candidate][1], candidate)
            if best is None or key < best:
                best = key
        return self.words[best[2]][0] if best else None


def _distance(a: str, b: str, limit: int) -> int:
    """Edit distance counting an adjacent swap as one edit (optimal string
    alignment), giving up with limit+1 as soon as the answer must exceed it."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous2: list[int] = []
    previous = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        current = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                current[j] = min(current[j], previous2[j - 2] + 1)
        if min(current) > limit:
            return limit + 1
        previous2, previous = previous, current
    return previous[-1]


# ---- The cached vocabulary ----

_lock = threading.Lock()
_cached: tuple[tuple, Vocabulary] | None = None


def _fingerprint() -> tuple:
    published = "TRUE" if db.is_postgres() else "1"
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT COUNT(*), COALESCE(MAX(updated_at), ''), COALESCE(MAX(id), 0) FROM pages "
            f"WHERE published = {published} AND project_id NOT IN (SELECT id FROM projects WHERE private = 1)"
        ).fetchone()
    return tuple(row)


def _build() -> Vocabulary:
    published = "TRUE" if db.is_postgres() else "1"
    counts: Counter = Counter()
    with db.get_connection() as conn:
        # Public projects only: suggestions are shared by every reader, so a
        # word from a private project must never become one (visibility.py).
        rows = conn.execute(
            f"SELECT title, markdown_content FROM pages WHERE published = {published} "
            "AND project_id NOT IN (SELECT id FROM projects WHERE private = 1)"
        ).fetchall()
    for title, body in rows:
        for word in _WORD_RE.findall(f"{title} {body}".lower()):
            if _MIN_LENGTH - 1 <= len(word) <= _MAX_LENGTH and not word.isdigit():
                counts[word] += 1
    return Vocabulary(counts)


def vocabulary() -> Vocabulary:
    global _cached
    fingerprint = _fingerprint()
    with _lock:
        if _cached is None or _cached[0] != fingerprint:
            _cached = (fingerprint, _build())
            _correct_word.cache_clear()
        return _cached[1]


@lru_cache(maxsize=2048)
def _correct_word(folded: str) -> str | None:
    vocab = _cached[1] if _cached else None
    if vocab is None or vocab.knows(folded):
        return None
    return vocab.closest(folded)


def correct(query: str) -> str | None:
    """The query with its misspelled words replaced, or None when there is
    nothing to correct (or nothing close enough to correct it to)."""
    words = [w for w in _WORD_RE.findall(query) if _MIN_LENGTH <= len(w) <= _MAX_LENGTH and not w.isdigit()]
    if not words:
        return None
    vocabulary()
    changed = False
    corrected = query
    for word in dict.fromkeys(words):
        replacement = _correct_word(fold(word))
        if replacement and fold(replacement) != fold(word):
            corrected = re.sub(rf"\b{re.escape(word)}\b", replacement, corrected)
            changed = True
    return corrected if changed else None
