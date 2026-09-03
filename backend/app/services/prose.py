"""Turning Markdown back into readable prose.

Two callers need this and they need slightly different things:

- The SEO layer wants a page's OPENING paragraph, and only if it is real
  prose -- a description that reads "``` bash" describes nothing.
- Search wants the WHOLE page as plain text, so it can cut a window around
  wherever the reader's words actually appear.

Both start from the same problem, which is why the stripping rules live here
rather than in either caller. The rules are deliberately textual, not a real
Markdown parse: a description and a search snippet are throwaway strings, and
pulling a parser into the request path to build them would cost far more than
the occasional stray character it would save.
"""
import re

_FENCE_RE = re.compile(r"^\s{0,3}(?:```|~~~)")
_SKIP_RE = re.compile(
    r"^\s{0,3}(?:"
    r"#"  # heading
    r"|\|"  # table row
    r"|(?:[-*_]\s*){3,}$"  # thematic break
    r"|<"  # raw HTML, an HTML comment, a badge block
    r"|!\["  # an image (or a row of shield badges) on its own line
    r"|={2,}$"  # a setext underline that outran its heading
    r")"
)
_LIST_MARKER_RE = re.compile(r"^\s{0,3}(?:[-*+]\s+|\d+[.)]\s+|>\s?)+")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TAG_RE = re.compile(r"<[^>]{0,200}>")
_NOISE_RE = re.compile(r"[`*~]+")
_SPACE_RE = re.compile(r"\s+")

_HEADING_MARKER_RE = re.compile(r"^\s{0,3}#{1,6}\s*")
_TABLE_DIVIDER_RE = re.compile(r"^\s{0,3}\|?[\s:|-]+\|[\s:|-]*$")
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)

_MAX_SCAN_LINES = 400
#: Past this much Markdown a page is an outlier, and a snippet is not worth
#: the scan. Cutting here bounds the cost of a search across many long pages.
_MAX_PROSE_CHARS = 40_000


def clip(text: str, limit: int) -> str:
    """Cut to `limit` on a word boundary, with an ellipsis. A single word
    longer than the limit is cut where it is -- better a hard cut than a
    description that is empty."""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[: limit + 1]
    cut = head.rsplit(" ", 1)[0] if " " in head else text[:limit]
    return cut.rstrip(" ,;:.-–—") + "…"


def _inline(text: str) -> str:
    """Strip the inline markers that survive a line-level pass."""
    text = _IMAGE_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)  # link text, without the URL
    text = _TAG_RE.sub("", text)
    # Backticks, ** and ~~ removed; `_` deliberately left alone, because it
    # is far more often part of an identifier (snake_case, a CLI flag) than
    # an emphasis marker, and eating it would corrupt the very words a
    # technical description exists to carry.
    return _NOISE_RE.sub("", text)


def first_paragraph(markdown: str, limit: int) -> str:
    """A page's first paragraph of actual PROSE, as a plain sentence.

    "Prose" is defined by what it is not: not the title, not a heading, not
    inside a fenced code block (or a mermaid diagram, which is one), not a
    table, not a horizontal rule, not a row of badge images, not raw HTML.
    Those are what documentation pages open with, and any of them as a
    description would describe nothing.

    Blockquotes and list items DO count, with their markers stripped: plenty
    of good pages open with a callout or a list, and the first item of one
    still says more about the page than the site's tagline does.
    """
    lines: list[str] = []
    in_fence = False
    # Neither caller is handed frontmatter today -- content_files parses it
    # off before a body reaches the index -- but to_prose() strips it, and
    # one of the two quietly not doing so is the kind of difference that is
    # only discovered by a description reading "title: Installing".
    markdown = _FRONTMATTER_RE.sub("", markdown)
    for index, raw in enumerate(markdown.splitlines()):
        if index >= _MAX_SCAN_LINES:
            break
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = raw.strip()
        if not line:
            # A blank line ends the paragraph once one has started, and is
            # simply skipped before that.
            if lines:
                break
            continue
        if _SKIP_RE.match(line):
            if lines:
                break
            continue
        lines.append(_LIST_MARKER_RE.sub("", line))

    if not lines:
        return ""
    return clip(_SPACE_RE.sub(" ", _inline(" ".join(lines))), limit)


