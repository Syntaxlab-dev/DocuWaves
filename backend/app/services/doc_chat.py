"""Asking the documentation a question, and getting an answer made only of
the documentation.

WHAT THIS IS. A reader types a question; this searches the published pages,
hands the best few to a language model as the ONLY material it may use, and
answers with the model's reply plus links to the pages it was given. It is
retrieval with a sentence generator on the end, not a general assistant that
happens to know about this site.

WHERE THE MODEL COMES FROM. Nowhere by default. DocuWaves ships no model,
bundles no API key and calls no service unless an operator configures one --
this feature is OFF until three environment variables are set, and an
instance that never sets them makes no outbound request, ever. The endpoint
is OpenAI-compatible (`POST {base}/chat/completions`), which is what a local
Ollama, a local llama.cpp server, OpenAI and most hosted providers all
speak, so "self-hosted docs" does not have to mean "and now a cloud
account".

WHY THE KEY IS AN ENVIRONMENT VARIABLE and not a field in the admin UI: it
is a credential, and every other setting in this app that a person edits
lives in `_site.yml`, which is a file in a repository built to be cloned and
read in pull requests. The same reasoning that keeps API tokens out of the
content repo keeps this key out of it, and once the key has to be an env var
the other two belong next to it rather than split across two places.

RETRIEVAL IS THE SAME SEARCH THE MCP ENDPOINT EXPOSES -- pages_store.search
over published pages, in the reader's language and the version they are
reading. So the built-in answer and the answer an external assistant gives
through /api/mcp are drawn from the same index, and there is no second
retrieval path to drift.

WHAT THE PROMPT IS FOR. Three rules, and all three are about not making
things up: answer only from the numbered sources, say plainly when they do
not cover the question, and never invent a page or a link. A documentation
assistant that guesses is worse than no assistant, because a reader cannot
tell the difference and the site's own name is on the answer.

NOTHING IS STORED. No conversation table, no question log. A question is a
request parameter and the answer is the response; both are gone when it
returns. What the operator's model provider does with it is between them and
their provider, and the admin UI says so.
"""

import logging
import re
import time
import threading

import requests

from app.services import pages_store, projects_store, prose, site_languages
from app.settings import settings

log = logging.getLogger("docuwaves")

# How many pages the model is given. Few enough that each one arrives with
# enough text to be useful, and few enough that a wrong hit is visible in the
# sources rather than buried among fifteen.
_SOURCE_LIMIT = 5

# Characters of each page. A documentation page is mostly under this; one
# that isn't gets its opening, which is where a page says what it is for.
# Deliberately a character budget and not a token count: this app cannot
# know the tokenizer of a model an operator chose, and a rough limit that is
# always right is better than a precise one that is right for one vendor.
_SOURCE_CHARS = 2400

MAX_QUESTION_LENGTH = 500

# A public endpoint that spends the operator's model budget, so the limit is
# strict and it is per client address. Six questions a minute is a
# conversation; it is not a script.
_RATE_LIMIT_QUESTIONS = 6
_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_BUCKET_SWEEP_AT = 512

_rate_lock = threading.Lock()
_rate_buckets: dict[str, list[float]] = {}

_TIMEOUT_SECONDS = 60


def is_enabled() -> bool:
    """All three, or none. A base URL with no model names no model to call,
    and a model with no base URL has nowhere to call -- half a configuration
    would be a chat box that fails on every question."""
    return bool(settings.chat_api_base and settings.chat_model and settings.chat_api_key)


def status() -> dict:
    """What the admin area shows about this feature. The key is reported as
    a boolean and never echoed."""
    return {
        "enabled": is_enabled(),
        "model": settings.chat_model if is_enabled() else "",
        "endpoint": settings.chat_api_base if is_enabled() else "",
        "max_question_length": MAX_QUESTION_LENGTH,
    }


def rate_limited(client_key: str) -> bool:
    """True = this address has asked too often in the last minute. In memory
    only, swept rather than retained: a bucket of timestamps, never a log of
    who asked what."""
    if not client_key:
        return False
    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    with _rate_lock:
        if len(_rate_buckets) > _RATE_BUCKET_SWEEP_AT:
            for key in [k for k, times in _rate_buckets.items() if not times or times[-1] < cutoff]:
                _rate_buckets.pop(key, None)
        recent = [t for t in _rate_buckets.get(client_key, []) if t >= cutoff]
        if len(recent) >= _RATE_LIMIT_QUESTIONS:
            _rate_buckets[client_key] = recent
            return True
        recent.append(now)
        _rate_buckets[client_key] = recent
        return False


class ChatError(RuntimeError):
    """Something about the model call went wrong. The message is written for
    a reader of the documentation site, not for a log: they cannot fix the
    operator's provider and should not be shown its error body."""


def find_sources(question: str, language: str, project_slug: str = "", version: str = "") -> list[dict]:
    """The pages this question will be answered from.

    Scoped exactly the way the reader's own search is: published pages only,
    their language, and -- when they are reading inside one project and one
    documentation version -- that project and that version. Somebody asking
    a question while reading the v2.0 docs must not be answered out of v3.0,
    which is the same rule the search box already follows.
    """
    project_id = None
    if project_slug:
        project = projects_store.get_project_by_slug(project_slug, language)
        if project is not None:
            project_id = project["id"]
    hits = pages_store.search(
        question,
        limit=_SOURCE_LIMIT,
        language=language,
        project_id=project_id,
        version=version if project_id is not None else None,
    )
    return hits[:_SOURCE_LIMIT]


