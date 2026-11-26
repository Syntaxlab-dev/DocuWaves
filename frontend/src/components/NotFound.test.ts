import { describe, expect, it } from "vitest";
import { wordsFromPath } from "./NotFound";

describe("wordsFromPath", () => {
  it("reads the last segment as words", () => {
    expect(wordsFromPath("/p/handbook/pages/instaling-the-widget")).toBe("instaling the widget");
    expect(wordsFromPath("/de/p/x/pages/strom_anschluss/")).toBe("strom anschluss");
    expect(wordsFromPath("/old/setup.html")).toBe("setup");
    expect(wordsFromPath("/")).toBe("");
  });
});
