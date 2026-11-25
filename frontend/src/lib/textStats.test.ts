import { describe, expect, it } from "vitest";
import { readingMinutes, wordCount } from "./textStats";

describe("wordCount", () => {
  it("counts the prose, not the markup", () => {
    expect(wordCount("# Über uns\n\nWir bauen **gute** Doku. [Mehr](https://example.com/a-b-c)")).toBe(7);
  });
  it("skips code blocks and images", () => {
    expect(wordCount("Vorher\n\n```js\nconst a = 1;\n```\n\n![Bild](img/x.png) nachher")).toBe(2);
  });
  it("is 0 for nothing", () => {
    expect(wordCount("")).toBe(0);
  });
});

describe("readingMinutes", () => {
  it("rounds, and never says 0", () => {
    expect(readingMinutes(0)).toBe(1);
    expect(readingMinutes(450)).toBe(2);
  });
});
