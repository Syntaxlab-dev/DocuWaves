import { describe, expect, it } from "vitest";
import { categoryTree, parentChoices, siblingsOf } from "./categoryTree";

const cats = [
  { slug: "guide", parent: "" },
  { slug: "reference", parent: "" },
  { slug: "linux", parent: "install" },
  { slug: "install", parent: "guide" },
  { slug: "deep", parent: "linux" },
  { slug: "stray", parent: "gone" },
];

describe("categoryTree", () => {
  it("lists each category followed by its branch", () => {
    expect(categoryTree(cats).map((e) => `${e.category.slug}:${e.depth}`)).toEqual([
      "guide:0", "install:1", "linux:2", "deep:3", "reference:0", "stray:0",
    ]);
  });

  it("never drops a category in a loop", () => {
    const loop = [{ slug: "a", parent: "b" }, { slug: "b", parent: "a" }];
    expect(categoryTree(loop).map((e) => e.category.slug).sort()).toEqual(["a", "b"]);
  });
});

describe("parentChoices", () => {
  it("leaves out the category's own branch", () => {
    const slugs = parentChoices(cats, "install").map((e) => e.category.slug);
    expect(slugs).not.toContain("install");
    expect(slugs).not.toContain("linux");
    expect(slugs).not.toContain("deep");
  });

  it("leaves out parents that would nest too deep", () => {
    // A new category under `deep` would be a fifth level.
    expect(parentChoices(cats, null).map((e) => e.category.slug)).not.toContain("deep");
    expect(parentChoices(cats, null).map((e) => e.category.slug)).toContain("linux");
    // `install` carries two levels below it: only top-level parents fit.
    expect(parentChoices(cats, "install").map((e) => e.category.slug)).toEqual(["guide", "reference", "stray"]);
  });
});

describe("siblingsOf", () => {
  it("is the categories with the same parent", () => {
    expect(siblingsOf(cats, cats[0]).map((c) => c.slug)).toEqual(["guide", "reference"]);
  });
});
