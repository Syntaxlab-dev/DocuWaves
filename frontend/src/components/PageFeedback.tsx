import { useEffect, useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/**
 * "Was this page helpful?" -- two buttons, once per page.
 *
 * Deliberately not a public comment box: that would be a moderation queue.
 * After the thumb, the reader may add a note that only editors read (under
 * Insights) -- the one thing a count cannot say is WHY. It is optional and
 * can be skipped; the vote has already counted by then.
 *
 * The "already answered" mark is per browser, in localStorage, and is a
 * courtesy rather than a control: it stops the buttons re-offering
 * themselves on a page someone just answered. The real limit is on the
 * server. Every read and write is guarded -- a browser blocking site data
 * throws on the property access itself, and losing a preference must never
 * cost the reader the page.
 */
const STORAGE_PREFIX = "docuwaves-feedback:";

function alreadyAnswered(key: string): boolean {
  try {
    return window.localStorage.getItem(STORAGE_PREFIX + key) !== null;
  } catch {
    return false;
  }
}

function remember(key: string) {
  try {
    window.localStorage.setItem(STORAGE_PREFIX + key, "1");
  } catch {
    // Not remembered; the vote still counted.
  }
}

export function PageFeedback({
  project,
  page,
  language,
  version,
}: {
  project: string;
  page: string;
  language?: string;
  version?: string;
}) {
  const { t } = useI18n();
  const key = `${project}/${version || ""}/${page}/${language || ""}`;
  const [state, setState] = useState<"asking" | "sending" | "note" | "done">("asking");
  const [ticket, setTicket] = useState<{ id: number; key: string; helpful: boolean } | null>(null);
  const [note, setNote] = useState("");

  // Re-checked per page rather than once on mount: the reader navigates
  // between pages without this component unmounting.
  useEffect(() => {
    setState(alreadyAnswered(key) ? "done" : "asking");
    setTicket(null);
  }, [key]);

  async function vote(helpful: boolean) {
    setState("sending");
    let next: "note" | "done" = "done";
    try {
      const answer = await api.publicFeedback({ project, page, helpful, language, version });
      if (answer.id !== undefined && answer.key) {
        setTicket({ id: answer.id, key: answer.key, helpful });
        setNote("");
        next = "note";
      }
    } catch {
      // Swallowed on purpose. The reader was doing us a favour; an error
      // banner would make them feel they had broken something, and there is
      // nothing for them to do about it either way.
    }
    remember(key);
    setState(next);
  }

  async function sendNote() {
    if (!ticket || !note.trim()) {
      setState("done");
      return;
    }
    setState("sending");
    try {
      await api.publicFeedbackComment({ id: ticket.id, key: ticket.key, comment: note });
    } catch {
      // As above: nothing the reader could do about it.
    }
    setState("done");
  }

  return (
    <div className="page-feedback mt-10 border-t border-[var(--border)] pt-4 text-sm">
      {state === "done" ? (
        <p className="text-[var(--muted)]">{t("feedback.thanks")}</p>
      ) : ticket && (state === "note" || (state === "sending" && note)) ? (
        <form
          className="flex max-w-xl flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void sendNote();
          }}
        >
          <label htmlFor="page-feedback-note" className="text-[var(--muted)]">
            {t(ticket.helpful ? "feedback.noteYes" : "feedback.noteNo")}
          </label>
          <textarea
            id="page-feedback-note"
            value={note}
            maxLength={1000}
            rows={3}
            onChange={(event) => setNote(event.target.value)}
            className="w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm"
          />
          <p className="text-xs text-[var(--muted)]">{t("feedback.notePrivacy")}</p>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={state === "sending" || !note.trim()}
              className="rounded-lg border border-[var(--border)] px-3 py-1.5 hover:bg-[var(--surface-2)] disabled:opacity-50"
            >
              {t("feedback.send")}
            </button>
            <button
              type="button"
              disabled={state === "sending"}
              onClick={() => setState("done")}
              className="rounded-lg px-3 py-1.5 text-[var(--muted)] hover:bg-[var(--surface-2)] disabled:opacity-50"
            >
              {t("feedback.skip")}
            </button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[var(--muted)]">{t("feedback.question")}</span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={state === "sending"}
              onClick={() => vote(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 hover:bg-[var(--surface-2)] disabled:opacity-50"
            >
              <ThumbsUp className="h-3.5 w-3.5" aria-hidden="true" />
              {t("feedback.yes")}
            </button>
            <button
              type="button"
              disabled={state === "sending"}
              onClick={() => vote(false)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 hover:bg-[var(--surface-2)] disabled:opacity-50"
            >
              <ThumbsDown className="h-3.5 w-3.5" aria-hidden="true" />
              {t("feedback.no")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
