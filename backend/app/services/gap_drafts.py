"""A first draft for a page readers searched for and did not find.

The search-gaps radar (services/search_gaps.py) lists what readers looked
for and found nothing about. Starting a page from one used to give the
author an empty editor with the search words as its title. With the
documentation chat's model configured, it can give them a skeleton instead:
a sensible structure of headings, the facts the EXISTING documentation
already states about the neighbouring topics, links to those pages, and a
visible **TODO** wherever something has to be written that the docs do not
say.

THE RULE IS THE CHAT'S RULE, applied to writing: nothing in the draft may
come from the model's general knowledge. A gap is, by definition, a topic
the docs do not cover yet, so most of a good draft is TODOs -- which is the
honest result, and the useful one: the author sees what the page needs and
what already exists to link to. A model that "helpfully" filled the gap
from training data would put invented product behaviour into a docs site
under its owner's name.

The draft is never saved here. It comes back to the editor as a new,
unpublished page that the author reads, fixes and saves themselves.
"""

import re

from app.services import content_versions, doc_chat

MAX_QUERY = 200
_SOURCE_LIMIT = 5
_WORD_RE = re.compile(r"\w{4,}", re.UNICODE)

_PROMPT = (
    "You draft a NEW page for a documentation site. Readers searched for the topic below and the site has "
    "no page about it yet. Write a first draft in Markdown for a human author to finish.\n"
    "\n"
    "Rules, in order of importance:\n"
    "1. Use ONLY facts stated in the numbered sources. Never add product behaviour, commands, settings, "
    "versions or numbers from general knowledge.\n"
    "2. Wherever the page needs information the sources do not give, write a line starting with "
    "'**TODO:**' saying exactly what is needed. Expect most of the page to be TODOs; that is correct.\n"
    "3. You may link to a source page, only with the exact URL given for it, e.g. [Title](/p/x/pages/y).\n"
    "4. Structure: a one-paragraph introduction (or a TODO for it), then 2-5 '## ' sections a reader "
    "of this topic would expect. Do not repeat the title as a '# ' heading.\n"
    "\n"
    "Write in {language_name}. Output only the Markdown of the page body."
)


def _sources(query: str, language: str, project_slug: str) -> list[dict]:
    """The pages nearest to the topic. The whole query first, as the chat
    does; a gap usually finds nothing that way (that is why it is a gap), so
    then each longer word on its own, merged."""
    version = content_versions.default_version(project_slug) if project_slug else ""
    # An author drafting a page may draw on private projects too: the draft
    # goes to them, not to a reader.
    hits = doc_chat.find_sources(query, language, project_slug, version, include_private=True)
    if hits:
        return hits
    seen: dict[int, dict] = {}
    for word in _WORD_RE.findall(query)[:6]:
        for hit in doc_chat.find_sources(word, language, project_slug, version, include_private=True):
            seen.setdefault(hit["page_id"], hit)
    return list(seen.values())[:_SOURCE_LIMIT]


def _context(hits: list[dict]) -> str:
    blocks = []
    for index, hit in enumerate(hits, start=1):
        version = f"{hit['version']}/" if hit.get("version") else ""
        url = f"/p/{hit['project_slug']}/{version}pages/{hit['page_slug']}"
        blocks.append(f"[{index}] {hit['title']} -- URL: {url}\n{doc_chat._page_text(hit)}")
    return "\n\n".join(blocks)


_FENCE_RE = re.compile(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", re.DOTALL)
_H1_RE = re.compile(r"^#\s+.*\n+")


def clean(markdown: str) -> str:
    """What models add around a page body anyway: a code fence around the
    whole thing, and the title as an H1 the editor already shows."""
    text = markdown.strip()
    fenced = _FENCE_RE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    return _H1_RE.sub("", text, count=1).strip() + "\n"


def draft(query: str, language: str, project_slug: str = "") -> dict:
    """{title, markdown, sources: [{title, project_slug, page_slug}]}, or
    doc_chat.ChatError ("not_configured", "empty_question", or a provider
    failure)."""
    query = " ".join(query.split())[:MAX_QUERY]
    if not query:
        raise doc_chat.ChatError("empty_question")
    if not doc_chat.is_enabled():
        raise doc_chat.ChatError("not_configured")
    hits = _sources(query, language, project_slug)
    material = _context(hits) if hits else "(none -- the documentation has nothing related yet)"
    body = doc_chat._post_chat(
        [
            {"role": "system", "content": _PROMPT.format(language_name=doc_chat._language_name(language))},
            {"role": "user", "content": f"Topic readers searched for: {query}\n\nSources:\n\n{material}"},
        ],
        max_tokens=1500,
    )
    return {
        "title": query[:1].upper() + query[1:],
        "markdown": clean(body),
        "sources": [
            {"title": h["title"], "project_slug": h["project_slug"], "page_slug": h["page_slug"]} for h in hits
        ],
    }
