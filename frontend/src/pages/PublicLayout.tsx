import { useState, type FormEvent } from "react";
import { Link, Outlet, useNavigate } from "react-router-dom";
import { Moon, Search, Sun } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { logoForTheme, useSite } from "@/lib/site";
import { applyTheme, getPreferredTheme } from "@/lib/theme";

export function PublicLayout() {
  const { t, lang, setLang } = useI18n();
  const { site } = useSite();
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
    if (q.trim()) navigate(`/search?q=${encodeURIComponent(q.trim())}`);
  }

  const logoUrl = logoForTheme(site, isDark);
  const hasFooter = Boolean(site.footer_text) || site.footer_links.length > 0;

  return (
    // flex column so the footer sits at the bottom of a short page instead
    // of floating halfway up it.
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-[var(--border)] bg-[var(--surface)]">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 text-lg font-semibold">
            {/* alt="" -- the name sits right next to it in text, so a screen
                reader announcing the logo too would just say it twice. */}
            {logoUrl && <img src={logoUrl} alt="" className="h-7 w-auto max-w-[10rem] object-contain" />}
            <span>{site.name}</span>
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
          <Button variant="ghost" size="sm" onClick={() => setLang(lang === "de" ? "en" : "de")}>
            {lang === "de" ? "EN" : "DE"}
          </Button>
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
            {site.footer_text && <span>{site.footer_text}</span>}
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
