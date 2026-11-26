import { describe, expect, it } from "vitest";
import { parseCodeMeta } from "@/components/MarkdownView";

describe("parseCodeMeta", () => {
  it("reads title, marked lines and line numbers in any order", () => {
    const m = parseCodeMeta('showLineNumbers {2,5-6} title="app/settings.py"');
    expect(m.title).toBe("app/settings.py");
    expect(m.lineNumbers).toBe(true);
    expect([...m.marked]).toEqual([2, 5, 6]);
  });
  it("ignores braces inside the title and anything it doesn't know", () => {
    const m = parseCodeMeta('title="a{1}.txt" linenos=false');
    expect(m.title).toBe("a{1}.txt");
    expect(m.marked.size).toBe(0);
    expect(m.lineNumbers).toBe(false);
  });
  it("is empty for an empty meta string", () => {
    expect(parseCodeMeta("")).toEqual({ title: "", lineNumbers: false, marked: new Set() });
  });
});

import { internalPage } from "@/components/LinkPreview";

describe("internalPage", () => {
  it("finds the project and page of a docs link", () => {
    expect(internalPage("/p/docuwaves/pages/docs-as-code")).toEqual({ project: "docuwaves", page: "docs-as-code" });
    expect(internalPage("/de/p/hb/v/1-0/pages/setup#install")).toEqual({ project: "hb", page: "setup" });
  });
  it("leaves everything else alone", () => {
    expect(internalPage("https://example.com/p/x/pages/y")).toBeNull();
    expect(internalPage("/p/docuwaves/c/guides")).toBeNull();
    expect(internalPage(undefined)).toBeNull();
  });
});
