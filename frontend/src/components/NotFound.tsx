import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { api, type SearchResult } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { useDocumentTitle, useSite } from "@/lib/site";
import { useAuth } from "@/lib/auth";

/**
 * Reached two ways: a URL matching no route at all (App.tsx's catch-all),
 * and a route whose project/category/page slug the API answers 404 for.
 * A slug that doesn't resolve is far more often a page that was renamed or
 * is still a draft than a typo, so the copy says that rather than blaming
 * the reader -- and the search box in the header above is the actual way
 * out, with the homepage link as the fallback.
 *
 * Two more ways out on the page itself: a search field, and "maybe you
 * meant" -- the address's last segment read as words and searched for
 * ("instaling-the-widget" finds "Installing the widget", the search
 * corrects the spelling). Nothing is shown when that finds nothing.
 */

/** "/p/handbook/pages/instaling-the-widget" -> "instaling the widget". */
export function wordsFromPath(pathname: string): string {
  const last = decodeURIComponent(pathname.split("/").filter(Boolean).pop() ?? "");
  return last
    .replace(/\.[a-z0-9]+$/i, "")
    .replace(/[-_+.]+/g, " ")
    .trim();
}
export function NotFound() {
  const { t } = useI18n();
  const { path } = useContentLang();
  const { site } = useSite();
  const { status } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { lang } = useContentLang();
  const [q, setQ] = useState("");
  const [similar, setSimilar] = useState<SearchResult[]>([]);
  useDocumentTitle(t("notFound.title"));

  const guess = wordsFromPath(location.pathname);
  useEffect(() => {
    setSimilar([]);
    if (guess.length < 3) return;
    let current = true;
    // All the words first; failing that, each longer word alone, longest
    // first -- a renamed page usually keeps one of its main words, and a
    // misspelled one may simply find nothing.
    const tries = [guess, ...guess.split(" ").filter((w) => w.length >= 4 && w !== guess).sort((a, b) => b.length - a.length)];
    (async () => {
      for (const words of tries.slice(0, 4)) {
        const r = await api.search(words, lang);
        if (r.results.length) return r.results;
      }
      return [];
    })()
      .then((results) => current && setSimilar(results.slice(0, 5)))
      .catch(() => {});
    return () => {
      current = false;
    };
  }, [guess, lang]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    if (q.trim()) navigate(path(`/search?q=${encodeURIComponent(q.trim())}`));
  }
  // Somebody who was sent a link into a private project lands here when not
  // signed in. Offered only where the header already offers sign-in (the
  // instance has private projects at all), so it says nothing new -- and
  // the same for every 404, so it says nothing about THIS address either.
  const offerSignIn = site.sign_in && !status?.authenticated;
  const next = encodeURIComponent(location.pathname + location.search);
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="py-12 text-center">
        <div className="text-5xl font-semibold text-[var(--muted)]">404</div>
        <h1 className="mt-4 text-2xl font-semibold">{t("notFound.title")}</h1>
        <p className="mx-auto mt-2 max-w-md text-[var(--muted)]">{t("notFound.body")}</p>
        <form onSubmit={onSearch} role="search" className="mx-auto mt-6 max-w-md">
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted)]"
              aria-hidden="true"
            />
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("home.searchPlaceholder")}
              aria-label={t("home.searchPlaceholder")}
              className="h-11 w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] pl-10 pr-3 outline-none transition focus:border-[var(--accent)] focus:ring-4 focus:ring-[var(--accent-soft)]"
            />
          </div>
        </form>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <Button asChild>
            <Link to={path("/")}>{t("notFound.home")}</Link>
          </Button>
          {offerSignIn && (
            <Button asChild variant="outline">
              <Link to={path(`/login?next=${next}`)}>{t("auth.signIn")}</Link>
            </Button>
          )}
        </div>
        {offerSignIn && <p className="mx-auto mt-3 max-w-md text-sm text-[var(--muted)]">{t("notFound.signInHint")}</p>}
      </div>
      {similar.length > 0 && (
        <section className="mx-auto max-w-md">
          <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">{t("notFound.similar")}</h2>
          <ul className="mt-3 divide-y divide-[var(--border)] rounded-xl border border-[var(--border)] bg-[var(--surface)]">
            {similar.map((hit) => (
              <li key={`${hit.project_slug}/${hit.page_slug}/${hit.language}`}>
                <Link
                  to={path(`/p/${hit.project_slug}/pages/${hit.page_slug}`)}
                  className="block px-4 py-3 hover:bg-[var(--surface-2)]"
                >
                  <span className="font-medium">{hit.title}</span>
                  <span className="block text-xs text-[var(--muted)]">
                    {hit.project_name} › {hit.category_name}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
