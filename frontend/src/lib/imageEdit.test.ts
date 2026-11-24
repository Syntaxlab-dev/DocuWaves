import { describe, expect, it } from "vitest";
import { blockSize, cropOf, editable, editedName, normalize, strokeWidth } from "./imageEdit";

describe("normalize", () => {
  it("accepts a drag in any direction and clamps to the image", () => {
    expect(normalize({ x: 50, y: 40 }, { x: 10, y: 5 }, 100, 100)).toEqual({ x: 10, y: 5, w: 40, h: 35 });
    expect(normalize({ x: -20, y: 90 }, { x: 30, y: 140 }, 100, 100)).toEqual({ x: 0, y: 90, w: 30, h: 10 });
  });
});

describe("cropOf", () => {
  it("is the whole image without a crop, and the last real crop otherwise", () => {
    expect(cropOf([], 800, 600)).toEqual({ x: 0, y: 0, w: 800, h: 600 });
    const ops = [
      { kind: "crop" as const, rect: { x: 0, y: 0, w: 100, h: 100 } },
      { kind: "blur" as const, rect: { x: 1, y: 1, w: 5, h: 5 } },
      { kind: "crop" as const, rect: { x: 10, y: 20, w: 300, h: 200 } },
      { kind: "crop" as const, rect: { x: 0, y: 0, w: 2, h: 2 } }, // a stray click, ignored
    ];
    expect(cropOf(ops, 800, 600)).toEqual({ x: 10, y: 20, w: 300, h: 200 });
  });
});

describe("sizes", () => {
  it("scales marks with the image", () => {
    expect(strokeWidth(400, 300)).toBe(3);
    expect(strokeWidth(3840, 2160)).toBe(12);
  });
  it("pixelates in blocks coarse enough to hide a line of text", () => {
    expect(blockSize({ x: 0, y: 0, w: 300, h: 20 })).toBeGreaterThanOrEqual(6);
    expect(blockSize({ x: 0, y: 0, w: 400, h: 120 })).toBe(20);
  });
});

describe("names and types", () => {
  it("marks an edited copy, keeping a JPEG's extension", () => {
    expect(editedName("screenshot-2026-11-24.png", "image/png")).toBe("screenshot-2026-11-24-edited.png");
    expect(editedName("photo.JPG", "image/jpeg")).toBe("photo-edited.jpg");
    expect(editedName("pic.webp", "image/webp")).toBe("pic-edited.png");
    expect(editedName("shot-edited.png", "image/png")).toBe("shot-edited.png");
  });
  it("edits bitmaps only", () => {
    expect(editable("image/png")).toBe(true);
    expect(editable("", "a.jpeg")).toBe(true);
    expect(editable("image/svg+xml", "a.svg")).toBe(false);
    expect(editable("image/gif", "a.gif")).toBe(false);
  });
});
