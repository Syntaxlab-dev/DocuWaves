import { Link, useLocation } from "react-router-dom";
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
 */
export function NotFound() {
  const { t } = useI18n();
  const { path } = useContentLang();
  const { site } = useSite();
  const { status } = useAuth();
  const location = useLocation();
  useDocumentTitle(t("notFound.title"));
  // Somebody who was sent a link into a private project lands here when not
  // signed in. Offered only where the header already offers sign-in (the
  // instance has private projects at all), so it says nothing new -- and
  // the same for every 404, so it says nothing about THIS address either.
  const offerSignIn = site.sign_in && !status?.authenticated;
  const next = encodeURIComponent(location.pathname + location.search);
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="py-16 text-center">
        <div className="text-5xl font-semibold text-[var(--muted)]">404</div>
        <h1 className="mt-4 text-2xl font-semibold">{t("notFound.title")}</h1>
        <p className="mx-auto mt-2 max-w-md text-[var(--muted)]">{t("notFound.body")}</p>
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
    </div>
  );
}
