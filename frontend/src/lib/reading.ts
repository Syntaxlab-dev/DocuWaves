/**
 * Roughly how long a page takes to read, in whole minutes -- shown next to
 * "last updated" so a reader knows what they are about to commit to.
 *
 * Words of prose at ~200 a minute, the usual figure for technical text (it is
 * read more slowly than a novel). Fenced code and Mermaid source are left out:
 * a reader scans a 40-line config file, they don't read it word by word, and
 * counting it would make every page with an example look twice as long.
 * 0 for a page with (next to) no prose, which then shows no reading time.
 */
const WORDS_PER_MINUTE = 200;

export function readingTime(markdown: string): number {
  const prose = markdown
    .replace(/^(`{3,}|~{3,})[^\n]*\n[\s\S]*?^\1[ \t]*$/gm, " ")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[#>*_`|~-]+/g, " ");
  const words = prose.split(/\s+/).filter((word) => /[\p{L}\p{N}]/u.test(word)).length;
  if (words < 60) return 0;
  return Math.max(1, Math.round(words / WORDS_PER_MINUTE));
}
