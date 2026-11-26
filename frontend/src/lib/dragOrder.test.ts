import { describe, expect, it } from "vitest";
import { reorder } from "./dragOrder";

describe("reorder", () => {
  it("puts an item before or after another", () => {
    expect(reorder(["a", "b", "c", "d"], "d", "b", false)).toEqual(["a", "d", "b", "c"]);
    expect(reorder(["a", "b", "c", "d"], "a", "c", true)).toEqual(["b", "c", "a", "d"]);
  });
  it("leaves the list alone for itself or a stranger", () => {
    const list = ["a", "b"];
    expect(reorder(list, "a", "a", true)).toBe(list);
    expect(reorder(list, "x", "a", true)).toBe(list);
  });
});
