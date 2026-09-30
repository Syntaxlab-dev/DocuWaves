import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Rss } from "lucide-react";
import { api, type ChangelogEntry } from "@/lib/api";
import { formatIsoDate } from "@/lib/dates";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { useDocumentTitle, useSite } from "@/lib/site";

/**
 * "New & updated": pages that went live or whose text changed, newest first
 * (backend services/changelog.py). The whole site at /changes, one project
 * at /p/<project>/changes. Grouped by day, because "what changed since I
 * last looked" is a question about days, not about commits.
 */
export function ChangesPage() {
  const { projectSlug = "" } = useParams<{ projectSlug: string }>();
  const { t, lang: uiLang } = useI18n();
  const { lang, path, multilingual } = useContentLang();
  const { site } = useSite();
  const [entries, setEntries] = useState<ChangelogEntry[] | null>(null);

  useDocumentTitle(t("changes.title"));

  useEffect(() => {
    setEntries(null);
    api
      .changelog(lang, projectSlug || undefined)
      .then((r) => setEntries(r.entries))
      .catch(() => setEntries([]));
  }, [lang, projectSlug]);

  const projectName = projectSlug && entries?.[0]?.project_slug === projectSlug ? entries[0].project_name : "";
  const feedLang = multilingual && lang !== site.default_language ? `?lang=${encodeURIComponent(lang)}` : "";
  const feed = `${projectSlug ? `/p/${encodeURIComponent(projectSlug)}` : ""}/feed.xml${feedLang}`;

  const days: [string, ChangelogEntry[]][] = [];
  for (const entry of entries ?? []) {
    const last = days[days.length - 1];
    if (last && last[0] === entry.date) last[1].push(entry);
    else days.push([entry.date, [entry]]);
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{t("changes.title")}</h1>
          {projectName && <p className="mt-1 text-[var(--muted)]">{projectName}</p>}
        </div>
        {/* A plain link to the XML: every feed reader and "add feed" field
            takes the address, and the browser shows what it is. */}
        <a
          href={feed}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm hover:text-[var(--accent)]"
        >
          <Rss className="h-4 w-4" aria-hidden="true" />
          {t("changes.feed")}
        </a>
      </div>

      {entries === null && <p className="mt-8 text-[var(--muted)]">{t("common.loading")}</p>}
      {entries !== null && entries.length === 0 && <p className="mt-8 text-[var(--muted)]">{t("changes.empty")}</p>}

      {days.map(([date, items]) => (
        <section key={date} className="mt-8">
          <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">
            {formatIsoDate(date, uiLang)}
          </h2>
          <ul className="mt-3 space-y-3">
            {items.map((entry) => (
              <li
                key={`${entry.project_slug}/${entry.page_slug}/${entry.language}`}
                className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4"
              >
                <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]">
                  <span
                    className={`rounded-full px-2 py-0.5 font-medium ${
                      entry.kind === "new"
                        ? "bg-[color-mix(in_srgb,#16a34a_15%,transparent)] text-[#16a34a]"
                        : "bg-[var(--accent-soft)] text-[var(--accent)]"
                    }`}
                  >
                    {t(entry.kind === "new" ? "changes.new" : "changes.updated")}
                  </span>
                  <span>
                    {entry.project_name} › {entry.category_name}
                  </span>
                </div>
                <Link
                  to={path(`/p/${entry.project_slug}/pages/${entry.page_slug}`)}
                  className="mt-1 block font-medium hover:text-[var(--accent)]"
                >
                  {entry.title}
                </Link>
                {entry.summary && <p className="mt-1 text-sm text-[var(--muted)]">{entry.summary}</p>}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
