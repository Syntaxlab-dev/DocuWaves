/**
 * The one place heading anchor ids are decided.
 *
 * Both consumers -- MarkdownView, which puts the `id` on the rendered
 * `<h2>`/`<h3>`, and TableOfContents, which links to it -- call
 * collectHeadings() on the same Markdown source, so a link can never point
 * at an id the renderer spells differently. Two independent slugifiers
 * (one over the source text, one over the rendered DOM text) would look
 * identical right up until the first heading containing a link, a code
 * span, or a duplicate title, and then drift apart silently.
 *
 * Matching a rendered heading back to its entry is done by SOURCE LINE, not
 * by document order: react-markdown hands each component the original hast
 * node, whose `position` survives the Markdown -> hast conversion, so the
 * lookup needs no counter that has to be reset per render pass and stays
 * correct no matter what order React happens to render in.
 */

export interface Heading {
  /** 1-based line in the Markdown source the heading starts on. */
  line: number;
  level: 2 | 3;
  /** Display text: the heading's inline Markdown, flattened. */
  text: string;
  id: string;
}

/** Opening or closing fence of a fenced code block. A `## ...` line inside
 *  one is code, never a heading, and must not end up in the contents. */
const FENCE = /^ {0,3}(`{3,}|~{3,})/;

/** ATX heading, h2/h3 only -- with GFM's optional closing run of `#`
 *  (`## Title ##`) stripped, which is part of the syntax, not the title. */
const ATX_HEADING = /^ {0,3}(#{2,3})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$/;

export function slugifyHeading(text: string): string {
  const slug = text
    .toLowerCase()
    // \p{L}/\p{N} rather than a-z0-9: this instance's docs are written in
    // German too, and mangling "Fehlerbehebung für Umlaute" into an
    // ASCII-only id would make deep links unreadable for no benefit --
    // a fragment is percent-encoded by the browser either way.
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .trim()
    .replace(/[\s-]+/g, "-");
  return slug || "section";
}

/** Inline Markdown flattened to the text a reader actually sees, so the
 *  contents entry for `## Using \`--force\`` reads "Using --force" and its
 *  id is derived from the same string. */
export function inlineText(markdown: string): string {
  return markdown
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[`*~]/g, "")
    .trim();
}

/**
 * Every h2/h3 in a page, in source order, with a unique id each.
 *
 * Setext headings (`Title` underlined with `---`) are not collected: they'd
 * need the paragraph-level context this line scanner doesn't have, and a
 * page written in this CMS uses the `##` form the README documents. One
 * written the other way simply gets no anchor -- it is equally absent from
 * the contents, so nothing links to an id that was never emitted.
 */
export function collectHeadings(markdown: string): Heading[] {
  const headings: Heading[] = [];
  const used = new Set<string>();
  let fence: string | null = null;

  markdown.split("\n").forEach((line, index) => {
    const fenceMatch = FENCE.exec(line);
    if (fence !== null) {
      // A fence only closes on the same character, at least as long as the
      // one that opened it -- ```` inside a ``` block is content.
      if (fenceMatch && fenceMatch[1][0] === fence[0] && fenceMatch[1].length >= fence.length) fence = null;
      return;
    }
    if (fenceMatch) {
      fence = fenceMatch[1];
      return;
    }

    const match = ATX_HEADING.exec(line);
    if (!match) return;
    const text = inlineText(match[2]);
    if (!text) return;

    const base = slugifyHeading(text);
    let id = base;
    // Two "Installation" headings must not fight over one id, and the
    // suffix has to be checked against ids already handed out rather than
    // just a per-base counter: a page can also contain a heading literally
    // called "Installation 2".
    for (let n = 2; used.has(id); n += 1) id = `${base}-${n}`;
    used.add(id);

    headings.push({ line: index + 1, level: match[1].length as 2 | 3, text, id });
  });

  return headings;
}

/** ATX h1 -- only ever matched against the FIRST content line, so a `#`
 *  inside a fenced block can't reach it. */
const LEADING_H1 = /^ {0,3}#[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$/;

function normalize(text: string): string {
  return inlineText(text).toLowerCase().replace(/\s+/g, " ").trim();
}

/**
 * Drops the body's opening `# Title` when it just repeats the page title
 * that is already rendered above it.
 *
 * Only that exact case: an opening h1 saying something *different* is the
 * author making a point and is left alone, and an h1 further down the page
 * is a section, not a title. Comparing flattened inline text rather than
 * the raw source means `# Using \`--force\`` still matches a title of
 * "Using --force".
 */
export function stripRedundantTitle(markdown: string, title?: string): string {
  if (!title) return markdown;
  const lines = markdown.split("\n");
  const first = lines.findIndex((line) => line.trim() !== "");
  if (first === -1) return markdown;

  const match = LEADING_H1.exec(lines[first]);
  if (!match || normalize(match[1]) !== normalize(title)) return markdown;

  // Drop the heading and the blank line that followed it, so the body
  // doesn't start with a gap where the heading used to be.
  let next = first + 1;
  if (lines[next]?.trim() === "") next += 1;
  return [...lines.slice(0, first), ...lines.slice(next)].join("\n");
}
