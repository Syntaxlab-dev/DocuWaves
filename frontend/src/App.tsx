import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/lib/auth";
import { I18nProvider } from "@/lib/i18n";
import { PublicLayout } from "@/pages/PublicLayout";
import { PublicHome } from "@/pages/PublicHome";
import { PublicProject } from "@/pages/PublicProject";
import { PublicCategory } from "@/pages/PublicCategory";
import { PublicPage } from "@/pages/PublicPage";
import { SearchResults } from "@/pages/SearchResults";
import { AdminGate } from "@/pages/AdminGate";

export default function App() {
  return (
    <I18nProvider>
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
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  );
}
