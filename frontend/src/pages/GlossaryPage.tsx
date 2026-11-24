import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import type { GlossaryEntry } from "@/lib/glossary";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { useDocumentTitle } from "@/lib/site";
import { useDocPath } from "@/lib/version";

/**
 * A project's glossary as a page (backend services/glossary.py): every term,
 * alphabetically, grouped under its first letter. At /p/<project>/glossary;
 * `?version=` for a version other than the default, like the print view.
 */
export function GlossaryPage() {
  const { projectSlug = "" } = useParams<{ projectSlug: string }>();
  const [params] = useSearchParams();
  const version = params.get("version") || "";
  const { t } = useI18n();
  const { lang } = useContentLang();
  const docPath = useDocPath();
  const [terms, setTerms] = useState<GlossaryEntry[] | null>(null);
  const [projectName, setProjectName] = useState("");

  useDocumentTitle(projectName ? `${t("glossary.title")} – ${projectName}` : t("glossary.title"));

  useEffect(() => {
    setTerms(null);
    api
      .publicGlossary(projectSlug, lang, version || undefined)
      .then((r) => setTerms(r.terms))
      .catch(() => setTerms([]));
    api
      .publicGetProject(projectSlug, lang, version || undefined)
      .then((r) => setProjectName(r.project.name))
      .catch(() => setProjectName(""));
  }, [projectSlug, lang, version]);

  const groups: [string, GlossaryEntry[]][] = [];
  for (const entry of terms ?? []) {
    const letter = entry.term.charAt(0).toLocaleUpperCase(lang || undefined);
    const last = groups[groups.length - 1];
    if (last && last[0] === letter) last[1].push(entry);
    else groups.push([letter, [entry]]);
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <Link to={docPath(projectSlug, "")} className="text-sm text-[var(--accent)] hover:underline">
        ← {projectName || projectSlug}
      </Link>
      <h1 className="mt-2 text-2xl font-semibold">{t("glossary.title")}</h1>
      {terms === null && <p className="mt-6 text-[var(--muted)]">{t("common.loading")}</p>}
      {terms?.length === 0 && <p className="mt-6 text-[var(--muted)]">{t("glossary.empty")}</p>}
      {groups.length > 1 && (
        <nav className="mt-4 flex flex-wrap gap-2 text-sm" aria-label={t("glossary.letters")}>
          {groups.map(([letter]) => (
            <a key={letter} href={`#glossary-${letter}`} className="text-[var(--accent)] hover:underline">
              {letter}
            </a>
          ))}
        </nav>
      )}
      {groups.map(([letter, entries]) => (
        <section key={letter} id={`glossary-${letter}`} className="mt-8">
          <h2 className="border-b border-[var(--border)] pb-1 text-lg font-semibold">{letter}</h2>
          <dl className="mt-3 space-y-3">
            {entries.map((entry) => (
              <div key={entry.term}>
                <dt className="font-medium">{entry.term}</dt>
                <dd className="text-[var(--muted)]">{entry.definition}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}
