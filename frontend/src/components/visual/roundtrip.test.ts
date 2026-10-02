/**
 * The visual editor's promise: a page edited visually loses nothing. These
 * pin down which Markdown it carries through unchanged (as a document -- see
 * lib/markdownTree.ts), and run every page of DocuWaves' own documentation
 * (docs/) through it as a real-world corpus.
 */
import { readFileSync, readdirSync, statSync } from "fs";
import path from "path";
import { describe, expect, it } from "vitest";
import { editableVisually, visualRoundTrip } from "./milkdown";
import { firstDifference, sameDocument } from "@/lib/markdownTree";

async function survives(markdown: string) {
  const out = await visualRoundTrip(markdown);
  expect(sameDocument(markdown, out), firstDifference(markdown, out)).toBe(true);
  return out;
}

describe("what the visual editor carries through", () => {
  const cases: Record<string, string> = {
    headings: "# One\n\n## Two\n\n### Three\n\nText.\n",
    emphasis: "Some **bold**, *italic*, ~~gone~~ and `code`.\n",
    links: "A [link](https://example.com \"title\") and <https://example.com>.\n",
    "reference links (become inline)": "A [link][ref].\n\n[ref]: https://example.com\n",
    images: "![A diagram](../assets/plan.png)\n",
    lists: "- one\n- two\n  - nested\n\n1. first\n2. second\n",
    "task lists": "- [x] done\n- [ ] open\n",
    quotes: "> A quote\n> over two lines.\n",
    callouts: "> [!WARNING]\n> Back up first.\n",
    "code with a language": "```bash\ndocker compose up -d\n```\n",
    "code with a file name": '```python title="app/main.py"\nprint(1)\n```\n',
    tables: "| A | B |\n|---|:-:|\n| 1 | 2 |\n",
    "a horizontal rule": "Above\n\n---\n\nBelow\n",
    variables: "Runs on port {{port}} for {{product}}.\n",
    "hard breaks": "Line one\\\nline two\n",
    "inline formulas": "Euler: $e^{i\\pi}+1=0$ and $a_1 + b_2$.\n",
    "formula blocks": "$$\n\\int_0^1 x^2\\,dx = \\frac{1}{3}\n$$\n",
    "diagrams": "```mermaid\ngraph LR\n  A --> B\n```\n",
  };
  for (const [name, markdown] of Object.entries(cases)) {
    it(name, async () => {
      await survives(markdown);
    });
  }

  it("keeps a callout's marker as written", async () => {
    const out = await survives("> [!WARNING]\n> Back up first.\n");
    expect(out).toContain("> [!WARNING]");
    expect(out).not.toContain("\\[");
  });

  it("writes tables without padding", async () => {
    const out = await survives("| Service | Port |\n|---|---|\n| Web | 8080 |\n");
    expect(out).toContain("| Web | 8080 |");
    expect(out).toContain("|---|---|");
  });

  it("writes bullets with - and keeps doing so", async () => {
    const out = await survives("* one\n* two\n");
    expect(out).toContain("- one");
    expect(await visualRoundTrip(out)).toBe(out);
  });
});

describe("what makes a page open in Markdown instead", () => {
  // Not lost -- refused: the round-trip check catches each of these, and the
  // page stays in the Markdown editor until the visual one learns them.
  const cases: Record<string, string> = {
    "raw HTML": "<details><summary>More</summary>\n\nHidden.\n\n</details>\n",
  };
  for (const [name, markdown] of Object.entries(cases)) {
    it(name, async () => {
      // Either the visual editor keeps it, or the check says no -- never a
      // silent loss. Both are acceptable; a lossy "yes" is the bug.
      const ok = await editableVisually(markdown);
      if (ok) expect(sameDocument(markdown, await visualRoundTrip(markdown))).toBe(true);
    });
  }
});

