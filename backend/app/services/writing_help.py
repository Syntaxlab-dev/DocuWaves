"""Writing help in the editor: rephrase, shorten, simplify, correct or
summarise the text an author has selected, with the documentation chat's
model (services/doc_chat.py, CHAT_* settings).

THE RULES ARE THE DRAFT'S RULES (services/gap_drafts.py), applied to
editing: the model works on the selected text only and may not add a fact
that is not in it -- no command, setting, version or number from its
general knowledge. Markdown stays Markdown: links keep their targets, code
spans and code blocks are not touched, callouts and lists keep their
markers.

Nothing is saved here. The suggestion goes back to the editor, the author
sees it next to the original and decides whether it replaces the
selection; only their own save writes anything.
"""
from app.services import doc_chat, gap_drafts

MAX_TEXT = 8000

ACTIONS = {
    "rephrase": "Rephrase the text so it reads clearly and naturally. Keep its meaning, its length roughly, "
    "and every fact in it.",
    "shorten": "Make the text noticeably shorter -- about half, where that is possible without losing a fact a "
    "reader needs. Drop filler and repetition, not information.",
    "simplify": "Rewrite the text in plain, simple language for a reader who is new to the topic: short "
    "sentences, everyday words, the same facts.",
    "fix": "Correct spelling, grammar and punctuation only. Change nothing else: not the wording, not the "
    "order, not the tone.",
    "summarize": "Write a short summary of the text: two to four sentences, or a short bulleted list when the "
    "text is a sequence of steps or points.",
}

_PROMPT = (
    "You help an author edit a page of technical documentation written in Markdown. Task:\n"
    "{task}\n"
    "\n"
    "Rules, in order of importance:\n"
    "1. Use ONLY what the text says. Never add facts, commands, settings, versions, numbers or examples "
    "from general knowledge. If the text is wrong, do not correct its facts -- only its language.\n"
    "2. Keep the Markdown: links with their exact targets, images, `code` and code blocks unchanged, "
    "headings, lists and callouts (`> [!NOTE]`) with their markers.\n"
    "3. Write in {language_name}, the language of the text.\n"
    "4. Output only the resulting Markdown -- no explanation, no quotes around it, no heading of your own."
)


def rewrite(text: str, action: str, language: str) -> str:
    """The suggestion, or doc_chat.ChatError ("not_configured",
    "empty_question", "unknown_action", "too_long" or a provider failure)."""
    if action not in ACTIONS:
        raise doc_chat.ChatError("unknown_action")
    if not text.strip():
        raise doc_chat.ChatError("empty_question")
    if len(text) > MAX_TEXT:
        raise doc_chat.ChatError("too_long")
    if not doc_chat.is_enabled():
        raise doc_chat.ChatError("not_configured")
    answer = doc_chat._post_chat(
        [
            {
                "role": "system",
                "content": _PROMPT.format(task=ACTIONS[action], language_name=doc_chat._language_name(language)),
            },
            {"role": "user", "content": text},
        ],
        # Room for the whole selection rewritten, a bit longer at most.
        max_tokens=min(4000, max(300, len(text) // 2)),
    )
    # Models like to fence the whole answer; the fence is not part of it.
    fenced = gap_drafts._FENCE_RE.match(answer.strip())
    result = (fenced.group(1) if fenced else answer).strip() + "\n"
    # A selection that ended mid-line must not grow a line break.
    return result if text.endswith("\n") else result.rstrip("\n")
