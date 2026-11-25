import { describe, expect, it } from "vitest";
import { contentPath, parseContentPath } from "./contentPath";

describe("contentPath", () => {
  it("grows with the selection", () => {
    expect(contentPath()).toBe("/admin/content");
    expect(contentPath("docs")).toBe("/admin/content/docs");
    expect(contentPath("docs", "guide")).toBe("/admin/content/docs/guide");
    expect(contentPath("docs", "guide", { kind: "page", slug: "start", language: "de" })).toBe(
      "/admin/content/docs/guide?page=start&lang=de",
    );
  });
  it("leaves a new page out", () => {
    expect(contentPath("docs", "guide", { kind: "new" })).toBe("/admin/content/docs/guide");
  });
});

describe("parseContentPath", () => {
  it("reads back what contentPath wrote", () => {
    expect(parseContentPath("/admin/content/docs/guide", "?page=start&lang=de")).toEqual({
      project: "docs",
      category: "guide",
      page: "start",
      lang: "de",
    });
  });
  it("is null without a project", () => {
    expect(parseContentPath("/admin/content", "")).toBeNull();
    expect(parseContentPath("/admin/content/", "")).toBeNull();
  });
  it("ignores a page without a category", () => {
    expect(parseContentPath("/admin/content/docs", "?page=x")?.page).toBe("");
  });
});
