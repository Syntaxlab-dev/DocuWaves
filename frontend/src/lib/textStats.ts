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
