"""Finding pages by what they mean, not only by the words in them.

A reader searching "make it start on boot" should find the page titled
"Running as a systemd service" even though it never says "boot". Full-text
search cannot: it matches words. This module ranks pages by the similarity
of embedding vectors -- numbers a model assigns to a text so that texts with
similar meaning get similar numbers -- and the search box merges that
ranking with the full-text one.

OFF BY DEFAULT, AND LOCAL IF YOU LIKE. Nothing here runs unless an operator
sets EMBEDDINGS_API_BASE and EMBEDDINGS_MODEL. The endpoint is
OpenAI-compatible (POST {base}/embeddings), so a local Ollama with
`nomic-embed-text` works exactly like a hosted provider, and no page text
has to leave the server. With it unset, search is the full-text search it
always was, byte for byte.

HOW PAGES ARE EMBEDDED. Each published page is cut into chunks at its
headings (a section is the unit a reader is looking for), each chunk
prefixed with the page title so it keeps its context. A chunk's vector is
stored under a hash of the model and the chunk's text (the `embeddings`
table), which makes everything incremental without bookkeeping: an
unchanged section is never sent twice, a reindex costs nothing, switching
models simply misses the cache. A background thread fills in what is
missing after every reindex; until it has, search falls back to whatever
is already there plus full-text.

HOW A QUERY IS RANKED. The query is embedded (cached briefly -- search as
you type repeats itself), compared with every chunk of every page the same
search may return (services/pages_store.search_pool: published, language,
version and privacy, identical rules), and each page scores as its best
chunk. Pure Python, no numpy: a few thousand chunks of a few hundred
dimensions is a few milliseconds of arithmetic, and one more compiled
dependency is not worth that.

WHEN THE ENDPOINT FAILS. Search never does: the semantic half is dropped
and the full-text results are returned as they always were. The failure is
logged (once a minute at most) and shown under Diagnostics.
"""

import hashlib
import logging
import math
import re
import threading
import time
from array import array
from collections import OrderedDict
from datetime import datetime, timezone

import requests

from app.services import db, pages_store, prose, snippets
from app.settings import settings

log = logging.getLogger("docuwaves")

_TIMEOUT_SECONDS = 30
# Inputs per request: large enough to index a site quickly, small enough
# that one slow request is not a minute-long stall.
_BATCH = 32
# A chunk is about a screen of text. Longer sections are split further:
# embedding models truncate long input silently, and the end of a long
# section would simply not count.
_CHUNK_CHARS = 1500
# Below this similarity a page is not "about" the query, it is just in the
# same language. Tuned so that unrelated pages do not trail every result
# list; full-text hits are never filtered by it.
MIN_SCORE = 0.35
_QUERY_CACHE_SIZE = 256

_lock = threading.Lock()
_vectors: dict[str, array] = {}  # hash -> unit vector, loaded lazily
_loaded = False
_query_cache: OrderedDict[str, array] = OrderedDict()
# page id + a hash of its text -> its chunks' (hash, text): cutting and
# hashing every page on every query would cost more than the arithmetic.
_chunk_cache: dict[tuple[int, str], list[tuple[str, str]]] = {}
_indexer: threading.Thread | None = None
_again = threading.Event()
_status = {"chunks": 0, "embedded": 0, "last_error": "", "last_error_at": "", "indexed_at": ""}
_last_logged = 0.0


def is_enabled() -> bool:
    return bool(settings.embeddings_api_base and settings.embeddings_model)


def status() -> dict:
    """For Diagnostics: whether it is on, which model, how much is indexed
    and the last thing that went wrong. Never the endpoint's key."""
    with _lock:
        return {
            "enabled": is_enabled(),
            "model": settings.embeddings_model if is_enabled() else "",
            "indexing": _indexer is not None and _indexer.is_alive(),
            **_status,
        }


# ---- Chunks ----

_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)


def chunks(title: str, markdown: str) -> list[str]:
    """The page as the pieces that get a vector each: one per section (cut
    at headings), long sections cut again at paragraph breaks, each piece
    starting with the page title. Plain prose, not Markdown: the model is
    asked what the text means, and link targets and table pipes are noise."""
    sections = []
    starts = [m.start() for m in _HEADING.finditer(markdown)]
    bounds = [0, *[s for s in starts if s > 0], len(markdown)]
    for a, b in zip(bounds, bounds[1:], strict=False):
        text = prose.to_prose(markdown[a:b]).strip()
        if text:
            sections.append(text)
    pieces = []
    for section in sections or [""]:
        while len(section) > _CHUNK_CHARS:
            cut = section.rfind(". ", 0, _CHUNK_CHARS)
            cut = cut + 1 if cut > _CHUNK_CHARS // 2 else _CHUNK_CHARS
            pieces.append(section[:cut].strip())
            section = section[cut:].strip()
        pieces.append(section)
    pieces = [piece for piece in pieces if piece]
    return [f"{title}\n{piece}" for piece in pieces] or [title]


