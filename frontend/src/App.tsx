import { BrowserRouter, Routes, Route, Outlet, useParams } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/lib/auth";
import { I18nProvider } from "@/lib/i18n";
import { ContentLangProvider, useContentLang } from "@/lib/lang";
import { SiteProvider, useSite } from "@/lib/site";
import { PublicLayout } from "@/pages/PublicLayout";
import { PublicHome } from "@/pages/PublicHome";
import { PublicProject } from "@/pages/PublicProject";
import { PublicCategory } from "@/pages/PublicCategory";
import { PublicPage } from "@/pages/PublicPage";
import { SearchResults } from "@/pages/SearchResults";
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
 */
const readingRoutes = [
  { path: "", element: <PublicHome /> },
  { path: "search", element: <SearchResults /> },
  { path: "p/:projectSlug", element: <PublicProject /> },
  { path: "p/:projectSlug/c/:categorySlug", element: <PublicCategory /> },
  { path: "p/:projectSlug/pages/:pageSlug", element: <PublicPage /> },
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
        <Route element={<PublicLayout />}>
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
