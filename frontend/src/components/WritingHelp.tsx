/** Writing help in the Markdown editor (backend services/writing_help.py):
 *  rephrase, shorten, simplify, correct or summarise the SELECTED text with
 *  the documentation chat's model. The suggestion is shown next to the
 *  original; only "Use it" puts it into the text, and only saving the page
 *  writes anything. Shown only when an operator configured a model. */
import { useState } from "react";
import { Sparkles, X } from "lucide-react";
import { api, ApiError, type WritingAction } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";

const ACTIONS: WritingAction[] = ["rephrase", "shorten", "simplify", "fix", "summarize"];

export type Selection = { from: number; to: number; text: string };

export function WritingHelp({
  getSelection,
  onApply,
  projectSlug,
  language,
}: {
  getSelection: () => Selection;
  onApply: (selection: Selection, text: string) => void;
  projectSlug: string;
  language: string;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<WritingAction | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ selection: Selection; text: string } | null>(null);

  async function run(action: WritingAction) {
    const selection = getSelection();
    setResult(null);
    if (!selection.text.trim()) {
      setError(t("writing.selectFirst"));
      return;
    }
    setError("");
    setBusy(action);
    try {
      const { text } = await api.adminWritingHelp(selection.text, action, projectSlug, language);
      setResult({ selection, text });
    } catch (err) {
      const code = err instanceof ApiError ? err.message : "";
      setError(
        code === "too_long"
          ? t("writing.tooLong")
          : code === "not_configured"
            ? t("writing.noModel")
            : t("writing.failed"),
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mb-2">
      <Button type="button" variant="outline" size="sm" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
        {t("writing.button")}
      </Button>
      {open && (
        <div className="mt-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3 text-sm">
          <div className="flex items-start gap-2">
            <p className="text-xs text-[var(--muted)]">{t("writing.hint")}</p>
            <button
              type="button"
              aria-label={t("writing.close")}
              className="ml-auto text-[var(--muted)] hover:text-[var(--ink)]"
              onClick={() => {
                setOpen(false);
                setResult(null);
                setError("");
              }}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {ACTIONS.map((action) => (
              <button
                key={action}
                type="button"
                disabled={busy !== null}
                // Keeps the textarea's selection: a click that took the
                // focus first would leave nothing selected to work on.
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => void run(action)}
                className="rounded-full border border-[var(--border)] px-2.5 py-1 text-xs hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:opacity-50"
              >
                {busy === action ? t("writing.working") : t(`writing.action.${action}` as never)}
              </button>
            ))}
          </div>
          {error && (
            <p role="alert" className="mt-2 text-xs text-[var(--danger,#dc2626)]">
              {error}
            </p>
          )}
          {result && (
            <div className="mt-3">
              <div className="text-xs font-medium">{t("writing.suggestion")}</div>
              <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded-md border border-[var(--border)] bg-[var(--surface)] p-2 font-mono text-xs">
                {result.text}
              </pre>
              <div className="mt-2 flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={() => {
                    onApply(result.selection, result.text);
                    setResult(null);
                  }}
                >
                  {t("writing.apply")}
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={() => setResult(null)}>
                  {t("writing.discard")}
                </Button>
              </div>
              <p className="mt-1.5 text-xs text-[var(--muted)]">{t("writing.checkIt")}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