def _page_text(hit: dict) -> str:
    page = pages_store.get_page(hit["page_id"])
    body = page["markdown_content"] if page else ""
    return prose.clip(prose.to_prose(body), _SOURCE_CHARS)


def build_context(hits: list[dict]) -> str:
    """The sources, numbered, as the only material the model is given.

    Numbered rather than labelled by title: the prompt asks for citations as
    [1], [2], and a number is something a model reproduces reliably while a
    title is something it paraphrases. The numbers are matched back to real
    pages here (see cited_indexes), so a citation cannot point at a page that
    was never supplied."""
    blocks = []
    for index, hit in enumerate(hits, start=1):
        blocks.append(
            f"[{index}] {hit['title']} ({hit['project_name']} / {hit['category_name']})\n{_page_text(hit)}"
        )
    return "\n\n".join(blocks)


_SYSTEM_PROMPT = (
    "You answer questions about a specific documentation site, using ONLY the numbered sources given to "
    "you in the user message.\n"
    "\n"
    "Rules, in order of importance:\n"
    "1. Never state anything the sources do not say. Do not fill gaps from general knowledge, and do not "
    "guess at product behaviour, versions, flags or file names.\n"
    "2. If the sources do not answer the question, say so plainly in one sentence and stop. Suggesting which "
    "of them looks closest is helpful; inventing an answer is not.\n"
    "3. Cite the sources you used as [1], [2] inline. Never cite a number you were not given, and never "
    "invent a page title, a URL or a link.\n"
    "\n"
    "Answer in {language_name}. Be brief -- a few sentences, or a short list. The reader is on the "
    "documentation site and can open the pages you cite."
)

_LANGUAGE_NAMES = {"de": "German", "en": "English", "fr": "French", "es": "Spanish", "it": "Italian", "nl": "Dutch"}


def _language_name(code: str) -> str:
    """What to call the reader's language IN THE PROMPT, which is English --
    a model follows "answer in German" more reliably than "answer in de".
    An unconfigured code falls back to English, which is also what an
    instance with no `languages:` gets."""
    return _LANGUAGE_NAMES.get(code, "English")


_CITATION_RE = re.compile(r"\[(\d{1,2})\]")


def cited_indexes(answer: str, source_count: int) -> list[int]:
    """The 1-based source numbers the answer actually cites, in order, and
    only ones that exist.

    A model that cites [7] when it was handed four sources has invented a
    citation; dropping it is what stops that reaching a reader as a link to
    nowhere. The answer text keeps the marker -- rewriting somebody's answer
    to hide a mistake in it would be the wrong kind of tidy."""
    seen: list[int] = []
    for match in _CITATION_RE.finditer(answer):
        index = int(match.group(1))
        if 1 <= index <= source_count and index not in seen:
            seen.append(index)
    return seen


def _post_chat(messages: list[dict]) -> str:
    """One OpenAI-compatible completion, or ChatError with a sentence a
    reader can be shown.

    Every failure mode collapses to one of three messages on purpose. A
    reader cannot act on "429 from api.example.com", and the operator's
    provider, model name and error body are not theirs to see -- the detail
    goes to the log, where the operator will look."""
    url = f"{settings.chat_api_base.rstrip('/')}/chat/completions"
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.chat_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.chat_model,
                "messages": messages,
                # Low but not zero: this is a factual answer built from
                # supplied text, and creativity is the failure mode.
                "temperature": 0.2,
                "max_tokens": 600,
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        log.warning("Doc chat timed out after %ss: %s", _TIMEOUT_SECONDS, exc)
        raise ChatError("timeout") from exc
    except requests.RequestException as exc:
        log.warning("Doc chat could not reach the model endpoint: %s", exc)
        raise ChatError("unreachable") from exc

    if response.status_code != 200:
        log.warning("Doc chat endpoint answered %s: %s", response.status_code, response.text[:500])
        raise ChatError("provider_error")
    try:
        return response.json()["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError, AttributeError) as exc:
        log.warning("Doc chat endpoint answered something unexpected: %s", response.text[:500])
        raise ChatError("provider_error") from exc


def ask(question: str, language: str, project_slug: str = "", version: str = "") -> dict:
    """The whole thing: search, prompt, call, and the sources to link to.

    A question with no matching pages does NOT reach the model. There is
    nothing for it to answer from, so the honest answer is "nothing here
    covers that" -- and asking a model to produce it anyway is asking it to
    make something up, at the operator's expense."""
    question = question.strip()[:MAX_QUESTION_LENGTH]
    if not question:
        raise ChatError("empty_question")
    if not is_enabled():
        raise ChatError("not_configured")

    hits = find_sources(question, language, project_slug, version)
    if not hits:
        return {"answer": "", "sources": [], "no_sources": True}

    prompt = (
        f"Question: {question}\n\nSources:\n\n{build_context(hits)}"
    )
    answer = _post_chat(
        [
            {"role": "system", "content": _SYSTEM_PROMPT.format(language_name=_language_name(language))},
            {"role": "user", "content": prompt},
        ]
    )
    cited = cited_indexes(answer, len(hits))
    return {
        "answer": answer,
        # Every source that was offered, marked with whether the answer used
        # it. A reader checking an answer wants the pages it came from; a
        # reader the answer did not help wants the ones it passed over.
        "sources": [
            {
                "n": index,
                "title": hit["title"],
                "project_slug": hit["project_slug"],
                "page_slug": hit["page_slug"],
                "version": hit["version"],
                "language": hit["language"],
                "cited": index in cited,
            }
            for index, hit in enumerate(hits, start=1)
        ],
        "no_sources": False,
    }
