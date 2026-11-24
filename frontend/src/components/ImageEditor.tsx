import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { ArrowUpRight, Crop, EyeOff, Square, Undo2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { COLORS, cropOf, editedName, normalize, paint, render, type Operation, type Tool } from "@/lib/imageEdit";

/**
 * Crop, mark up and blur a screenshot before it goes into a page.
 *
 * Opened by the page editor for a single pasted or dropped image, and from
 * the images panel for one already uploaded. "Insert" hands back the file to
 * upload: the original, untouched, when nothing was changed (so pressing
 * Enter right away is the same as pasting was before), otherwise a new PNG
 * (or JPEG for a JPEG) named "<name>-edited". Cancel hands back null.
 *
 * Everything happens in the browser on a canvas; the image never goes
 * anywhere but the ordinary upload afterwards.
 */
export function ImageEditor({
  file,
  onDone,
  confirmLabel,
}: {
  file: File;
  onDone: (result: File | null) => void;
  confirmLabel?: string;
}) {
  const { t } = useI18n();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [failed, setFailed] = useState(false);
  const [ops, setOps] = useState<Operation[]>([]);
  const [draft, setDraft] = useState<Operation | null>(null);
  const [tool, setTool] = useState<Tool>("rect");
  const [color, setColor] = useState(COLORS[0]);
  const [busy, setBusy] = useState(false);
  const start = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => setImage(img);
    img.onerror = () => setFailed(true);
    img.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const width = image?.naturalWidth ?? 0;
  const height = image?.naturalHeight ?? 0;

  // Redraw: the marks, plus (on screen only) a dimmed outside of the crop.
  useEffect(() => {
    const el = canvas.current;
    if (!el || !image) return;
    el.width = width;
    el.height = height;
    const ctx = el.getContext("2d")!;
    const all = draft ? [...ops, draft] : ops;
    paint(ctx, image, width, height, all.filter((op) => op.kind !== "crop"));
    const crop = cropOf(all, width, height);
    if (crop.w !== width || crop.h !== height) {
      ctx.save();
      ctx.fillStyle = "rgb(0 0 0 / 0.55)";
      ctx.beginPath();
      ctx.rect(0, 0, width, height);
      ctx.rect(crop.x, crop.y, crop.w, crop.h);
      ctx.fill("evenodd");
      ctx.setLineDash([10, 6]);
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = Math.max(2, width / 600);
      ctx.strokeRect(crop.x, crop.y, crop.w, crop.h);
      ctx.restore();
    }
  }, [image, ops, draft, width, height]);

  // Keys: Enter inserts, Escape cancels, Ctrl/Cmd+Z undoes.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onDone(null);
      } else if (e.key === "Enter" && !busy) {
        e.preventDefault();
        void finish();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        setOps((list) => list.slice(0, -1));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function point(e: ReactPointerEvent<HTMLCanvasElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(width, ((e.clientX - box.left) / box.width) * width)),
      y: Math.max(0, Math.min(height, ((e.clientY - box.top) / box.height) * height)),
    };
  }

  function operation(a: { x: number; y: number }, b: { x: number; y: number }): Operation {
    if (tool === "arrow") return { kind: "arrow", from: a, to: b, color };
    const rect = normalize(a, b, width, height);
    if (tool === "crop") return { kind: "crop", rect };
    if (tool === "blur") return { kind: "blur", rect };
    return { kind: "rect", rect, color };
  }

  function onPointerDown(e: ReactPointerEvent<HTMLCanvasElement>) {
    if (!image) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    start.current = point(e);
  }

  function onPointerMove(e: ReactPointerEvent<HTMLCanvasElement>) {
    if (!start.current) return;
    setDraft(operation(start.current, point(e)));
  }

  function onPointerUp(e: ReactPointerEvent<HTMLCanvasElement>) {
    if (!start.current) return;
    const op = operation(start.current, point(e));
    start.current = null;
    setDraft(null);
    // A click without a drag adds nothing.
    const size = op.kind === "arrow" ? Math.hypot(op.to.x - op.from.x, op.to.y - op.from.y) : op.rect.w * op.rect.h;
    if (size < (op.kind === "arrow" ? 8 : 64)) return;
    setOps((list) => [...list, op]);
  }

  async function finish() {
    if (!image) return;
    if (ops.length === 0) return onDone(file);
    setBusy(true);
    try {
      const blob = await render(image, width, height, ops, file.type);
      onDone(new File([blob], editedName(file.name, file.type), { type: blob.type }));
    } catch {
      setFailed(true);
      setBusy(false);
    }
  }

  const tools: { id: Tool; icon: typeof Crop; label: string }[] = [
    { id: "rect", icon: Square, label: t("imageEditor.rect") },
    { id: "arrow", icon: ArrowUpRight, label: t("imageEditor.arrow") },
    { id: "blur", icon: EyeOff, label: t("imageEditor.blur") },
    { id: "crop", icon: Crop, label: t("imageEditor.crop") },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-[2px]"
      onMouseDown={(e) => e.target === e.currentTarget && onDone(null)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("imageEditor.title")}
        className="flex max-h-full w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl"
      >
        <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] p-2">
          <span className="px-1 text-sm font-medium">{t("imageEditor.title")}</span>
          <div role="radiogroup" aria-label={t("imageEditor.tools")} className="flex gap-1">
            {tools.map(({ id, icon: Icon, label }) => (
              <button
                key={id}
                type="button"
                role="radio"
                aria-checked={tool === id}
                title={label}
                onClick={() => setTool(id)}
                className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs ${
                  tool === id ? "bg-[var(--accent)] text-white" : "hover:bg-[var(--surface-2)]"
                }`}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                {label}
              </button>
            ))}
          </div>
          {(tool === "rect" || tool === "arrow") && (
            <div role="radiogroup" aria-label={t("imageEditor.color")} className="flex gap-1">
              {COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  role="radio"
                  aria-checked={color === c}
                  aria-label={c}
                  onClick={() => setColor(c)}
                  className={`h-5 w-5 rounded-full border-2 ${color === c ? "border-[var(--ink)]" : "border-transparent"}`}
                  style={{ background: c }}
                />
              ))}
            </div>
          )}
          <Button variant="ghost" size="sm" disabled={!ops.length} onClick={() => setOps((list) => list.slice(0, -1))}>
            <Undo2 className="h-3.5 w-3.5" />
            {t("imageEditor.undo")}
          </Button>
          <button type="button" aria-label={t("imageEditor.cancel")} className="ml-auto rounded p-1 hover:bg-[var(--surface-2)]" onClick={() => onDone(null)}>
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto bg-[var(--surface-2)] p-3">
          {failed ? (
            <p className="text-sm text-[var(--muted)]">{t("imageEditor.failed")}</p>
          ) : (
            <canvas
              ref={canvas}
              aria-label={t("imageEditor.canvas")}
              className="mx-auto block max-h-[65vh] max-w-full cursor-crosshair touch-none select-none object-contain"
              style={{ aspectRatio: width && height ? `${width} / ${height}` : undefined }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
            />
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-[var(--border)] p-2">
          <span className="text-xs text-[var(--muted)]">
            {image ? `${cropOf(ops, width, height).w} × ${cropOf(ops, width, height).h} px · ` : ""}
            {t("imageEditor.hint")}
          </span>
          <Button variant="outline" size="sm" className="ml-auto" onClick={() => onDone(null)}>
            {t("imageEditor.cancel")}
          </Button>
          <Button size="sm" disabled={!image || busy} onClick={() => void finish()}>
            {ops.length ? confirmLabel ?? t("imageEditor.insertEdited") : confirmLabel ?? t("imageEditor.insert")}
          </Button>
        </div>
      </div>
    </div>
  );
}
