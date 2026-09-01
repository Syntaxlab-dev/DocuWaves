import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/lib/auth";
import { I18nProvider } from "@/lib/i18n";
import { SiteProvider } from "@/lib/site";
import { PublicLayout } from "@/pages/PublicLayout";
import { PublicHome } from "@/pages/PublicHome";
import { PublicProject } from "@/pages/PublicProject";
import { PublicCategory } from "@/pages/PublicCategory";
import { PublicPage } from "@/pages/PublicPage";
import { SearchResults } from "@/pages/SearchResults";
import { AdminGate } from "@/pages/AdminGate";
import { NotFound } from "@/components/NotFound";

export default function App() {
  return (
    <I18nProvider>
      {/* Outside the router: the branding (accent colour, favicon, tab
          title) is the same on every route, admin included, so it's fetched
          once for the whole app rather than per view. */}
      <SiteProvider>
        <AuthProvider>
          <BrowserRouter>
            <Toaster richColors position="top-right" />
            <Routes>
              <Route path="/admin/*" element={<AdminGate />} />
              <Route element={<PublicLayout />}>
                <Route path="/" element={<PublicHome />} />
                <Route path="/search" element={<SearchResults />} />
                <Route path="/p/:projectSlug" element={<PublicProject />} />
                <Route path="/p/:projectSlug/c/:categorySlug" element={<PublicCategory />} />
                <Route path="/p/:projectSlug/pages/:pageSlug" element={<PublicPage />} />
                {/* Inside the layout, so a wrong URL still has the header's
                    search box and home link to get out with. */}
                <Route path="*" element={<NotFound />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </SiteProvider>
    </I18nProvider>
  );
}
