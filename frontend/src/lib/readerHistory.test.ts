import { describe, expect, it } from "vitest";
import { withEntry, type ReadEntry } from "./readerHistory";
import { filterNav } from "@/components/DocsSidebar";

const e = (path: string, at = 0): ReadEntry => ({ path, title: path, context: "", at });

describe("withEntry", () => {
  it("puts the newest first, once, and caps the list", () => {
    const list = [e("/a"), e("/b"), e("/c")];
    expect(withEntry(list, e("/b", 9), 3).map((x) => x.path)).toEqual(["/b", "/a", "/c"]);
    expect(withEntry(list, e("/d"), 3).map((x) => x.path)).toEqual(["/d", "/a", "/b"]);
  });
});

describe("filterNav", () => {
  const cat = (slug: string, name: string, pages: [number, string][]) =>
    ({ slug, name, pages: pages.map(([id, title]) => ({ id, title })) }) as never;
  const categories = [cat("start", "Getting started", [[1, "Install"], [2, "First run"]]), cat("wiring", "Wiring", [[3, "Mains"]])];
  const ancestors = (slug: string) => (slug === "wiring" ? [{ slug: "start" }] : []);

  it("keeps matching pages and the sections around them", () => {
    const r = filterNav(categories, "mains", ancestors);
    expect([...r.pages]).toEqual([3]);
    expect([...r.sections].sort()).toEqual(["start", "wiring"]);
  });
  it("keeps a whole section whose name matches", () => {
    expect([...filterNav(categories, "getting", ancestors).pages]).toEqual([1, 2]);
  });
  it("finds nothing for nothing", () => {
    expect(filterNav(categories, "zzz", ancestors).sections.size).toBe(0);
  });
});
