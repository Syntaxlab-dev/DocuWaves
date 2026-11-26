import { describe, expect, it } from "vitest";
import { contrastRatio, readableAccent } from "./theme";

describe("readableAccent", () => {
  it("lightens a dark accent for the dark scheme until text in it is readable", () => {
    const dark = ["#0d1017", "#151920", "#1c212a"];
    const shade = readableAccent("#0e7490", dark);
    expect(shade).not.toBe("#0e7490");
    for (const surface of dark) expect(contrastRatio(shade, surface)).toBeGreaterThanOrEqual(4.5);
  });
  it("leaves an accent that already reads alone", () => {
    expect(readableAccent("#0e7490", ["#ffffff"])).toBe("#0e7490");
  });
  it("darkens a pale accent on light surfaces", () => {
    const shade = readableAccent("#ffd43b", ["#ffffff", "#f6f7f9"]);
    expect(contrastRatio(shade, "#ffffff")).toBeGreaterThanOrEqual(4.5);
  });
});
