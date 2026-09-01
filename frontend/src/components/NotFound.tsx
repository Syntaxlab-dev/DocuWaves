import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { useDocumentTitle } from "@/lib/site";

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
  useDocumentTitle(t("notFound.title"));
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="py-16 text-center">
        <div className="text-5xl font-semibold text-[var(--muted)]">404</div>
        <h1 className="mt-4 text-2xl font-semibold">{t("notFound.title")}</h1>
        <p className="mx-auto mt-2 max-w-md text-[var(--muted)]">{t("notFound.body")}</p>
        <Button asChild className="mt-6">
          <Link to={path("/")}>{t("notFound.home")}</Link>
        </Button>
      </div>
    </div>
  );
}
