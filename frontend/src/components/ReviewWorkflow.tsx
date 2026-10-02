/** Approval before publishing, in the admin UI (backend
 *  services/page_review.py): the panel in the editor, the queue, and the
 *  small marks in the page list.
 *
 *  The server decides everything -- who may approve, what an approval does
 *  -- and refuses what it does not allow. This side only offers the buttons
 *  that make sense right now and says why the others are not there: an
 *  author looking for "Approve" on their own text should read that somebody
 *  else has to, not find a button that answers with an error. */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, ClipboardCheck, GitPullRequestArrow, MessageSquareWarning, X } from "lucide-react";
import { api, ApiError, type Page, type ReviewDiff, type ReviewQueueEntry, type ReviewState } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { formatIsoDate } from "@/lib/dates";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DiffView } from "@/components/DiffView";

type Translate = ReturnType<typeof useI18n>["t"];

/** The API's refusal codes, in words. */
function reviewError(err: unknown, t: Translate): string {
  if (!(err instanceof ApiError)) return t("common.error");
  const known: Record<string, Parameters<Translate>[0]> = {
    own_change: "review.errOwnChange",
    nothing_to_review: "review.errNothing",
    already_submitted: "review.errAlready",
    not_submitted: "review.errNotSubmitted",
    review_required: "review.errRequired",
  };
  return known[err.message] ? t(known[err.message]) : err.message;
}

function day(iso: string, lang: string): string {
  return iso ? formatIsoDate(iso.slice(0, 10), lang) : "";
}

/** Whoever wrote the text under review -- the one person who may not
 *  approve it. Mirrors page_review.approve on the server. */
export function writtenBy(review: ReviewState): string {
  return review.changed_by || review.submitted_by;
}

/**
 * The review workflow's panel in the page editor.
 *
 * `canWrite`: may change the text (submit, withdraw, discard). Approving and
 * asking for changes are offered regardless -- read-only accounts may
 * review. `dirty`: unsaved edits; every action works on the SAVED text, so
 * all of them wait for a save rather than quietly deciding on something
 * other than what is on screen.
 */
