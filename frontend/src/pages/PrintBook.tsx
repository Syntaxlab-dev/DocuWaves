import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Printer } from "lucide-react";
import { api, ApiError, type Book } from "@/lib/api";
import { MarkdownView } from "@/components/MarkdownView";
import { NotFound } from "@/components/NotFound";
import { formatIsoDate } from "@/lib/dates";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { siteText, useDocumentTitle, useSite } from "@/lib/site";

/**
 * A whole project -- or one category of it -- as ONE printable document:
 * a cover, a table of contents, and every published page on a fresh sheet,
 * in the sidebar's order. "Save as PDF" in the browser's print dialog turns
 * it into the manual people ask for.
 *
 * The browser does the PDF, as it already does for single pages (see the
 * print stylesheet in index.css): no rendering service to run, no fonts to
 * ship, and diagrams, formulas and tabs come out exactly as they look on the
 * site because they ARE the site's own rendering. Links inside the PDF stay
 * clickable; the table of contents jumps within the document.
 *
 * The print button waits until the document is really finished -- every
 * diagram rendered, every image loaded. Printing earlier gives a PDF with
 * "Rendering diagram…" in it, or blank spaces where lazy images had not
 * been fetched yet.
 */
export function PrintBook() {
  const { projectSlug = "" } = useParams<{ projectSlug: string }>();
  const [params] = useSearchParams();
  const category = params.get("category") || "";
  const version = params.get("version") || "";
  const { t, lang: uiLang } = useI18n();
  const { lang, path } = useContentLang();
  const { site } = useSite();
  const [book, setBook] = useState<Book | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "notfound" | "failed">("loading");
  const [finished, setFinished] = useState(false);
  const body = useRef<HTMLDivElement>(null);

  const chapterName = category && book?.categories[0]?.name;
  useDocumentTitle(book ? [book.project.name, chapterName].filter(Boolean).join(" – ") : t("book.title"));

  useEffect(() => {
    let current = true;
    setStatus("loading");
    setFinished(false);
    api
      .publicGetBook(projectSlug, lang, version || undefined, category || undefined)
      .then((data) => {
        if (!current) return;
        setBook(data);
        setStatus("ready");
      })
      .catch((error) => current && setStatus(error instanceof ApiError && error.status === 404 ? "notfound" : "failed"));
    return () => {
      current = false;
    };
  }, [projectSlug, lang, version, category]);

  useEffect(() => {
    if (status !== "ready") return;
    const timer = window.setInterval(() => {
      const root = body.current;
      if (!root) return;
      root.querySelectorAll<HTMLImageElement>("img[loading='lazy']").forEach((img) => (img.loading = "eager"));
      const images = Array.from(root.querySelectorAll("img"));
      const done = !root.querySelector(".mermaid-pending") && images.every((img) => img.complete);
      if (done) {
        setFinished(true);
        window.clearInterval(timer);
      }
    }, 300);
    return () => window.clearInterval(timer);
  }, [status, book]);

  if (status === "notfound") return <NotFound />;
  if (status === "failed") return <p className="mx-auto max-w-3xl px-4 py-8 text-[var(--muted)]">{t("common.error")}</p>;
  if (!book) return <p className="mx-auto max-w-3xl px-4 py-8 text-[var(--muted)]">{t("common.loading")}</p>;

  const pageCount = book.categories.reduce((n, c) => n + c.pages.length, 0);
  const versionLabel = book.versions
    ? book.versions.frozen.find((v) => v.id === book.versions!.selected)?.label ?? book.versions.current_label
    : "";
  const anchor = (categorySlug: string, pageSlug: string) => `book-${categorySlug}-${pageSlug}`;
  const back = path(`/p/${projectSlug}${version ? `/${version}` : ""}${category ? `/c/${category}` : ""}`);

  return (
    <div className="book mx-auto max-w-3xl px-4 py-8">
      <div className="book-toolbar print-hide mb-8 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
        <Link to={back} className="inline-flex items-center gap-1 text-sm text-[var(--muted)] hover:text-[var(--accent)]">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          {t("book.back")}
        </Link>
        <span className="text-sm text-[var(--muted)]">
          {t("book.pages").replace("{count}", String(pageCount))}
        </span>
        <button
          type="button"
          onClick={() => window.print()}
          disabled={!finished}
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          <Printer className="h-4 w-4" aria-hidden="true" />
          {finished ? t("book.print") : t("book.preparing")}
        </button>
        <p className="w-full text-xs text-[var(--muted)]">{t("book.hint")}</p>
      </div>

      <div ref={body}>
        <section className="book-cover">
          <p className="text-sm uppercase tracking-wide text-[var(--muted)]">{siteText(site, "name", lang)}</p>
          <h1 className="mt-2 text-4xl font-semibold">{book.project.name}</h1>
          {chapterName && <p className="mt-2 text-2xl">{chapterName}</p>}
          {versionLabel && <p className="mt-4 text-lg">{t("book.version").replace("{version}", versionLabel)}</p>}
          {book.project.description && <p className="mt-6 text-[var(--muted)]">{book.project.description}</p>}
          <p className="mt-12 text-sm text-[var(--muted)]">
            {t("book.printedOn").replace("{date}", formatIsoDate(new Date().toISOString().slice(0, 10), uiLang))}
            <br />
            {typeof window !== "undefined" ? window.location.origin + back : ""}
          </p>
        </section>

        {pageCount > 1 && (
          // A <section>, not a <nav>: the print stylesheet removes every
          // <nav> (site navigation is useless on paper), and this one IS
          // the paper's navigation.
          <section className="book-toc" aria-label={t("book.contents")}>
            <h2 className="text-xl font-semibold">{t("book.contents")}</h2>
            <ol className="mt-4 space-y-3">
              {book.categories.map((c) => (
                <li key={c.slug}>
                  {!category && <p className="font-medium">{c.name}</p>}
                  <ol className={category ? "space-y-1" : "mt-1 space-y-1 pl-4"}>
                    {c.pages.map((p) => (
                      <li key={p.slug}>
                        <a href={`#${anchor(c.slug, p.slug)}`} className="hover:text-[var(--accent)]">
                          {p.title}
                        </a>
                      </li>
                    ))}
                  </ol>
                </li>
              ))}
            </ol>
          </section>
        )}

        {book.categories.map((c) =>
          c.pages.map((p) => (
            <article key={`${c.slug}/${p.slug}`} id={anchor(c.slug, p.slug)} className="book-page">
              {!category && <p className="text-xs uppercase tracking-wide text-[var(--muted)]">{c.name}</p>}
              <h1 className="mt-1 text-2xl font-semibold">{p.title}</h1>
              <MarkdownView
                content={p.markdown_content}
                title={p.title}
                projectSlug={projectSlug}
                categorySlug={c.slug}
                versionDir={p.version}
                lang={p.fallback ? p.language : undefined}
              />
            </article>
          )),
        )}
      </div>
    </div>
  );
}
