/** Words in a Markdown text, as a reader would count them: code blocks,
 *  link targets, image paths and HTML tags are not words. */
export function wordCount(markdown: string): number {
  const prose = markdown
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/~~~[\s\S]*?~~~/g, " ")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\]\([^)]*\)/g, "] ")
    .replace(/<[^>]+>/g, " ");
  return (prose.match(/[\p{L}\p{N}][\p{L}\p{N}'’_-]*/gu) ?? []).length;
}

/** Minutes to read at a steady 200 words a minute, at least 1. */
export function readingMinutes(words: number): number {
  return Math.max(1, Math.round(words / 200));
}

/** The first lines of prose in a Markdown text as plain text, cut at a word
 *  boundary to about `max` characters -- for a teaser under a link. */
export function excerpt(markdown: string, max = 140): string {
  const prose = markdown
    .replace(/<!--[\s\S]*?-->/g, "\n")
    .replace(/```[\s\S]*?```/g, "\n")
    .replace(/~~~[\s\S]*?~~~/g, "\n")
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter((block) => block && !/^(#|\||>\s*\[!|!\[|<|-{3,}|\$\$|:::)/.test(block))
    .map((block) =>
      block
        .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
        .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
        .replace(/^\s*(?:[-*+]|\d+\.|>)\s+/gm, "")
        .replace(/[*_`~]+/g, "")
        .replace(/\s+/g, " ")
        .trim(),
    )
    .filter(Boolean);
  const text = prose[0] ?? "";
  if (text.length <= max) return text;
  const cut = text.slice(0, max);
  return `${cut.slice(0, Math.max(cut.lastIndexOf(" "), max * 0.6)).replace(/[,;:.\s]+$/, "")}…`;
}
