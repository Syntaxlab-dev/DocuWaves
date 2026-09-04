import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Eye, Moon, Sun } from "lucide-react";
import { api, type PreviewData } from "@/lib/api";
import { MarkdownView } from "@/components/MarkdownView";
import { TableOfContents } from "@/components/TableOfContents";
import { collectHeadings } from "@/lib/headings";
import { formatIsoDate } from "@/lib/dates";
import { useI18n } from "@/lib/i18n";
import { siteText, useDocumentTitle, useSite } from "@/lib/site";
import { applyTheme, getPreferredTheme } from "@/lib/theme";
import { Button } from "@/components/ui/button";

/**
 * One page behind a preview link: unpublished, readable by whoever holds the
 * link, until the date on it.
 *
 * DELIBERATELY NOT INSIDE PublicLayout, and that is the whole design. The
 * layout carries a search box, a home link, a sidebar and a language
 * switcher -- every one of them a way out of this page and into the rest of
 * the instance, which is precisely what the holder of this link was not
 * given access to. So this view has a header that says where it is and what
 * it is, and nothing that navigates. The backend enforces the same boundary
 * on its side (see routers/public_content.py's preview endpoint): the token
 * reads one page and cannot ask for another.
 *
 * The reader is a person who was sent a draft to read, not a visitor who
 * found the site. So the page says, before the text, that this is a draft
 * and that the link runs out -- rather than letting them take unfinished
 * writing for the documentation.
 */
export function PreviewPage() {
  const { token } = useParams<{ token: string }>();
  const { t, lang: uiLang } = useI18n();
  const { site } = useSite();
  const [data, setData] = useState<PreviewData | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "invalid">("loading");
  const [isDark, setIsDark] = useState(getPreferredTheme() === "dark");

  useEffect(() => {
    if (!token) return;
    let current = true;
    api
      .publicPreview(token)
      .then((result) => {
        if (!current) return;
        setData(result);
        setStatus("ready");
      })
      .catch(() => {
        // One message for every reason, exactly as the endpoint answers one
        // status for all of them: a dead link is a dead link, and telling
        // its holder which KIND of dead would be telling them something
        // about a page they cannot read.
        if (current) setStatus("invalid");
      });
    return () => {
      current = false;
    };
  }, [token]);

  useDocumentTitle(data?.page.title);

  const headings = useMemo(() => (data ? collectHeadings(data.page.markdown_content) : []), [data]);

  function toggleTheme() {
    const next = isDark ? "light" : "dark";
    applyTheme(next);
    setIsDark(next === "dark");
  }

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <header className="border-b border-[var(--border)] bg-[var(--surface)]">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
          <span className="flex items-center gap-1.5 rounded-full border border-amber-500/60 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-600">
            <Eye className="h-3.5 w-3.5" aria-hidden="true" />
            {t("preview.badge")}
          </span>
          {/* The site's name, as a label and not as a link: it says which
              instance this draft belongs to, without offering a way in. */}
          <span className="min-w-0 flex-1 truncate text-sm text-[var(--muted)]">
            {siteText(site, "name", uiLang)}
          </span>
          <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={t(isDark ? "nav.toLightMode" : "nav.toDarkMode")}>
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8">
        {status === "loading" && <p className="text-[var(--muted)]">{t("common.loading")}</p>}

        {status === "invalid" && (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-6 text-sm">
            {t("preview.invalid")}
          </div>
        )}

        {status === "ready" && data && (
          <>
            <div className="mb-5 rounded-lg border border-amber-500/60 bg-amber-500/10 px-3 py-2.5 text-sm">
              <p>{t("preview.notice")}</p>
              {/* The expiry, said out loud. A link that simply stops working
                  one morning reads as a fault; a date reads as a deadline,
                  which is what it is. */}
              <p className="mt-1 text-[var(--muted)]">
                {t("preview.expires").replace("{date}", formatIsoDate(data.expires_at, uiLang))}
              </p>
              {/* A published page reached through a preview link is not an
                  error -- the draft was published while the link was still
                  live. Saying so stops the reader reviewing something that
                  has already gone out. */}
              {data.page.published && <p className="mt-1 text-[var(--muted)]">{t("preview.published")}</p>}
            </div>

            <div className="text-sm text-[var(--muted)]">
              {data.project.name}
              {data.category ? ` / ${data.category.name}` : ""}
            </div>
            <h1 className="mt-2 mb-4 text-2xl font-semibold">{data.page.title}</h1>

            {headings.length >= 2 && <TableOfContents headings={headings} variant="standalone" />}

            {/* versionDir is the page file's own directory, so `../assets/…`
                in the draft resolves the same way it will once published. */}
            <MarkdownView
              content={data.page.markdown_content}
              title={data.page.title}
              projectSlug={data.project.slug}
              categorySlug={data.category?.slug}
              versionDir={data.page.version}
            />
          </>
        )}
      </main>
    </div>
  );
}