export function ReviewPanel({
  pageId,
  review,
  published,
  dirty,
  canWrite,
  onChanged,
}: {
  pageId: number;
  review: ReviewState;
  published: boolean;
  dirty: boolean;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const { t, lang } = useI18n();
  const { status: auth } = useAuth();
  const me = auth?.username ?? "";
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"none" | "submit" | "changes">("none");
  const [text, setText] = useState("");
  const [diff, setDiff] = useState<ReviewDiff | null>(null);
  const [showDiff, setShowDiff] = useState(false);

  // A different page, or the state moved on: close whatever was half open.
  useEffect(() => {
    setMode("none");
    setText("");
    setDiff(null);
    setShowDiff(false);
  }, [pageId, review.status, review.pending]);

  const submitted = review.status === "pending";
  const changesRequested = review.status === "changes_requested";
  const somethingToReview = review.pending || !published;
  if (!review.required && !review.status && !review.pending) return null;

  async function run(action: () => Promise<unknown>, success: Parameters<Translate>[0]) {
    setBusy(true);
    try {
      await action();
      toast.success(t(success));
      onChanged();
    } catch (err) {
      toast.error(reviewError(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function toggleDiff() {
    if (!showDiff && !diff) {
      try {
        setDiff(await api.adminReviewDiff(pageId));
      } catch (err) {
        toast.error(reviewError(err, t));
        return;
      }
    }
    setShowDiff((v) => !v);
  }

  const ownText = Boolean(me) && writtenBy(review) === me;
  const disabled = busy || dirty;

  let headline: string;
  if (submitted) {
    headline = t("review.submitted")
      .replace("{name}", review.submitted_by)
      .replace("{date}", day(review.submitted_at, lang));
  } else if (changesRequested) {
    headline = t("review.changesRequested").replace("{name}", review.decided_by);
  } else if (review.pending) {
    headline = t("review.proposalNotSubmitted");
  } else if (!published) {
    headline = t("review.draftNeedsApproval");
  } else {
    headline = t("review.liveRequired");
  }

  const tone = changesRequested
    ? "border-red-400/60 bg-red-500/10 text-red-700 dark:text-red-300"
    : submitted
      ? "border-sky-400/60 bg-sky-500/10 text-sky-800 dark:text-sky-300"
      : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--ink)]";

  return (
    <div className={`mt-2 rounded-lg border px-3 py-2 text-sm ${tone}`} role="status">
      <div className="flex items-start gap-2">
        {changesRequested ? (
          <MessageSquareWarning className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        ) : (
          <GitPullRequestArrow className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        )}
        <div className="min-w-0 flex-1">
          <p>{headline}</p>
          {review.pending && <p className="text-xs opacity-80">{t("review.readersSeeLive")}</p>}
          {submitted && review.note && <p className="mt-1 whitespace-pre-wrap text-xs italic">„{review.note}“</p>}
          {changesRequested && review.comment && (
            <p className="mt-1 whitespace-pre-wrap text-xs italic">„{review.comment}“</p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-2">
            {(submitted || review.pending) && (
              <Button size="sm" variant="outline" onClick={() => void toggleDiff()}>
                {showDiff ? t("review.hideChanges") : t("review.showChanges")}
              </Button>
            )}

            {submitted && (
              <>
                <Button
                  size="sm"
                  disabled={disabled || ownText}
                  title={ownText ? t("review.ownChangeHint") : undefined}
                  onClick={() => void run(() => api.adminReviewApprove(pageId), "review.approved")}
                >
                  <CheckCircle2 className="mr-1 h-4 w-4" />
                  {t("review.approve")}
                </Button>
                <Button size="sm" variant="outline" disabled={disabled} onClick={() => setMode("changes")}>
                  {t("review.requestChanges")}
                </Button>
              </>
            )}

            {canWrite && !submitted && somethingToReview && (
              <Button size="sm" disabled={disabled} onClick={() => setMode("submit")}>
                {changesRequested ? t("review.resubmit") : t("review.submit")}
              </Button>
            )}
            {canWrite && submitted && (
              <Button
                size="sm"
                variant="ghost"
                disabled={disabled}
                onClick={() => void run(() => api.adminReviewWithdraw(pageId), "review.withdrawn")}
              >
                {t("review.withdraw")}
              </Button>
            )}
            {canWrite && review.pending && (
              <Button
                size="sm"
                variant="ghost"
                disabled={disabled}
                onClick={() => {
                  if (confirm(t("review.discardConfirm"))) {
                    void run(() => api.adminReviewDiscard(pageId), "review.discarded");
                  }
                }}
              >
                {t("review.discard")}
              </Button>
            )}
          </div>

          {submitted && ownText && <p className="mt-1 text-xs opacity-80">{t("review.ownChangeHint")}</p>}
          {dirty && <p className="mt-1 text-xs opacity-80">{t("review.saveFirst")}</p>}

          {mode !== "none" && (
            <div className="mt-2 flex flex-col gap-2">
              <Textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={3}
                maxLength={2000}
                placeholder={mode === "submit" ? t("review.notePlaceholder") : t("review.commentPlaceholder")}
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  disabled={disabled}
                  onClick={() =>
                    void (mode === "submit"
                      ? run(() => api.adminReviewSubmit(pageId, text), "review.submittedToast")
                      : run(() => api.adminReviewRequestChanges(pageId, text), "review.changesRequestedToast"))
                  }
                >
                  {mode === "submit" ? t("review.submit") : t("review.sendBack")}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setMode("none")}>
                  {t("admin.cancel")}
                </Button>
              </div>
            </div>
          )}

          {showDiff && diff && (
            <div className="mt-2">
              {diff.live === null && <p className="mb-1 text-xs opacity-80">{t("review.newPage")}</p>}
              {diff.live && diff.live.title !== diff.proposed.title && (
                <p className="mb-1 text-xs">
                  {t("review.titleChange").replace("{from}", diff.live.title).replace("{to}", diff.proposed.title)}
                </p>
              )}
              {diff.diff ? <DiffView diff={diff.diff} /> : <p className="text-xs opacity-80">{t("review.noTextChange")}</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** A small mark for the page list: where this page stands, when it is
 *  anywhere at all. */
export function ReviewMark({ variants }: { variants: Page[] }) {
  const { t } = useI18n();
  let label: string | null = null;
  let tone = "text-[var(--muted)]";
  if (variants.some((v) => v.review_status === "pending")) {
    label = t("review.markPending");
    tone = "text-sky-700 dark:text-sky-300";
  } else if (variants.some((v) => v.review_status === "changes_requested")) {
    label = t("review.markChanges");
    tone = "text-red-600 dark:text-red-400";
  } else if (variants.some((v) => v.has_pending)) {
    label = t("review.markProposal");
  }
  if (!label) return null;
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${tone}`} title={label}>
      <GitPullRequestArrow className="h-3.5 w-3.5" aria-hidden="true" />
      <span className="hidden sm:inline">{label}</span>
    </span>
  );
}

/** Everything waiting for a decision, oldest first. Opening an entry takes
 *  the admin to the page's editor, where the diff and the buttons are. */
export function ReviewQueueCard({
  onOpen,
  onClose,
  refreshKey,
}: {
  onOpen: (entry: ReviewQueueEntry) => void;
  onClose: () => void;
  refreshKey: number;
}) {
  const { t, lang } = useI18n();
  const { status: auth } = useAuth();
  const [entries, setEntries] = useState<ReviewQueueEntry[] | null>(null);

  useEffect(() => {
    api
      .adminReviewQueue()
      .then((r) => setEntries(r.reviews))
      .catch(() => setEntries([]));
  }, [refreshKey]);

  return (
    <Card className="mb-4">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          <ClipboardCheck className="h-4 w-4" />
          {t("review.queueTitle")}
        </CardTitle>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label={t("admin.cancel")}>
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent>
        {entries === null && <p className="text-sm text-[var(--muted)]">…</p>}
        {entries !== null && entries.length === 0 && (
          <p className="text-sm text-[var(--muted)]">{t("review.queueEmpty")}</p>
        )}
        {entries !== null && entries.length > 0 && (
          <ul className="divide-y divide-[var(--border)]">
            {entries.map((e) => {
              const own = (e.changed_by || e.submitted_by) === auth?.username;
              return (
                <li key={e.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                  <button
                    type="button"
                    className="font-medium text-[var(--accent)] hover:underline"
                    onClick={() => onOpen(e)}
                  >
                    {e.title}
                  </button>
                  <span className="text-xs text-[var(--muted)]">
                    {e.project_name} › {e.category_name}
                    {e.language ? ` · ${e.language.toUpperCase()}` : ""}
                  </span>
                  <span className="text-xs text-[var(--muted)]">
                    {e.pending ? t("review.kindChange") : t("review.kindNew")}
                  </span>
                  <span className="ml-auto text-xs text-[var(--muted)]">
                    {t("review.submittedShort").replace("{name}", e.submitted_by).replace("{date}", day(e.submitted_at, lang))}
                    {own && ` · ${t("review.yours")}`}
                  </span>
                  {e.note && <p className="w-full text-xs italic text-[var(--muted)]">„{e.note}“</p>}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
