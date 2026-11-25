// An in-app replacement for window.confirm(): same promise-shaped "are you
// sure?", but styled like the rest of the admin, with a clear title, a red
// button for what cannot be taken back, Escape to cancel and the focus on
// the safe choice. askConfirm() works from anywhere (no hook needed), and
// <ConfirmHost /> in App.tsx renders whichever question is open.
import { useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";

export interface ConfirmOptions {
  /** The question itself, short: "Delete this page?" */
  title: string;
  /** What happens, in a sentence. Optional. */
  message?: string;
  /** The label of the confirming button; "OK" when left out. */
  confirmLabel?: string;
  /** Red button and a warning icon: deleting, revoking, discarding. */
  danger?: boolean;
}

interface Pending extends ConfirmOptions {
  resolve: (ok: boolean) => void;
}

let show: ((pending: Pending) => void) | null = null;

/** Asks, resolves true on confirm and false on cancel, Escape or a click
 *  outside. Without a mounted host (a unit test) it falls back to the
 *  browser's own confirm(), so no question is ever silently answered. */
export function askConfirm(options: ConfirmOptions): Promise<boolean> {
  if (!show) {
    const text = options.message ? `${options.title}\n\n${options.message}` : options.title;
    return Promise.resolve(window.confirm(text));
  }
  const open = show;
  return new Promise((resolve) => open({ ...options, resolve }));
}

export function ConfirmHost() {
  const { t } = useI18n();
  const [pending, setPending] = useState<Pending | null>(null);
  const safeButton = useRef<HTMLButtonElement>(null);
  const confirmButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    show = (next) =>
      setPending((current) => {
        current?.resolve(false); // a second question replaces the first
        return next;
      });
    return () => {
      show = null;
    };
  }, []);

  useEffect(() => {
    if (!pending) return;
    const previous = document.activeElement as HTMLElement | null;
    (pending.danger ? safeButton : confirmButton).current?.focus();
    return () => previous?.focus?.();
  }, [pending]);

  if (!pending) return null;
  const close = (ok: boolean) => {
    pending.resolve(ok);
    setPending(null);
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && close(false)}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          close(false);
        }
      }}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby={pending.message ? "confirm-message" : undefined}
        className="w-full max-w-md rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-2xl"
      >
        <div className="flex gap-3">
          {pending.danger && (
            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-500/10 text-red-600">
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            </span>
          )}
          <div className="min-w-0">
            <h2 id="confirm-title" className="text-base font-semibold">
              {pending.title}
            </h2>
            {pending.message && (
              <p id="confirm-message" className="mt-1 whitespace-pre-line text-sm text-[var(--muted)]">
                {pending.message}
              </p>
            )}
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button ref={safeButton} variant="outline" onClick={() => close(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            ref={confirmButton}
            className={pending.danger ? "bg-red-600 text-white hover:bg-red-700" : undefined}
            onClick={() => close(true)}
          >
            {pending.confirmLabel ?? "OK"}
          </Button>
        </div>
      </div>
    </div>
  );
}
