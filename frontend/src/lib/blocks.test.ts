import { describe, expect, it } from "vitest";
import { unified } from "unified";
import remarkParse from "remark-parse";
import { remarkBlocks } from "@/lib/blocks";

type Node = { type: string; value?: string; children?: Node[]; data?: { hName?: string; hProperties?: Record<string, unknown> } };

function tree(markdown: string): Node {
  const processor = unified().use(remarkParse).use(remarkBlocks);
  return processor.runSync(processor.parse(markdown)) as Node;
}

function classes(node?: Node): unknown {
  return node?.data?.hProperties?.className;
}

describe("remarkBlocks", () => {
  it("turns the list after <!-- steps --> into steps and drops the marker", () => {
    const root = tree("<!-- steps -->\n1. One\n2. Two\n");
    expect(root.children?.map((c) => c.type)).toEqual(["list"]);
    expect(classes(root.children?.[0])).toEqual(["steps"]);
  });

  it("turns the list after <!-- cards --> into cards, linked ones marked", () => {
    const root = tree("<!-- cards -->\n- **[A](/a)** First\n- **B** Second\n");
    const list = root.children?.[0];
    expect(classes(list)).toEqual(["cards"]);
    expect(classes(list?.children?.[0])).toEqual(["card", "card-linked"]);
    expect(classes(list?.children?.[1])).toEqual(["card"]);
  });

  it("drops a marker with no list after it", () => {
    const root = tree("<!-- steps -->\n\nJust text.\n");
    expect(root.children?.map((c) => c.type)).toEqual(["paragraph"]);
  });

  it("makes badges of `badge:` code, with an optional colour", () => {
    const paragraph = tree("New `badge:Beta` and `badge:warning:Old` but `badge:` and `code`.").children?.[0];
    const badges = paragraph?.children?.filter((c) => c.type === "badge") ?? [];
    expect(badges.map((b) => [classes(b), b.children?.[0].value])).toEqual([
      [["badge", "badge-info"], "Beta"],
      [["badge", "badge-warning"], "Old"],
    ]);
    expect(paragraph?.children?.filter((c) => c.type === "inlineCode").map((c) => c.value)).toEqual(["badge:", "code"]);
  });

  it("leaves fenced code alone", () => {
    const root = tree("```\n`badge:Beta`\n<!-- steps -->\n```\n");
    expect(root.children?.[0].type).toBe("code");
  });
});
