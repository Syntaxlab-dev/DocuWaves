import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type SiteBranding } from "@/lib/api";
import { applyAccent, applyFavicon } from "@/lib/theme";

/** What the app renders before (and instead of, if the request fails) the
 *  branding arrives -- deliberately identical to what the backend answers
 *  for a content repo with no _site.yml in it, so an unbranded instance
 *  never flashes one set of values and then another. */
const DEFAULT_SITE: SiteBranding = {
  name: "DocuWaves",
  tagline: "",
  logo: "",
  logo_url: null,
  logo_dark: "",
  logo_dark_url: null,
  favicon: "",
  favicon_url: null,
  accent: "",
  footer_text: "",
  footer_links: [],
};

const SiteContext = createContext<{ site: SiteBranding; reload: () => Promise<void> }>({
  site: DEFAULT_SITE,
  reload: async () => {},
});

export function SiteProvider({ children }: { children: ReactNode }) {
  const [site, setSite] = useState<SiteBranding>(DEFAULT_SITE);

  const reload = useCallback(async () => {
    try {
      setSite(await api.publicGetSite());
    } catch {
      // A branding request that fails is not worth an error screen -- the
      // docs themselves load from other endpoints and read perfectly well
      // with the default look.
      setSite(DEFAULT_SITE);
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

  return <SiteContext.Provider value={{ site, reload }}>{children}</SiteContext.Provider>;
}

export function useSite() {
  return useContext(SiteContext);
}

/** `<page title> · <site name>`, or just the site name on the home page
 *  (pass nothing). Called from each view rather than derived from the route
 *  centrally, because only the view knows the real title -- a page's is the
 *  page's own, not something the URL spells out. */
export function useDocumentTitle(pageTitle?: string) {
  const { site } = useSite();
  useEffect(() => {
    document.title = pageTitle ? `${pageTitle} · ${site.name}` : site.name;
  }, [pageTitle, site.name]);
}

/** The logo to render for the current colour scheme: the dark variant only
 *  when one is configured AND the reader is in dark mode, otherwise the
 *  normal logo in both. Null means "no logo" -- the name renders as text. */
export function logoForTheme(site: SiteBranding, isDark: boolean): string | null {
  return isDark && site.logo_dark_url ? site.logo_dark_url : site.logo_url;
}
