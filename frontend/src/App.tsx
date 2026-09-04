import { BrowserRouter, Routes, Route, Outlet, useParams } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/lib/auth";
import { I18nProvider } from "@/lib/i18n";
import { ContentLangProvider, useContentLang } from "@/lib/lang";
import { ProjectVersionProvider } from "@/lib/version";
import { SiteProvider, useSite } from "@/lib/site";
import { PublicLayout } from "@/pages/PublicLayout";
import { PublicHome } from "@/pages/PublicHome";
import { PublicProject } from "@/pages/PublicProject";
import { PublicCategory } from "@/pages/PublicCategory";
import { PublicPage } from "@/pages/PublicPage";
import { SearchResults } from "@/pages/SearchResults";
import { PreviewPage } from "@/pages/PreviewPage";
import { AdminGate } from "@/pages/AdminGate";
import { NotFound } from "@/components/NotFound";

/**
 * Every reading route exists twice: once unprefixed (`/p/x`) and once under
 * a content language (`/de/p/x`). Both render the same view -- which
 * language it serves comes from lib/lang.tsx, not from the component.
 *
 * The unprefixed set is not a legacy leftover: it IS the whole set on a
 * single-language instance (no prefix is ever added there), and on a
 * multilingual one it keeps every link that was ever shared working, by
 * redirecting to the default language (ContentLangProvider). Written as one
 * list rendered twice so the two can't drift apart.
 *
 * The same is true one level down for documentation VERSIONS: a project's
 * three reading routes exist with and without a `:version` segment, and the
 * version-less ones are what an unversioned project (and every project's
 * DEFAULT version) uses -- so no link ever breaks when a project starts
 * versioning. The two shapes can't collide: the version-less routes all
 * have a fixed segment (`c`, `pages`) exactly where the versioned ones have
 * `:version`, and react-router ranks a literal segment above a dynamic one.
 * `c` and `pages` are refused as version ids on the backend for that reason
 * (see content_versions._RESERVED_IDS).
 */
const readingRoutes = [
  { path: "", element: <PublicHome /> },
  { path: "search", element: <SearchResults /> },
  { path: "p/:projectSlug", element: <PublicProject /> },
  { path: "p/:projectSlug/c/:categorySlug", element: <PublicCategory /> },
  { path: "p/:projectSlug/pages/:pageSlug", element: <PublicPage /> },
  { path: "p/:projectSlug/:version", element: <PublicProject /> },
  { path: "p/:projectSlug/:version/c/:categorySlug", element: <PublicCategory /> },
  { path: "p/:projectSlug/:version/pages/:pageSlug", element: <PublicPage /> },
];

function readingRouteElements(keyPrefix: string) {
  return readingRoutes.map(({ path, element }) =>
    path === "" ? (
      <Route key={`${keyPrefix}-index`} index element={element} />
    ) : (
      <Route key={`${keyPrefix}-${path}`} path={path} element={element} />
    ),
  );
}

/**
 * The parent of every `/:lang/...` route: it answers what only a matched
 * route can, namely whether that first segment was meant as a language.
 * `/xx/p/foo` on an instance that has no `xx` is a wrong URL, not a reason
 * to quietly serve the default language -- and on a single-language
 * instance `/de/p/foo` is a wrong URL for exactly the same reason.
 */
function LanguageGate() {
  const { languages, multilingual, ready } = useContentLang();
  const { lang } = useParams<{ lang: string }>();
  // Until the branding has answered, nothing is known about the configured
  // languages -- rendering a 404 now would flash one on every prefixed URL.
  if (!ready) return null;
  if (!multilingual || !lang || !languages.includes(lang)) return <NotFound />;
  return <Outlet />;
}

/** Reads the branding the language machinery needs and hands it down. Kept
 *  separate from SiteProvider because the provider below has to sit INSIDE
 *  the router (it reads the URL and can redirect), while the branding is
 *  fetched once for the whole app, admin included. */
function LanguageRouting() {
  const { site, ready } = useSite();
  return (
    <ContentLangProvider languages={site.languages} defaultLanguage={site.default_language} ready={ready}>
      <Routes>
        <Route path="/admin/*" element={<AdminGate />} />
        {/* Outside PublicLayout on purpose: a preview link gives its holder
            ONE page, and the layout's search box, sidebar and home link are
            all ways out of it into an instance they were not given. The
            literal first segment also keeps it clear of the `:lang` route
            below -- react-router ranks a literal above a dynamic segment,
            and `preview` is not a language code on any instance. */}
        <Route path="/preview/:token" element={<PreviewPage />} />
        {/* Inside the layout route's element, so the header's version
            switcher and the docs views below it share one context -- the
            views report which version they loaded, the header renders the
            switcher for it. */}
        <Route element={<ProjectVersionProvider><PublicLayout /></ProjectVersionProvider>}>
          {readingRouteElements("plain")}
          <Route path=":lang" element={<LanguageGate />}>
            {readingRouteElements("lang")}
          </Route>
          {/* Inside the layout, so a wrong URL still has the header's
              search box and home link to get out with. */}
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </ContentLangProvider>
  );
}

export default function App() {
  return (
    <I18nProvider>
      {/* Outside the router: the branding (accent colour, favicon, tab
          title, and the content-language list) is the same on every route,
          admin included, so it's fetched once for the whole app rather than
          per view. */}
      <SiteProvider>
        <AuthProvider>
          <BrowserRouter>
            <Toaster richColors position="top-right" />
            <LanguageRouting />
          </BrowserRouter>
        </AuthProvider>
      </SiteProvider>
    </I18nProvider>
  );
}
