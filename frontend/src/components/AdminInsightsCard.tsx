import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FilePlus2, MessageSquare, Sparkles, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { api, ApiError, type FeedbackComment, type FeedbackSummary, type ReviewDuePage, type SearchGap } from "@/lib/api";
import { formatIsoDate } from "@/lib/dates";
import { useI18n } from "@/lib/i18n";
import { usePermissions } from "@/lib/auth";
import { askConfirm } from "@/components/ConfirmDialog";

type Broken = {
  project_slug: string;
  page_slug: string;
  page_title: string;
  version: string;
  target: string;
  reason: string;
};

/**
 * What the documentation itself says about its own state: which pages
 * readers said did not help, and which links no longer go anywhere.
 *
 * Both are read-only reports plus one destructive action each (forgetting a
 * page's votes), so they share a card rather than each taking a place in the
 * header. They are also both things an author looks at occasionally and not
 * while writing.
 */
export function AdminInsightsCard({
  onClose,
  onCreatePage,
}: {
  onClose: () => void;
  /** Starts a new page with this title, in this project when the search
   *  was scoped to one ("" = the one currently selected). */
  onCreatePage: (title: string, projectSlug: string, body?: string) => void;
}) {
  const { t, lang } = useI18n();
  // Forgetting a page's votes is a DELETE, so a read-only account does not
  // get the button. Both reports themselves are reading and stay -- they
  // are, in fact, most of what a reviewer account is for.
  const { canWrite } = usePermissions();
  const [feedback, setFeedback] = useState<FeedbackSummary[] | null>(null);
  // The readers' notes of the one page opened in the list, keyed by it.
  const [notes, setNotes] = useState<{ key: string; comments: FeedbackComment[] } | null>(null);
  const [broken, setBroken] = useState<Broken[] | null>(null);
  const [gaps, setGaps] = useState<{ enabled: boolean; gaps: SearchGap[]; can_draft?: boolean } | null>(null);
  const [drafting, setDrafting] = useState<number | null>(null);
  const [due, setDue] = useState<ReviewDuePage[] | null>(null);

  async function load() {
    const [f, b, g, d] = await Promise.all([
      api.adminFeedback().catch(() => ({ pages: [] as FeedbackSummary[] })),
      api.adminLinkCheck().catch(() => ({ broken: [] as Broken[] })),
      api.adminSearchGaps().catch(() => ({ enabled: true, gaps: [] as SearchGap[] })),
      api.adminReviewDue().catch(() => ({ pages: [] as ReviewDuePage[], count: 0 })),
    ]);
    setDue(d.pages);
    setFeedback(f.pages);
    setBroken(b.broken);
    setGaps(g);
  }

  async function draftGap(gap: SearchGap) {
    setDrafting(gap.id);
    const waiting = toast.loading(t("gaps.drafting"));
    try {
      const result = await api.adminDraftFromGap(gap.query, gap.project_slug, gap.language);
      toast.dismiss(waiting);
      onCreatePage(result.title, gap.project_slug, result.markdown);
    } catch (error) {
      toast.dismiss(waiting);
      toast.error(error instanceof ApiError && error.message === "not_configured" ? t("gaps.draftNoModel") : t("gaps.draftFailed"));
    } finally {
      setDrafting(null);
    }
  }

  async function forgetGap(id: number | null) {
    if (id === null && !(await askConfirm({ title: t("gaps.clearConfirm"), danger: true }))) return;
    try {
      await (id === null ? api.adminClearSearchGaps() : api.adminForgetSearchGap(id));
      await load();
    } catch {
      toast.error(t("common.error"));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function toggleNotes(projectSlug: string, pageSlug: string) {
    const key = `${projectSlug}/${pageSlug}`;
    if (notes?.key === key) {
      setNotes(null);
      return;
    }
    try {
      const { comments } = await api.adminFeedbackComments(projectSlug, pageSlug);
      setNotes({ key, comments });
    } catch {
      toast.error(t("common.error"));
    }
  }

  async function clearVotes(projectSlug: string, pageSlug: string) {
    try {
      const { cleared } = await api.adminClearFeedback(projectSlug, pageSlug);
      toast.success(t("insights.cleared").replace("{n}", String(cleared)));
      await load();
    } catch {
      toast.error(t("common.error"));
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{t("insights.title")}</CardTitle>
        <Button variant="ghost" size="sm" onClick={onClose}>
          {t("common.back")}
        </Button>
      </CardHeader>
      <CardContent className="grid gap-8 lg:grid-cols-2">
        {/* First and full width: of the three, the only one that says what
            is MISSING rather than what is wrong with what exists. */}
        <section className="lg:col-span-2">
          <div className="mb-1 flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{t("gaps.title")}</h3>
            {canWrite && gaps && gaps.gaps.length > 0 && (
              <Button variant="ghost" size="sm" onClick={() => void forgetGap(null)}>
                {t("gaps.clearAll")}
              </Button>
            )}
          </div>
          <p className="mb-3 text-xs text-[var(--muted)]">{t("gaps.hint")}</p>
          {gaps === null && <p className="text-sm text-[var(--muted)]">{t("common.loading")}</p>}
          {gaps && !gaps.enabled && <p className="text-sm text-[var(--muted)]">{t("gaps.off")}</p>}
          {gaps?.enabled && gaps.gaps.length === 0 && (
            <p className="text-sm text-[var(--muted)]">{t("gaps.none")}</p>
          )}
          {gaps?.enabled && gaps.gaps.length > 0 && (
            <ul className="grid gap-2 md:grid-cols-2">
              {gaps.gaps.map((gap) => (
                <li
                  key={gap.id}
                  className="flex items-center gap-2 rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">„{gap.query}“</span>
                    <span className="block truncate text-xs text-[var(--muted)]">
                      {t("gaps.count").replace("{n}", String(gap.hits))}
                      {gap.project_slug && ` · ${gap.project_slug}`}
                      {gap.language && ` · ${gap.language.toUpperCase()}`}
                      {` · ${gap.last_seen}`}
                    </span>
                  </span>
                  {canWrite && (
                    <>
                      {gaps?.can_draft && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 shrink-0"
                          title={t("gaps.draftPage")}
                          aria-label={t("gaps.draftPage")}
                          disabled={drafting !== null}
                          onClick={() => void draftGap(gap)}
                        >
                          <Sparkles className="h-4 w-4" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 shrink-0"
                        title={t("gaps.createPage")}
                        aria-label={t("gaps.createPage")}
                        onClick={() => onCreatePage(gap.query, gap.project_slug)}
                      >
                        <FilePlus2 className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 shrink-0"
                        title={t("gaps.forget")}
                        aria-label={t("gaps.forget")}
                        onClick={() => void forgetGap(gap.id)}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h3 className="mb-1 text-sm font-semibold">{t("insights.feedbackTitle")}</h3>
          <p className="mb-3 text-xs text-[var(--muted)]">{t("insights.feedbackHint")}</p>
          {feedback === null && <p className="text-sm text-[var(--muted)]">{t("common.loading")}</p>}
          {feedback?.length === 0 && <p className="text-sm text-[var(--muted)]">{t("insights.noFeedback")}</p>}
          {feedback && feedback.length > 0 && (
            <ul className="flex flex-col gap-2">
              {feedback.map((row) => (
                <li
                  key={`${row.project_slug}/${row.version}/${row.page_slug}/${row.language}`}
                  className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
                >
                  <div className="flex items-center gap-3">
                    <span className="min-w-0 flex-1 truncate">
                      {row.project_slug} / {row.page_slug}
                      {row.version && <span className="text-[var(--muted)]"> · {row.version}</span>}
                    </span>
                    <span className="shrink-0 tabular-nums text-[var(--muted)]">
                      {row.helpful} / {row.total}
                    </span>
                    {row.comments > 0 && (
                      <Button variant="ghost" size="sm" onClick={() => void toggleNotes(row.project_slug, row.page_slug)}>
                        <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />
                        {notes?.key === `${row.project_slug}/${row.page_slug}`
                          ? t("insights.notesHide")
                          : t("insights.notes").replace("{n}", String(row.comments))}
                      </Button>
                    )}
                    {canWrite && (
                      <Button variant="ghost" size="sm" onClick={() => clearVotes(row.project_slug, row.page_slug)}>
                        {t("insights.clear")}
                      </Button>
                    )}
                  </div>
                  {notes?.key === `${row.project_slug}/${row.page_slug}` && (
                    <ul className="mt-2 flex flex-col gap-1.5 border-t border-[var(--border)] pt-2">
                      {notes.comments.map((note, index) => (
                        <li key={`${note.created_at}/${index}`} className="flex gap-2">
                          {note.helpful ? (
                            <ThumbsUp className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--muted)]" aria-hidden="true" />
                          ) : (
                            <ThumbsDown className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--muted)]" aria-hidden="true" />
                          )}
                          <span className="min-w-0 flex-1 whitespace-pre-line break-words">{note.comment}</span>
                          <time className="shrink-0 text-xs text-[var(--muted)]" dateTime={note.created_at}>
                            {formatIsoDate(note.created_at.slice(0, 10), lang)}
                          </time>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h3 className="mb-1 text-sm font-semibold">{t("insights.linksTitle")}</h3>
          {/* Said plainly rather than left to be discovered: someone who
              expects external URLs to be checked would read an empty list as
              "everything is fine". */}
          <p className="mb-3 text-xs text-[var(--muted)]">{t("insights.linksHint")}</p>
          {broken === null && <p className="text-sm text-[var(--muted)]">{t("common.loading")}</p>}
          {broken?.length === 0 && <p className="text-sm text-[var(--muted)]">{t("insights.noBroken")}</p>}
          {broken && broken.length > 0 && (
            <ul className="flex flex-col gap-2">
              {broken.map((row, index) => (
                <li
                  key={`${row.project_slug}/${row.page_slug}/${row.target}/${index}`}
                  className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
                >
                  <div className="truncate font-medium">{row.page_title}</div>
                  <div className="truncate text-xs text-[var(--muted)]">
                    <code>{row.target}</code> — {row.reason}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="lg:col-span-2">
          <h3 className="mb-1 text-sm font-semibold">
            {t("reviewDue.title")}
            {due && due.length > 0 && <span className="ml-2 tabular-nums text-[var(--muted)]">{due.length}</span>}
          </h3>
          <p className="mb-3 text-xs text-[var(--muted)]">{t("reviewDue.hint")}</p>
          {due === null && <p className="text-sm text-[var(--muted)]">{t("common.loading")}</p>}
          {due?.length === 0 && <p className="text-sm text-[var(--muted)]">{t("reviewDue.none")}</p>}
          {due && due.length > 0 && (
            <ul className="flex flex-col gap-2">
              {due.map((row) => (
                <li
                  key={`${row.page_id}`}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
                >
                  <a
                    href={`/p/${row.project_slug}/pages/${row.slug}`}
                    target="_blank"
                    rel="noreferrer"
                    className="min-w-0 flex-1 truncate font-medium hover:underline"
                  >
                    {row.title}
                    {row.language && <span className="text-[var(--muted)]"> · {row.language}</span>}
                  </a>
                  <span className="truncate text-xs text-[var(--muted)]">
                    {row.project_name} / {row.category_name}
                  </span>
                  <span className="shrink-0 text-xs text-[var(--muted)]">
                    {row.days_overdue === null
                      ? t("reviewDue.never")
                      : t("reviewDue.overdue")
                          .replace("{date}", formatIsoDate(row.reviewed_at.slice(0, 10), lang))
                          .replace("{n}", String(row.days_overdue))}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </CardContent>
    </Card>
  );
}
