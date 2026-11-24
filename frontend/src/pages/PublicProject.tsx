import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CloudDownload } from "lucide-react";
import { offlineAvailable, saveForOffline, savedAt } from "@/lib/offline";
import { CategoryTiles } from "@/components/CategoryTiles";
import { DocsShell } from "@/components/DocsShell";
import { NotFound } from "@/components/NotFound";
import { PrivateBadge } from "@/components/PrivateBadge";
import { api } from "@/lib/api";
import { useGlossary } from "@/lib/glossary";
import { topCategories, useProjectNav } from "@/lib/nav";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { useDocPath, useReportProjectVersion } from "@/lib/version";
import { useDocumentTitle } from "@/lib/site";

export function PublicProject() {
  const { projectSlug, version } = useParams<{ projectSlug: string; version: string }>();
  const { t } = useI18n();
  const { lang, path } = useContentLang();
  const docPath = useDocPath();
  // The nav endpoint returns this project plus every category and its
  // published pages, which is a superset of what the tiles need -- so the
  // sidebar costs no extra request here, and the tiles can't disagree with
  // the tree standing next to them.
  const { nav, status } = useProjectNav(projectSlug, lang, version);
  const glossary = useGlossary(projectSlug, lang, version);
  const [offline, setOffline] = useState<{ done: number; total: number } | null>(null);
  const [saved, setSaved] = useState(() => savedAt(projectSlug ?? "", lang, version ?? ""));

  async function keepOffline() {
    if (!projectSlug) return;
    setOffline({ done: 0, total: 0 });
    try {
      await saveForOffline(projectSlug, lang, version ?? "", (done, total) => setOffline({ done, total }));
      setSaved(savedAt(projectSlug, lang, version ?? ""));
    } finally {
      setOffline(null);
    }
  }

  // The project's landing page exists in every version, so the switcher can
  // always stay put here -- `tail` is empty and `available` unused.
  useReportProjectVersion({
    projectSlug: projectSlug ?? "",
    version: version ?? "",
    tail: "",
    info: nav?.versions ?? null,
  });

  useDocumentTitle(nav?.project.name);

  if (status === "notfound") return <NotFound />;
  if (status === "failed") return <p className="mx-auto max-w-5xl px-4 py-8 text-[var(--muted)]">{t("common.error")}</p>;
  if (!nav) return <p className="mx-auto max-w-5xl px-4 py-8 text-[var(--muted)]">{t("common.loading")}</p>;

  const categories = topCategories(nav);

  return (
    <DocsShell nav={nav}>
      <div className="flex items-center gap-2">
        {nav.project.icon && <span className="text-2xl">{nav.project.icon}</span>}
        <h1 className="text-2xl font-semibold">{nav.project.name}</h1>
        {nav.project.private && <PrivateBadge />}
      </div>
      {nav.project.description && <p className="mt-1 text-[var(--muted)]">{nav.project.description}</p>}
      <Link
        to={path(`/p/${nav.project.slug}/changes`)}
        className="mt-2 inline-block text-sm text-[var(--accent)] hover:underline"
      >
        {t("changes.link")} →
      </Link>
      <Link
        to={path(`/p/${nav.project.slug}/print${version ? `?version=${encodeURIComponent(version)}` : ""}`)}
        className="ml-4 mt-2 inline-block text-sm text-[var(--accent)] hover:underline"
      >
        {t("book.link")} →
      </Link>
      {glossary.length > 0 && (
        <Link
          to={path(`/p/${nav.project.slug}/glossary${version ? `?version=${encodeURIComponent(version)}` : ""}`)}
          className="ml-4 mt-2 inline-block text-sm text-[var(--accent)] hover:underline"
        >
          {t("glossary.title")} →
        </Link>
      )}
      {/* Plain links: the server answers with the file to save. */}
      <a
        href={api.publicProjectExportUrl(nav.project.slug, "epub", lang, version)}
        title={t("book.epubHint")}
        download
        className="ml-4 mt-2 inline-block text-sm text-[var(--accent)] hover:underline"
      >
        {t("book.epub")} ↓
      </a>
      <a
        href={api.publicProjectExportUrl(nav.project.slug, "markdown", lang, version)}
        title={t("book.markdownHint")}
        download
        className="ml-4 mt-2 inline-block text-sm text-[var(--accent)] hover:underline"
      >
        {t("book.markdown")} ↓
      </a>

      {/* Only with a service worker in control (public/sw.js): without one
          there is nowhere to keep the pages. */}
      {offlineAvailable() && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-[var(--muted)]">
          <button
            type="button"
            onClick={() => void keepOffline()}
            disabled={offline !== null}
            title={t("offline.saveHint")}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-2.5 py-1 hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:opacity-60"
          >
            <CloudDownload className="h-3.5 w-3.5" aria-hidden="true" />
            {offline
              ? t("offline.saving").replace("{done}", String(offline.done)).replace("{total}", String(offline.total || "…"))
              : t(saved ? "offline.update" : "offline.save")}
          </button>
          {saved && !offline && (
            <span>{t("offline.savedOn").replace("{date}", new Date(saved).toLocaleDateString(lang || undefined))}</span>
          )}
        </div>
      )}

      <h2 className="mt-8 text-sm font-medium uppercase tracking-wide text-[var(--muted)]">
        {t("project.categories")}
      </h2>
      {categories.length === 0 && <p className="mt-4 text-[var(--muted)]">{t("project.empty")}</p>}
      <CategoryTiles nav={nav} categories={categories} href={(c) => docPath(nav.project.slug, `/c/${c.slug}`)} />
    </DocsShell>
  );
}
