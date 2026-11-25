import { describe, expect, it } from "vitest";
import { relativeTime } from "./time";

describe("relativeTime", () => {
  const now = Date.parse("2026-11-25T12:00:00Z");
  it("picks the largest whole unit", () => {
    expect(relativeTime("2026-11-23T12:00:00Z", "en", now)).toBe("2 days ago");
    expect(relativeTime("2026-11-25T11:00:00Z", "de", now)).toBe("vor 1 Stunde");
  });
  it("says now for seconds and nothing for junk", () => {
    expect(relativeTime("2026-11-25T11:59:50Z", "en", now)).toBe("this minute");
    expect(relativeTime("kaputt", "en", now)).toBe("");
  });
});
