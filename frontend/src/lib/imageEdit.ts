/**
 * What the screenshot editor (components/ImageEditor.tsx) does to an image,
 * as a list of operations replayed onto a canvas: the dialog draws them for
 * the author, and the same function draws them once more, without any of
 * the editing furniture, into the file that is uploaded.
 *
 * Coordinates are in the image's own pixels, never in screen pixels, so the
 * result does not depend on how large the dialog happened to be.
 *
 * "blur" is pixelation, and it is applied to the pixels drawn so far: the
 * uploaded file holds only the coarse blocks, never the original text under
 * them. A real Gaussian blur of a few pixels can be partly undone, and that
 * is exactly what someone hiding an e-mail address or a token must not rely
 * on.
 */

export type Tool = "crop" | "rect" | "arrow" | "blur";

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type Operation =
  | { kind: "crop"; rect: Rect }
  | { kind: "rect"; rect: Rect; color: string }
  | { kind: "blur"; rect: Rect }
  | { kind: "arrow"; from: { x: number; y: number }; to: { x: number; y: number }; color: string };

export const COLORS = ["#e11d48", "#f59e0b", "#16a34a", "#2563eb", "#111827"];

/** A rectangle from two corners, any drag direction, clamped to the image. */
export function normalize(a: { x: number; y: number }, b: { x: number; y: number }, width: number, height: number): Rect {
  const x1 = Math.max(0, Math.min(a.x, b.x));
  const y1 = Math.max(0, Math.min(a.y, b.y));
  const x2 = Math.min(width, Math.max(a.x, b.x));
  const y2 = Math.min(height, Math.max(a.y, b.y));
  return { x: Math.round(x1), y: Math.round(y1), w: Math.round(Math.max(0, x2 - x1)), h: Math.round(Math.max(0, y2 - y1)) };
}

/** The last crop wins; without one, the whole image. */
export function cropOf(ops: Operation[], width: number, height: number): Rect {
  for (let i = ops.length - 1; i >= 0; i--) {
    const op = ops[i];
    if (op.kind === "crop" && op.rect.w >= 4 && op.rect.h >= 4) return op.rect;
  }
  return { x: 0, y: 0, w: width, h: height };
}

/** Line width and pixel block size, relative to the image so a 4K
 *  screenshot gets marks as visible as a small one's. */
export function strokeWidth(width: number, height: number): number {
  return Math.max(3, Math.round(Math.max(width, height) / 320));
}

export function blockSize(rect: Rect): number {
  return Math.max(6, Math.round(Math.min(rect.w, rect.h) / 6), Math.round(Math.max(rect.w, rect.h) / 40));
}

function pixelate(ctx: CanvasRenderingContext2D, rect: Rect) {
  if (rect.w < 1 || rect.h < 1) return;
  const block = blockSize(rect);
  const small = document.createElement("canvas");
  small.width = Math.max(1, Math.ceil(rect.w / block));
  small.height = Math.max(1, Math.ceil(rect.h / block));
  const sctx = small.getContext("2d")!;
  sctx.imageSmoothingEnabled = true;
  sctx.drawImage(ctx.canvas, rect.x, rect.y, rect.w, rect.h, 0, 0, small.width, small.height);
  ctx.save();
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(small, 0, 0, small.width, small.height, rect.x, rect.y, rect.w, rect.h);
  ctx.restore();
}

function arrow(ctx: CanvasRenderingContext2D, from: { x: number; y: number }, to: { x: number; y: number }, color: string, line: number) {
  const angle = Math.atan2(to.y - from.y, to.x - from.x);
  const head = line * 4.5;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = line;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.lineTo(to.x - Math.cos(angle) * head * 0.8, to.y - Math.sin(angle) * head * 0.8);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(to.x, to.y);
  ctx.lineTo(to.x - head * Math.cos(angle - Math.PI / 7), to.y - head * Math.sin(angle - Math.PI / 7));
  ctx.lineTo(to.x - head * Math.cos(angle + Math.PI / 7), to.y - head * Math.sin(angle + Math.PI / 7));
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

/** The image with every mark and blur drawn on, uncropped. */
export function paint(ctx: CanvasRenderingContext2D, image: CanvasImageSource, width: number, height: number, ops: Operation[]) {
  ctx.clearRect(0, 0, width, height);
  ctx.drawImage(image, 0, 0, width, height);
  const line = strokeWidth(width, height);
  for (const op of ops) {
    if (op.kind === "blur") pixelate(ctx, op.rect);
    else if (op.kind === "rect") {
      ctx.save();
      ctx.strokeStyle = op.color;
      ctx.lineWidth = line;
      ctx.lineJoin = "round";
      ctx.strokeRect(op.rect.x + line / 2, op.rect.y + line / 2, Math.max(0, op.rect.w - line), Math.max(0, op.rect.h - line));
      ctx.restore();
    } else if (op.kind === "arrow") arrow(ctx, op.from, op.to, op.color, line);
  }
}

/** The finished file: painted, then cropped. PNG, except that a JPEG stays a
 *  JPEG (a photo as PNG is several times the size for nothing). */
export function render(image: CanvasImageSource, width: number, height: number, ops: Operation[], type: string): Promise<Blob> {
  const full = document.createElement("canvas");
  full.width = width;
  full.height = height;
  paint(full.getContext("2d")!, image, width, height, ops);
  const crop = cropOf(ops, width, height);
  const out = document.createElement("canvas");
  out.width = crop.w;
  out.height = crop.h;
  out.getContext("2d")!.drawImage(full, crop.x, crop.y, crop.w, crop.h, 0, 0, crop.w, crop.h);
  const outType = type === "image/jpeg" ? "image/jpeg" : "image/png";
  return new Promise((resolve, reject) =>
    out.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("The image could not be encoded."))), outType, 0.92),
  );
}

/** "shot.png" -> "shot-edited.png" (".jpg" kept for a JPEG). */
export function editedName(name: string, type: string): string {
  const stem = name.replace(/\.[^.]+$/, "") || "image";
  const ext = type === "image/jpeg" ? (/\.jpe?g$/i.exec(name)?.[0].toLowerCase() ?? ".jpg") : ".png";
  return `${stem.replace(/-edited$/, "")}-edited${ext}`;
}

/** Only bitmaps a canvas can re-encode without losing anything that matters:
 *  not an SVG (it would turn into a bitmap) and not a GIF (animation). */
export function editable(type: string, name = ""): boolean {
  return /^image\/(png|jpeg|webp)$/.test(type) || /\.(png|jpe?g|webp)$/i.test(name);
}
