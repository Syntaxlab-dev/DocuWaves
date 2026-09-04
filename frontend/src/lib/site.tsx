import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type SiteBranding } from "@/lib/api";
import { useContentLang } from "@/lib/lang";
import { applyAccent, applyFavicon } from "@/lib/theme";

/** What the app renders before (and instead of, if the request fails) the
 *  branding arrives -- deliberately identical to what the backend answers
 *  for a content repo with no _site.yml in it, so an unbranded instance
 *  never flashes one set of values and then another. */
const DEFAULT_SITE: SiteBranding = {
  // No languages until the real branding says otherwise: the language
  // prefix and switcher are decided from this, so guessing here would flash
  // a switcher onto a single-language instance for one render.
  languages: [],
  default_language: "",
  name: "DocuWaves",
  name_i18n: {},
  tagline: "",
  tagline_i18n: {},
  footer_text_i18n: {},
  logo: "",
  logo_url: null,
  logo_dark: "",
  logo_dark_url: null,
  favicon: "",
  favicon_url: null,
  accent: "",
  footer_text: "",
  footer_links: [],
  // Nothing measured until the real branding says otherwise. Nothing in the
  // browser acts on this anyway -- the tag is written server-side (the
  // backend's seo.render_analytics); the admin form is its only reader here.
  analytics: {},
};

/** `ready` is false until the first branding response has landed (either
 *  way -- a failed request still counts as answered). Nothing renders
 *  differently for it, but the language routing does have to wait: the
 *  configured languages decide whether an unprefixed URL should redirect,
 *  and redirecting before they are known would send a reader of a
 *  multilingual site to the wrong place. */
const SiteContext = createContext<{ site: SiteBranding; ready: boolean; reload: () => Promise<void> }>({
  site: DEFAULT_SITE,
  ready: false,
  reload: async () => {},
});

export function SiteProvider({ children }: { children: ReactNode }) {
  const [site, setSite] = useState<SiteBranding>(DEFAULT_SITE);
  const [ready, setReady] = useState(false);

  const reload = useCallback(async () => {
    try {
      setSite(await api.publicGetSite());
    } catch {
      // A branding request that fails is not worth an error screen -- the
      // docs themselves load from other endpoints and read perfectly well
      // with the default look.
      setSite(DEFAULT_SITE);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Applied here rather than in each consumer: both are document-level side
  // effects (an inline style on <html>, the <link rel="icon"> in <head>), so
  // there is exactly one writer for each and re-saving in the admin form
  // updates the live page through the same path as the first load.
  useEffect(() => {
    applyAccent(site.accent);
  }, [site.accent]);

  useEffect(() => {
    applyFavicon(site.favicon_url);
  }, [site.favicon_url]);

  return <SiteContext.Provider value={{ site, ready, reload }}>{children}</SiteContext.Provider>;
}

export function useSite() {
  return useContext(SiteContext);
}

/** A branding text in the content language being read: the per-language
 *  value when this instance has one, the configured value otherwise. The
 *  whole mapping is in the one branding response (see the backend's
 *  read_branding), so switching language never refetches it. */
export function siteText(site: SiteBranding, field: "name" | "tagline" | "footer_text", lang: string): string {
  const mapping = field === "name" ? site.name_i18n : field === "tagline" ? site.tagline_i18n : site.footer_text_i18n;
  return (lang && mapping[lang]) || site[field];
}

/** `<page title> · <site name>`, or just the site name on the home page
 *  (pass nothing). Called from each view rather than derived from the route
 *  centrally, because only the view knows the real title -- a page's is the
 *  page's own, not something the URL spells out. */
export function useDocumentTitle(pageTitle?: string) {
  const { site } = useSite();
  // The site name in the content language being read, when this instance
  // translates it -- the tab is part of the page, so it says the same thing
  // the header does.
  const { lang } = useContentLang();
  const name = siteText(site, "name", lang);
  useEffect(() => {
    document.title = pageTitle ? `${pageTitle} · ${name}` : name;
  }, [pageTitle, name]);
}

/** The logo to render for the current colour scheme: the dark variant only
 *  when one is configured AND the reader is in dark mode, otherwise the
 *  normal logo in both. Null means "no logo" -- the name renders as text. */
export function logoForTheme(site: SiteBranding, isDark: boolean): string | null {
  return isDark && site.logo_dark_url ? site.logo_dark_url : site.logo_url;
}
