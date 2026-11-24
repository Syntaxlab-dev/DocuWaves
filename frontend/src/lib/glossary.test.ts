import { describe, expect, it } from "vitest";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkRehype from "remark-rehype";
import type { Element, Root, RootContent } from "hast";
import { rehypeGlossary } from "@/lib/glossary";

/** Just enough HTML to compare: elements and text, glossary spans with their index. */
function html(node: Root | RootContent): string {
  if (node.type === "text") return node.value;
  if (node.type === "root") return node.children.map(html).join("");
  if (node.type !== "element") return "";
  const element = node as Element;
  const inner = element.children.map(html).join("");
  const mark = element.properties?.dataGlossary;
  return mark !== undefined ? `<span data-glossary="${String(mark)}">${inner}</span>` : `<${element.tagName}>${inner}</${element.tagName}>`;
}

function render(markdown: string, terms: { term: string; definition: string }[]): string {
  const processor = unified().use(remarkParse).use(remarkRehype).use(rehypeGlossary(terms));
  const tree = processor.runSync(processor.parse(markdown)) as Root;
  return html(tree);
}

const TERMS = [
  { term: "SLA", definition: "Service level." },
  { term: "Deployment", definition: "Shipping." },
  { term: "API key", definition: "A secret." },
  { term: "API", definition: "Interface." },
];

describe("rehypeGlossary", () => {
  it("marks the first use of each term only", () => {
    const html = render("Our SLA and the SLA again.", TERMS);
    expect(html.match(/data-glossary/g)?.length).toBe(1);
    expect(html).toContain('<span data-glossary="0">SLA</span> and the SLA again');
  });

  it("matches words in any case, acronyms only as written", () => {
    expect(render("every deployment counts", TERMS)).toContain('<span data-glossary="1">deployment</span>');
    expect(render("see /docs/sla-page", TERMS)).not.toContain("data-glossary");
  });

  it("never inside part of a longer word, a link, code or a heading", () => {
    expect(render("Redeployments happen.", TERMS)).not.toContain("data-glossary");
    expect(render("[the SLA](/x) and `SLA`\n\n## SLA", TERMS)).not.toContain("data-glossary");
  });

  it("prefers the longer term", () => {
    const html = render("Keep the API key safe, the API is public.", TERMS);
    expect(html).toContain('<span data-glossary="2">API key</span>');
    expect(html).toContain('<span data-glossary="3">API</span> is public');
  });

  it("handles letters beyond ASCII", () => {
    const html = render("Die Übergabe und Übergaben.", [{ term: "Übergabe", definition: "x" }]);
    expect(html).toContain('Die <span data-glossary="0">Übergabe</span> und Übergaben.');
  });
});