def _hash(text: str) -> str:
    return hashlib.sha256(f"{settings.embeddings_model}\n\0{text}".encode("utf-8")).hexdigest()


# ---- Vectors ----


def _unit(values) -> array:
    vector = array("f", values)
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return array("f", (v / norm for v in vector))


def _dot(a: array, b: array) -> float:
    # math.sumprod (Python 3.12) runs in C, ~20x the generator below.
    if _sumprod is not None:
        return _sumprod(a, b)
    return sum(x * y for x, y in zip(a, b, strict=True))


_sumprod = getattr(math, "sumprod", None)


def embed(texts: list[str]) -> list[array]:
    """Unit vectors for `texts`, in order. Raises EmbeddingError."""
    headers = {"Content-Type": "application/json"}
    if settings.embeddings_api_key:
        headers["Authorization"] = f"Bearer {settings.embeddings_api_key}"
    try:
        response = requests.post(
            f"{settings.embeddings_api_base}/embeddings",
            headers=headers,
            json={"model": settings.embeddings_model, "input": texts},
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise EmbeddingError(f"could not reach the embeddings endpoint: {exc}") from exc
    if response.status_code != 200:
        raise EmbeddingError(f"the embeddings endpoint answered {response.status_code}: {response.text[:300]}")
    try:
        data = sorted(response.json()["data"], key=lambda d: d.get("index", 0))
        vectors = [_unit(d["embedding"]) for d in data]
    except (ValueError, KeyError, TypeError) as exc:
        raise EmbeddingError(f"the embeddings endpoint answered something unexpected: {response.text[:300]}") from exc
    if len(vectors) != len(texts):
        raise EmbeddingError(f"asked for {len(texts)} vectors, got {len(vectors)}")
    return vectors


class EmbeddingError(Exception):
    pass


def _failed(message: str) -> None:
    global _last_logged
    with _lock:
        _status["last_error"] = message
        _status["last_error_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    now = time.monotonic()
    if now - _last_logged > 60:
        _last_logged = now
        log.warning("Semantic search: %s", message)


def _load() -> None:
    """Every stored vector into memory, once per process."""
    global _loaded
    if _loaded:
        return
    with db.get_connection() as conn:
        rows = conn.execute("SELECT hash, vector FROM embeddings").fetchall()
    with _lock:
        for digest, blob in rows:
            vector = array("f")
            vector.frombytes(bytes(blob))
            _vectors[digest] = vector
        _loaded = True


def _store(pairs: list[tuple[str, array]]) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        for digest, vector in pairs:
            conn.execute(
                f"INSERT INTO embeddings (hash, vector, used_at) VALUES ({placeholder}, {placeholder}, {placeholder}) "
                f"ON CONFLICT (hash) DO NOTHING",
                (digest, vector.tobytes(), now),
            )
    with _lock:
        for digest, vector in pairs:
            _vectors[digest] = vector


# ---- Indexing ----


def _all_chunks() -> dict[str, str]:
    """hash -> text, for every chunk of every published page (every
    language and version: whichever one a reader searches has to be there)."""
    placeholder = "%s" if db.is_postgres() else "?"
    with db.get_connection() as conn:
        rows = conn.execute(
            f"SELECT p.title, p.markdown_content, pr.slug, p.version, p.language FROM pages p "
            f"JOIN projects pr ON pr.id = p.project_id WHERE p.published = {placeholder}",
            (True if db.is_postgres() else 1,),
        ).fetchall()
    wanted: dict[str, str] = {}
    for title, markdown, project_slug, version, language in rows:
        body = snippets.resolve(markdown or "", project_slug, version, language)
        for text in chunks(title, body):
            wanted[_hash(text)] = text
    return wanted


def index_now() -> int:
    """Embeds every chunk that has no vector yet. Returns how many it added.
    Runs in the background thread; called directly by tests."""
    if not is_enabled():
        return 0
    _load()
    wanted = _all_chunks()
    with _lock:
        missing = [(h, t) for h, t in wanted.items() if h not in _vectors]
        _status["chunks"] = len(wanted)
    added = 0
    for start in range(0, len(missing), _BATCH):
        batch = missing[start:start + _BATCH]
        try:
            vectors = embed([text for _, text in batch])
        except EmbeddingError as exc:
            _failed(str(exc))
            break
        _store([(digest, vector) for (digest, _), vector in zip(batch, vectors, strict=True)])
        added += len(batch)
    with _lock:
        _status["embedded"] = sum(1 for h in wanted if h in _vectors)
        _status["indexed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if added and _status["embedded"] == len(wanted):
            _status["last_error"] = ""
    return added


def schedule() -> None:
    """Brings the vectors up to date in the background -- called after
    every reindex. One thread at most; a call while it runs makes it go
    round once more, so the last change is never missed."""
    global _indexer
    if not is_enabled():
        return
    # A snippet a page includes may have changed: cut the pages afresh.
    _chunk_cache.clear()
    with _lock:
        if _indexer is not None and _indexer.is_alive():
            _again.set()
            return
        _again.clear()

        def run() -> None:
            while True:
                try:
                    index_now()
                except Exception as exc:  # noqa: BLE001 -- a background thread must not die silently
                    _failed(f"indexing failed: {exc}")
                if not _again.is_set():
                    return
                _again.clear()

        _indexer = threading.Thread(target=run, name="semantic-index", daemon=True)
        _indexer.start()


# ---- Searching ----


def _query_vector(query: str) -> array:
    key = query.strip().lower()
    with _lock:
        if key in _query_cache:
            _query_cache.move_to_end(key)
            return _query_cache[key]
    vector = embed([query.strip()])[0]
    with _lock:
        _query_cache[key] = vector
        while len(_query_cache) > _QUERY_CACHE_SIZE:
            _query_cache.popitem(last=False)
    return vector


def _page_chunks(row: tuple) -> list[tuple[str, str]]:
    key = (row[0], hashlib.sha256(f"{row[1]}\n\0{row[3]}".encode("utf-8")).hexdigest())
    cached = _chunk_cache.get(key)
    if cached is None:
        body = snippets.resolve(row[3] or "", row[5], row[11], row[8])
        cached = [(_hash(text), text) for text in chunks(row[1], body)]
        if len(_chunk_cache) > 20000:
            _chunk_cache.clear()
        _chunk_cache[key] = cached
    return cached


def rank(query: str, pool: list[tuple], limit: int) -> list[tuple[tuple, float, str]]:
    """The rows of `pool` (pages_store.search_pool) that are about `query`,
    best first, as (row, score, best chunk's text). Empty when the feature
    is off, nothing is embedded yet, or the endpoint fails."""
    if not is_enabled() or not query.strip() or not pool:
        return []
    try:
        _load()
        target = _query_vector(query)
    except EmbeddingError as exc:
        _failed(str(exc))
        return []
    scored = []
    for row in pool:
        best, best_text = -1.0, ""
        for digest, text in _page_chunks(row):
            vector = _vectors.get(digest)
            if vector is None or len(vector) != len(target):
                continue
            score = _dot(target, vector)
            if score > best:
                best, best_text = score, text
        if best >= MIN_SCORE:
            scored.append((row, best, best_text))
    scored.sort(key=lambda entry: entry[1], reverse=True)
    return scored[:limit]


def merge(text_hits: list[dict], query: str, language: str | None, project_id, version, include_private: bool, limit: int = 20) -> list[dict]:
    """Full-text hits and meaning hits as one list, by reciprocal rank
    fusion: each list votes 1/(60 + rank) for its pages, and the sums
    decide. A page both find rises to the top; a page only one finds still
    gets in. Hits found by meaning alone say so (`match: "meaning"`) and
    show the section that matched as their snippet -- the reader's words
    may not be in it, and the snippet is the evidence of why it is here."""
    if not is_enabled():
        return text_hits
    pool = pages_store.search_pool(language, project_id, version, include_private)
    meaning = rank(query, pool, limit)
    if not meaning:
        return text_hits
    scores: dict[int, float] = {}
    hits: dict[int, dict] = {}
    for position, hit in enumerate(text_hits):
        scores[hit["page_id"]] = scores.get(hit["page_id"], 0) + 1 / (60 + position)
        hits[hit["page_id"]] = hit
    for position, (row, _score, text) in enumerate(meaning):
        page_id = row[0]
        scores[page_id] = scores.get(page_id, 0) + 1 / (60 + position)
        if page_id not in hits:
            hit = pages_store.result_row(row, language, query)
            # Without the title line chunks() put in front of it.
            hit["snippet"] = prose.clip(text.split("\n", 1)[-1], 220)
            hit["match"] = "meaning"
            hits[page_id] = hit
    ordered = sorted(hits, key=lambda page_id: scores[page_id], reverse=True)
    return [hits[page_id] for page_id in ordered[:limit]]
