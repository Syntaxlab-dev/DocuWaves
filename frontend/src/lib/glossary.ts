import { useEffect, useState } from "react";
import type { Element, ElementContent, Root, RootContent, Text } from "hast";
import { api } from "@/lib/api";

/**
 * The glossary (backend services/glossary.py): terms a project defines,
 * shown as a tooltip where a page uses them.
 *
 * Marked at render time by a rehype plugin rather than by walking the DOM
 * afterwards: React owns that DOM, and a text node replaced behind its back
 * is one it later fails to update. The plugin wraps the FIRST use of each
 * term on a page in `<span data-glossary="n">`, and MarkdownView renders
 * that span as a GlossaryTerm.
 */
export type GlossaryEntry = { term: string; definition: string };

/** Never inside these: a link already leads somewhere, code is literal,
 *  a heading is a heading. */
const SKIP = new Set(["a", "code", "pre", "kbd", "samp", "h1", "h2", "h3", "h4", "h5", "h6", "button", "script", "style"]);

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** "SLA" (no lowercase letter) matches only as written; "Deployment"
 *  matches in any case. Letters or digits next to it mean it is part of a
 *  longer word, which is not a use of the term. */
function matcher(term: string): RegExp {
  const caseSensitive = term === term.toUpperCase();
  return new RegExp(`(?<![\\p{L}\\p{N}])${escapeRegExp(term)}(?![\\p{L}\\p{N}])`, caseSensitive ? "u" : "iu");
}

export function rehypeGlossary(terms: GlossaryEntry[]) {
  // Longest first, so "API key" is found before "API" can claim its first word.
  const order = terms
    .map((entry, index) => ({ index, re: matcher(entry.term), length: entry.term.length }))
    .sort((a, b) => b.length - a.length);

  return () => (tree: Root) => {
    const pending = new Set(order.map((o) => o.index));

    function split(node: Text): ElementContent[] | null {
      let best: { start: number; end: number; index: number } | null = null;
      for (const { index, re } of order) {
        if (!pending.has(index)) continue;
        const found = re.exec(node.value);
        if (found && (best === null || found.index < best.start)) {
          best = { start: found.index, end: found.index + found[0].length, index };
        }
      }
      if (!best) return null;
      pending.delete(best.index);
      const out: ElementContent[] = [];
      if (best.start > 0) out.push({ type: "text", value: node.value.slice(0, best.start) });
      out.push({
        type: "element",
        tagName: "span",
        properties: { dataGlossary: String(best.index) },
        children: [{ type: "text", value: node.value.slice(best.start, best.end) }],
      });
      const rest: Text = { type: "text", value: node.value.slice(best.end) };
      if (rest.value) out.push(...(split(rest) ?? [rest]));
      return out;
    }

    function walk(parent: Root | Element) {
      const next: (RootContent | ElementContent)[] = [];
      for (const child of parent.children) {
        if (pending.size === 0) {
          next.push(child);
          continue;
        }
        if (child.type === "text") {
          const replaced = split(child);
          next.push(...(replaced ?? [child]));
        } else if (child.type === "element") {
          if (!SKIP.has(child.tagName) && child.properties?.dataGlossary === undefined) walk(child);
          next.push(child);
        } else {
          next.push(child);
        }
      }
      parent.children = next as typeof parent.children;
    }

    if (order.length) walk(tree);
  };
}

const cache = new Map<string, Promise<GlossaryEntry[]>>();

/** The project's terms, fetched once per project, language and version. */
export function useGlossary(projectSlug?: string, lang?: string, version?: string): GlossaryEntry[] {
  const [terms, setTerms] = useState<GlossaryEntry[]>([]);
  useEffect(() => {
    if (!projectSlug) {
      setTerms([]);
      return;
    }
    const key = `${projectSlug}|${lang ?? ""}|${version ?? ""}`;
    let request = cache.get(key);
    if (!request) {
      request = api
        .publicGlossary(projectSlug, lang, version)
        .then((r) => r.terms)
        .catch(() => {
          cache.delete(key);
          return [];
        });
      cache.set(key, request);
    }
    let alive = true;
    void request.then((loaded) => alive && setTerms(loaded));
    return () => {
      alive = false;
    };
  }, [projectSlug, lang, version]);
  return terms;
}
