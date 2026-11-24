"""A first draft of a translation, from the page's text in another language,
with the documentation chat's model (services/doc_chat.py, CHAT_*).

It fills the editor of a translation that does not exist yet. Nothing is
saved and nothing is published: the author reads it, corrects it and saves
it like any page they wrote themselves -- in a project with approval, it
then goes through review like any other change. A machine translation that
went live unread would put words under the owner's name that nobody of
theirs has checked.

WHAT IS NOT TRANSLATED. Code blocks and inline code are taken out before
the text goes to the model and put back afterwards, so a command can never
be "translated"; link targets, image paths and `{{variables}}` are kept as
they are by instruction. A long page is sent in sections (at its `## `
headings), so a page of any length fits the model's limits.
"""
import re

from app.services import doc_chat, gap_drafts

MAX_TEXT = 60000
_CHUNK = 6000
_FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})[^\n]*\n.*?^\1\2[ \t]*$", re.MULTILINE | re.DOTALL)
_INLINE = re.compile(r"(`+)(?!`).+?(?<!`)\1(?!`)")
_TOKEN = "⟦C{}⟧"  # ⟦C0⟧: nothing a writer types, nothing a model "translates"
_TOKEN_RE = re.compile("⟦C(\\d+)⟧")

_PROMPT = (
    "You translate a page of technical documentation from {source} to {target}. The text is Markdown.\n"
    "\n"
    "Rules:\n"
    "1. Translate faithfully: the same facts, the same structure, nothing added or left out. Use the "
    "terms a {target}-speaking technical reader expects; keep product names, commands and UI labels "
    "that are not {source} words as they are.\n"
    "2. Keep all Markdown exactly: headings, lists, tables, callout markers like `> [!NOTE]`, link "
    "targets and image paths (translate only the visible link text), and every `{{{{name}}}}` variable.\n"
    "3. Keep every placeholder of the form ⟦C0⟧, ⟦C1⟧ ... exactly as it is, in place. "
    "They stand for code.\n"
    "4. Output only the translated Markdown, nothing else."
)


def language_name(code: str) -> str:
    known = doc_chat._LANGUAGE_NAMES.get(code)
    return known or f"the language with the ISO code '{code}'"


def _protect(text: str) -> tuple[str, list[str]]:
    kept: list[str] = []

    def keep(match: re.Match) -> str:
        kept.append(match.group(0))
        return _TOKEN.format(len(kept) - 1)

    text = _FENCE.sub(keep, text)
    text = _INLINE.sub(keep, text)
    return text, kept


def _restore(text: str, kept: list[str]) -> str:
    return _TOKEN_RE.sub(lambda m: kept[int(m.group(1))] if int(m.group(1)) < len(kept) else m.group(0), text)


def _chunks(text: str) -> list[str]:
    """Sections at `## ` headings, packed together up to _CHUNK characters."""
    sections = re.split(r"(?m)^(?=## )", text)
    chunks: list[str] = []
    for section in sections:
        if chunks and len(chunks[-1]) + len(section) <= _CHUNK:
            chunks[-1] += section
        else:
            chunks.append(section)
    return [c for c in chunks if c.strip()]


def _translate(text: str, source: str, target: str) -> str:
    answer = doc_chat._post_chat(
        [
            {"role": "system", "content": _PROMPT.format(source=language_name(source), target=language_name(target))},
            {"role": "user", "content": text},
        ],
        max_tokens=min(8000, max(400, len(text))),
    )
    fenced = gap_drafts._FENCE_RE.match(answer.strip())
    return fenced.group(1).strip() if fenced else answer.strip()


def draft(title: str, markdown: str, source: str, target: str) -> dict:
    """{title, markdown, missing_code: n}, or doc_chat.ChatError
    ("not_configured", "empty_question", "too_long", "same_language" or a
    provider failure)."""
    if not markdown.strip() and not title.strip():
        raise doc_chat.ChatError("empty_question")
    if len(markdown) > MAX_TEXT:
        raise doc_chat.ChatError("too_long")
    if not source or not target or source == target:
        raise doc_chat.ChatError("same_language")
    if not doc_chat.is_enabled():
        raise doc_chat.ChatError("not_configured")

    protected, kept = _protect(markdown.replace("\r\n", "\n"))
    parts = [_translate(chunk, source, target) for chunk in _chunks(protected)]
    body = "\n\n".join(p.strip("\n") for p in parts)
    used = {int(n) for n in _TOKEN_RE.findall(body)}
    # A placeholder the model dropped is code that would silently be gone:
    # it is said, and the code is appended where the author will see it.
    missing = [i for i in range(len(kept)) if i not in used]
    body = _restore(body, kept)
    if missing:
        body += "\n\n" + "\n\n".join(kept[i] for i in missing)
    translated_title = _translate(title, source, target).splitlines()[0].lstrip("# ").strip() if title.strip() else ""
    return {"title": translated_title, "markdown": body.strip() + "\n", "missing_code": len(missing)}