def to_prose(markdown: str) -> str:
    """The WHOLE page as one line of plain text, for searching within.

    Unlike `first_paragraph` this keeps almost everything, because a snippet
    has to be able to land wherever the match is:

    - Headings keep their text; a hit in a heading is a good hit.
    - Fenced code keeps its CONTENT. Readers search documentation for exact
      strings -- an environment variable, a CLI flag -- and those often
      appear only inside a code sample. Dropping code would send the snippet
      somewhere the reader's words are not.
    - Tables keep their cell text; only the pipes and the divider row go.
    - Images go entirely: alt text is rarely the thing that matched, and a
      URL in a snippet is noise.
    """
    markdown = _FRONTMATTER_RE.sub("", markdown[:_MAX_PROSE_CHARS])
    out: list[str] = []
    for raw in markdown.splitlines():
        if _FENCE_RE.match(raw):
            continue  # the fence line itself, and its language tag
        line = raw.strip()
        if not line or _TABLE_DIVIDER_RE.match(line):
            continue
        line = _HEADING_MARKER_RE.sub("", line)
        line = _LIST_MARKER_RE.sub("", line)
        line = line.replace("|", " ")
        line = _inline(line)
        line = line.strip()
        if line:
            out.append(line)
    return _SPACE_RE.sub(" ", " ".join(out)).strip()


def terms_of(query: str) -> list[str]:
    """The words a snippet should try to show, longest first.

    Longest first because the long words are the specific ones. Searching
    "reverse proxy port" against a page that says "port" forty times and
    "reverse proxy" once, the one useful window is the one with the phrase
    in it, and ordering the terms this way makes the tie-break below prefer
    it without needing to weigh anything.
    """
    words = {w for w in re.findall(r"[\w./-]{2,}", query.lower())}
    return sorted(words, key=len, reverse=True)


#: How far before the first match the window opens, so a hit is not flush
#: against the left edge with no run-up.
_LEAD_IN = 45


def snippet(text: str, terms: list[str], limit: int = 220) -> str:
    """A window of `text` around the densest cluster of `terms`.

    Density, not first-occurrence: a page that mentions one search word in
    passing at the top and discusses all of them together further down
    should show the discussion. Windows are scored by how many DISTINCT
    terms they contain, so one word repeated cannot outrank a real cluster.

    Falls back to the opening of the text when nothing matches -- which
    happens legitimately, because the index and this function do not
    tokenise identically (a stemmed or prefix match can be a true hit whose
    literal characters are not here).
    """
    if not text:
        return ""
    if not terms:
        return clip(text, limit)

    lowered = text.lower()
    # (position, which term) for every occurrence, in document order.
    hits: list[tuple[int, str]] = []
    for term in terms:
        start = lowered.find(term)
        while start != -1:
            hits.append((start, term))
            start = lowered.find(term, start + 1)
    if not hits:
        return clip(text, limit)
    hits.sort()

    best_start, best_score = hits[0][0], -1
    for index, (position, _) in enumerate(hits):
        distinct = set()
        for other_position, other_term in hits[index:]:
            if other_position >= position + limit:
                break
            distinct.add(other_term)
        # Ties keep the EARLIER window: `>` rather than `>=`. Documentation
        # tends to introduce a subject before elaborating on it, so the
        # first place a cluster appears is usually the explanation.
        if len(distinct) > best_score:
            best_start, best_score = position, len(distinct)

    start = max(0, best_start - _LEAD_IN)
    if start > 0:
        # Do not open mid-word.
        space = text.find(" ", start)
        start = space + 1 if space != -1 and space < best_start else start
    window = text[start : start + limit]
    if start + limit < len(text):
        window = window.rsplit(" ", 1)[0] if " " in window else window
        window = window.rstrip(" ,;:.-–—") + "…"
    return ("…" + window) if start > 0 else window
