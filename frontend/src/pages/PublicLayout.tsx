import { useState, type FormEvent } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Languages, Moon, Search, Sun } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { languageName, useContentLang } from "@/lib/lang";
import { useProjectVersion } from "@/lib/version";
import { VersionSwitcher } from "@/components/VersionSwitcher";
import { logoForTheme, siteText, useSite } from "@/lib/site";
import { applyTheme, getPreferredTheme } from "@/lib/theme";

export function PublicLayout() {
  const { t, lang: uiLang, setLang: setUiLang } = useI18n();
  const { site } = useSite();
  const contentLang = useContentLang();
  const projectVersion = useProjectVersion();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [isDark, setIsDark] = useState(getPreferredTheme() === "dark");

  function toggleTheme() {
    const next = isDark ? "light" : "dark";
    applyTheme(next);
    setIsDark(next === "dark");
  }

  function onSearch(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    // Searching from inside a documentation version searches THAT version:
    // the reader is standing in one release's docs, and a hit from another
    // one would move them out of it without saying so. Carried in the URL
    // rather than in component state so the results page is a shareable
    // address that means the same thing tomorrow. Nothing is added at all
    // outside a versioned project, so an unversioned instance's search URLs
    // are exactly the ones it always had.
    const scope = projectVersion.info
      ? `&project=${encodeURIComponent(projectVersion.projectSlug)}` +
        `&version=${encodeURIComponent(projectVersion.version || projectVersion.info.default)}`
      : "";
    navigate(contentLang.path(`/search?q=${encodeURIComponent(q.trim())}${scope}`));
  }

  const logoUrl = logoForTheme(site, isDark);
  const footerText = siteText(site, "footer_text", contentLang.lang);
  const hasFooter = Boolean(footerText) || site.footer_links.length > 0;

  return (
    // flex column so the footer sits at the bottom of a short page instead
    // of floating halfway up it.
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-[var(--border)] bg-[var(--surface)]">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
          <Link to={contentLang.path("/")} className="flex items-center gap-2 text-lg font-semibold">
            {/* alt="" -- the name sits right next to it in text, so a screen
                reader announcing the logo too would just say it twice. */}
            {logoUrl && <img src={logoUrl} alt="" className="h-7 w-auto max-w-[10rem] object-contain" />}
            <span>{siteText(site, "name", contentLang.lang)}</span>
          </Link>
          <form onSubmit={onSearch} className="ml-auto flex flex-1 max-w-sm items-center gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted)]" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={t("nav.search")}
                className="pl-8"
              />
            </div>
          </form>
          <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="theme">
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
          {/* Two different questions, so two different controls -- and only
              ever one of them at a time. On a multilingual instance the
              switcher picks the CONTENT language (and the interface follows
              it, see lib/lang.tsx); on a single-language one there is no
              content language to pick, so the interface toggle stays
              exactly the control it has always been. */}
          {/* Next to the language switcher, and on the same terms: it
              renders only where there is something to switch. */}
          <VersionSwitcher />
          {contentLang.multilingual ? (
            <ContentLanguageSwitcher />
          ) : (
            <Button variant="ghost" size="sm" onClick={() => setUiLang(uiLang === "de" ? "en" : "de")}>
              {uiLang === "de" ? "EN" : "DE"}
            </Button>
          )}
        </div>
      </header>
      {/* No container of its own: the docs views need a wider one than the
          home and search views (a sidebar and a contents column live beside
          the text there), so each view owns its width. */}
      <main className="flex-1">
        <Outlet />
      </main>
      {/* Nothing configured, no footer at all -- an empty bar would be a
          visible change to an instance that never asked for one. */}
      {hasFooter && (
        <footer className="mt-12 border-t border-[var(--border)] bg-[var(--surface)]">
          <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-6 text-sm text-[var(--muted)]">
            {footerText && <span>{footerText}</span>}
            {site.footer_links.map((link) => (
              <a
                key={`${link.label}-${link.url}`}
                href={link.url}
                // These point off this site by definition (the backend only
                // accepts http(s)/mailto/site-relative), so: new tab, and
                // noreferrer stops the target from reaching back via
                // window.opener.
                target="_blank"
                rel="noreferrer noopener"
                className="hover:text-[var(--accent)]"
              >
                {link.label}
              </a>
            ))}
          </div>
        </footer>
      )}
    </div>
  );
}

/**
 * Switches the content language while staying on the same page: the slug is
 * shared by a page's translations, so only the URL's language segment
 * changes and the reader keeps reading where they were. A page that has no
 * version in the language they picked still opens -- with the fallback
 * notice on it (see PublicPage) rather than a 404.
 *
 * A plain row of codes rather than a dropdown: an instance has two or three
 * languages, and a menu to open would be one more click for the one thing a
 * bilingual reader does most often on this header.
 */
function ContentLanguageSwitcher() {
  const { t } = useI18n();
  const { lang, languages } = useContentLang();
  const { pathname, search, hash } = useLocation();

  // Everything after the current language segment is the page itself.
  const rest = pathname.split("/").slice(2).join("/");

  return (
    <div className="flex items-center gap-1" aria-label={t("nav.language")}>
      <Languages className="h-3.5 w-3.5 text-[var(--muted)]" aria-hidden="true" />
      {languages.map((code) => (
        <Link
          key={code}
          to={`/${code}${rest ? `/${rest}` : ""}${search}${hash}`}
          hrefLang={code}
          aria-current={code === lang ? "true" : undefined}
          title={languageName(code, lang)}
          className={
            code === lang
              ? "rounded px-1.5 py-1 text-sm font-medium text-[var(--accent)]"
              : "rounded px-1.5 py-1 text-sm text-[var(--muted)] hover:text-[var(--ink)]"
          }
        >
          {code.toUpperCase()}
        </Link>
      ))}
    </div>
  );
}
