import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  CircleCheckBig,
  Clock,
  Download,
  ExternalLink,
  FolderPlus,
  History,
  SearchX,
  Sparkles,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import {
  api,
  type ActivityEntry,
  type Project,
  type ReviewDuePage,
  type ReviewQueueEntry,
  type SearchGap,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** What the dashboard can open: enough for AdminApp to pick the project, the
 *  category and then the page in the editor. */
export interface OpenTarget {
  project_slug: string;
  category_id: number;
  slug: string;
  language: string;
}

interface Recent extends OpenTarget {
  title: string;
  project_name: string;
  author: string;
  date: string;
  pending: boolean;
}

const LIMIT = 6;

/** The pages touched by the latest commits, newest first, each once. */
function recentPages(entries: ActivityEntry[]): Recent[] {
  const seen = new Set<string>();
  const out: Recent[] = [];
  for (const entry of entries) {
    for (const page of entry.pages) {
      // Gone since (deleted or renamed): nothing to open.
      if (!page.title || !page.category_id) continue;
      const key = `${page.project_slug}/${page.version}/${page.slug}/${page.language}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({
        project_slug: page.project_slug,
        project_name: page.project_name,
        category_id: page.category_id,
        slug: page.slug,
        language: page.language,
        title: page.title,
        pending: page.pending,
        author: entry.author,
        date: entry.date,
      });
    }
  }
  return out;
}

export function relativeTime(iso: string, lang: string, now = Date.now()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const seconds = Math.round((then - now) / 1000);
  const format = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["week", 604_800],
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit);
  }
  return format.format(0, "minute");
}

export function Dashboard({
  projects,
  canWrite,
  reviewsKey,
  onOpen,
}: {
  projects: Project[];
  canWrite: boolean;
  /** Changes after every save, so the counts never lag behind the work. */
  reviewsKey: number;
  onOpen: (target: OpenTarget) => void;
}) {
  const { t, lang } = useI18n();
  const [loaded, setLoaded] = useState(false);
  const [reviews, setReviews] = useState<ReviewQueueEntry[]>([]);
  const [recent, setRecent] = useState<Recent[]>([]);
  const [due, setDue] = useState<ReviewDuePage[]>([]);
  const [gaps, setGaps] = useState<SearchGap[]>([]);

  useEffect(() => {
    let live = true;
    // Each list on its own: one that fails (an area this account may not
    // read, an old server) leaves the others standing.
    Promise.all([
      api.adminReviewQueue().catch(() => ({ reviews: [] as ReviewQueueEntry[] })),
      api.adminActivity(30).catch(() => ({ entries: [] as ActivityEntry[] })),
      api.adminReviewDue().catch(() => ({ pages: [] as ReviewDuePage[] })),
      api.adminSearchGaps().catch(() => ({ gaps: [] as SearchGap[] })),
    ]).then(([r, a, d, g]) => {
      if (!live) return;
      setReviews(r.reviews);
      setRecent(recentPages(a.entries));
      setDue(d.pages);
      setGaps(g.gaps);
      setLoaded(true);
    });
    return () => {
      live = false;
    };
  }, [reviewsKey]);

  const stats: { label: string; value: number; to: string; icon: ComponentType<{ className?: string }> }[] = [
    { label: t("dash.projects"), value: projects.length, to: "/admin/content", icon: FolderPlus },
    { label: t("dash.approvals"), value: reviews.length, to: "/admin/reviews", icon: CircleCheckBig },
    { label: t("dash.due"), value: due.length, to: "/admin/insights", icon: Clock },
    { label: t("dash.gaps"), value: gaps.length, to: "/admin/insights", icon: SearchX },
  ];

  if (loaded && projects.length === 0) {
    return (
      <Card className="mx-auto max-w-xl px-8 py-12 text-center">
        <Sparkles className="mx-auto h-10 w-10 text-[var(--accent)]" aria-hidden="true" />
        <h2 className="mt-4 text-xl font-semibold">{t("dash.emptyTitle")}</h2>
        <p className="mt-2 text-[var(--muted)]">{t(canWrite ? "dash.emptyText" : "dash.emptyReadOnly")}</p>
        {canWrite && (
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <Link
              to="/admin/content"
              className="inline-flex items-center gap-2 rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-[var(--accent-ink)]"
            >
              <FolderPlus className="h-4 w-4" /> {t("dash.createProject")}
            </Link>
            <Link
              to="/admin/import"
              className="inline-flex items-center gap-2 rounded-md border border-[var(--border)] px-4 py-2 text-sm"
            >
              <Download className="h-4 w-4" /> {t("dash.importDocs")}
            </Link>
          </div>
        )}
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold">{t("dash.title")}</h1>
        <div className="flex flex-wrap gap-2 text-sm">
          <Link
            to="/admin/content"
            className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 hover:bg-[var(--surface-2)]"
          >
            {t("dash.toContent")} <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 hover:bg-[var(--surface-2)]"
          >
            {t("nav.public")} <ExternalLink className="h-4 w-4" />
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {stats.map((s) => (
          <Link key={s.label} to={s.to} className="group">
            <Card className="flex items-center gap-3 p-4 transition-colors group-hover:border-[var(--accent)]">
              <s.icon className="h-5 w-5 shrink-0 text-[var(--accent)]" aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-2xl font-semibold leading-tight">{loaded ? s.value : "–"}</p>
                <p className="truncate text-xs text-[var(--muted)]">{s.label}</p>
              </div>
            </Card>
          </Link>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t("dash.waiting")} icon={CircleCheckBig} more={reviews.length > LIMIT ? "/admin/reviews" : undefined} loaded={loaded}>
          {reviews.length === 0 ? (
            <Empty text={t("dash.waitingNone")} />
          ) : (
            reviews.slice(0, LIMIT).map((r) => (
              <Row
                key={r.id}
                title={r.title}
                detail={`${r.project_name} · ${r.category_name} · ${r.submitted_by}`}
                onClick={() => onOpen(r)}
              />
            ))
          )}
        </Section>

        <Section title={t("dash.recent")} icon={History} more="/admin/activity" loaded={loaded}>
          {recent.length === 0 ? (
            <Empty text={t("dash.recentNone")} />
          ) : (
            recent.slice(0, LIMIT).map((r) => (
              <Row
                key={`${r.project_slug}/${r.slug}/${r.language}`}
                title={r.title}
                badge={r.pending ? t("dash.proposal") : undefined}
                detail={`${r.project_name} · ${r.author} · ${relativeTime(r.date, lang)}`}
                onClick={() => onOpen(r)}
              />
            ))
          )}
        </Section>

        <Section title={t("dash.dueTitle")} icon={Clock} more={due.length > LIMIT ? "/admin/insights" : undefined} loaded={loaded}>
          {due.length === 0 ? (
            <Empty text={t("dash.dueNone")} />
          ) : (
            due.slice(0, LIMIT).map((d) => (
              <Row
                key={d.page_id}
                title={d.title}
                detail={`${d.project_name} · ${
                  d.days_overdue === null ? t("dash.neverReviewed") : t("dash.overdue").replace("{n}", String(d.days_overdue))
                }`}
                onClick={() =>
                  onOpen({ project_slug: d.project_slug, category_id: d.category_id, slug: d.slug, language: d.language })
                }
              />
            ))
          )}
        </Section>

        <Section title={t("dash.gapsTitle")} icon={SearchX} more="/admin/insights" loaded={loaded}>
          {gaps.length === 0 ? (
            <Empty text={t("dash.gapsNone")} />
          ) : (
            gaps.slice(0, LIMIT).map((g) => (
              <Row
                key={g.id}
                title={`„${g.query}“`}
                detail={t("dash.searches").replace("{n}", String(g.hits))}
                to="/admin/insights"
              />
            ))
          )}
        </Section>
      </div>
    </div>
  );
}

function Section({
  title,
  icon: Icon,
  more,
  loaded,
  children,
}: {
  title: string;
  icon: ComponentType<{ className?: string }>;
  more?: string;
  loaded: boolean;
  children: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <Card className="flex flex-col">
      <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3">
        <Icon className="h-4 w-4 text-[var(--muted)]" aria-hidden="true" />
        <h2 className="text-sm font-semibold">{title}</h2>
        {more && (
          <Link to={more} className="ml-auto text-xs text-[var(--accent)]">
            {t("dash.all")}
          </Link>
        )}
      </div>
      <ul className="divide-y divide-[var(--border)]">
        {loaded ? children : <Skeleton />}
      </ul>
    </Card>
  );
}

function Row({
  title,
  detail,
  badge,
  onClick,
  to,
}: {
  title: string;
  detail: string;
  badge?: string;
  onClick?: () => void;
  to?: string;
}) {
  const body = (
    <>
      <span className="flex min-w-0 items-center gap-2">
        <span className="truncate text-sm font-medium">{title}</span>
        {badge && (
          <span className="shrink-0 rounded-full bg-[var(--surface-2)] px-2 text-[10px] font-medium leading-4 text-[var(--muted)]">
            {badge}
          </span>
        )}
      </span>
      <span className="block truncate text-xs text-[var(--muted)]">{detail}</span>
    </>
  );
  const className = "block w-full px-4 py-2.5 text-left hover:bg-[var(--surface-2)]";
  return (
    <li>
      {to ? (
        <Link to={to} className={className}>
          {body}
        </Link>
      ) : (
        <button type="button" className={className} onClick={onClick}>
          {body}
        </button>
      )}
    </li>
  );
}

function Empty({ text }: { text: string }) {
  return <li className="px-4 py-6 text-center text-sm text-[var(--muted)]">{text}</li>;
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, i) => (
        <li key={i} className="px-4 py-3" aria-hidden="true">
          <div className="h-3.5 w-2/3 animate-pulse rounded bg-[var(--surface-2)]" />
          <div className="mt-2 h-2.5 w-1/3 animate-pulse rounded bg-[var(--surface-2)]" />
        </li>
      ))}
    </>
  );
}