describe("DocuWaves' own documentation", () => {
  const root = path.resolve(import.meta.dirname, "../../../../docs");
  const pages: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const full = path.join(dir, name);
      if (statSync(full).isDirectory()) walk(full);
      else if (name.endsWith(".md")) pages.push(full);
    }
  };
  walk(root);
  const body = (file: string) => readFileSync(file, "utf-8").replace(/^---\n[\s\S]*?\n---\n/, "");

  it("has pages to test with", () => {
    expect(pages.length).toBeGreaterThan(40);
  });

  it("every one of them can be edited visually", async () => {
    const lossy: string[] = [];
    for (const file of pages) {
      const markdown = body(file);
      if (!sameDocument(markdown, await visualRoundTrip(markdown))) lossy.push(path.relative(root, file));
    }
    expect(lossy).toEqual([]);
  });

  it("and saving one unchanged changes nothing but blank lines", async () => {
    // The promise behind "visual by default": opening an existing page and
    // saving it leaves (almost) no trace in its history. The one thing it
    // may change is a blank line between two blocks that had none -- a
    // heading straight above a code block, as in a tab group.
    const lines = (text: string) => text.split("\n").filter((line) => line.trim() !== "");
    const rewritten: string[] = [];
    let identical = 0;
    for (const file of pages) {
      const markdown = body(file).replace(/^\n+/, "");
      const out = await visualRoundTrip(markdown);
      if (out.trimEnd() === markdown.trimEnd()) identical += 1;
      if (lines(out).join("\n") !== lines(markdown).join("\n")) rewritten.push(path.relative(root, file));
    }
    expect(rewritten).toEqual([]);
    expect(identical).toBeGreaterThanOrEqual(pages.length - 2);
  });

  for (const file of pages) {
    const name = path.relative(root, file);
    it(`${name}: visual or Markdown, never lossy`, async () => {
      const markdown = body(file);
      const out = await visualRoundTrip(markdown);
      const ok = sameDocument(markdown, out);
      // The check and the editor agree...
      expect(await editableVisually(markdown)).toBe(ok);
      // ...and once written by the visual editor, a page stays as it is.
      if (ok) expect(await visualRoundTrip(out)).toBe(out);
    });
  }
});

describe("DocuWaves' blocks in the visual editor", () => {
  it("a callout is a box that knows its kind", async () => {
    const root = document.createElement("div");
    const { createVisualEditor } = await import("./milkdown");
    const handle = await createVisualEditor({ root, markdown: "> [!CAUTION]\n> Deletes everything.\n" });
    const box = root.querySelector("blockquote");
    expect(box?.getAttribute("data-kind")).toBe("CAUTION");
    expect(box?.textContent).toBe("Deletes everything.");
    handle.destroy();
  });

  it("turning a paragraph into a callout writes GitHub's marker", async () => {
    const root = document.createElement("div");
    const { createVisualEditor } = await import("./milkdown");
    const { setCalloutCommand } = await import("./extensions");
    const handle = await createVisualEditor({ root, markdown: "Back up first.\n" });
    handle.run(setCalloutCommand, "WARNING");
    expect(handle.markdown().trim()).toBe("> [!WARNING]\n> Back up first.");
    handle.run(setCalloutCommand, "TIP");
    expect(handle.markdown().trim()).toBe("> [!TIP]\n> Back up first.");
    handle.destroy();
  });

  it("variables and snippets are shown as chips and written as they were", async () => {
    const root = document.createElement("div");
    const { createVisualEditor } = await import("./milkdown");
    const markdown = "Port {{port}} here.\n\n<!-- snippet: prerequisites -->\n";
    const handle = await createVisualEditor({ root, markdown });
    expect(root.querySelector(".visual-chip-variable")?.textContent).toBe("{{port}}");
    expect(root.querySelector(".visual-chip-snippet")?.textContent).toContain("prerequisites");
    expect(handle.markdown()).toBe(markdown);
    handle.destroy();
  });

  it("inserting a variable puts {{name}} at the cursor", async () => {
    const root = document.createElement("div");
    const { createVisualEditor } = await import("./milkdown");
    const handle = await createVisualEditor({ root, markdown: "Port: \n" });
    handle.insertMarkdown("{{port}}", true);
    expect(handle.markdown()).toContain("{{port}}");
    handle.destroy();
  });
});

describe("tabs in the visual editor", () => {
  const TABS = "<!-- tabs -->\n#### macOS\n\n```bash\nbrew install x\n```\n\n#### Linux\n\n```bash\napt install x\n```\n<!-- /tabs -->\n";

  it("a tab group becomes tabs, and is written back as it was", async () => {
    const root = document.createElement("div");
    const { createVisualEditor } = await import("./milkdown");
    const handle = await createVisualEditor({ root, markdown: TABS });
    const titles = [...root.querySelectorAll(".visual-tab")].map((b) => b.textContent);
    expect(titles).toEqual(["macOS", "Linux"]);
    expect(sameDocument(TABS, handle.markdown())).toBe(true);
    handle.destroy();
  });

  it("a group the site would not accept is left exactly as written", async () => {
    const broken = "<!-- tabs -->\nNo heading first.\n<!-- /tabs -->\n";
    const out = await survives(broken);
    expect(out).toContain("<!-- tabs -->");
  });

  it("inserting tabs writes a group the site renders as tabs", async () => {
    const root = document.createElement("div");
    const { createVisualEditor } = await import("./milkdown");
    const { insertTabsCommand } = await import("./extensions");
    const handle = await createVisualEditor({ root, markdown: "Intro.\n" });
    handle.run(insertTabsCommand, ["Windows", "Linux"]);
    const out = handle.markdown();
    expect(out).toMatch(/<!-- tabs -->\n+#### Windows\n[\s\S]*#### Linux[\s\S]*<!-- \/tabs -->/);
    handle.destroy();
  });
});
