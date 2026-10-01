import { Navigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { useDocumentTitle } from "@/lib/site";
import { Login } from "@/pages/Login";

/** A path on this site, or "/" -- the same rule the backend applies to the
 *  SSO return address (routers/auth.py safe_next), so a crafted
 *  `/login?next=https://elsewhere` cannot send anybody away. */
export function safeNext(target: string | null): string {
  if (!target || !target.startsWith("/") || target.startsWith("//") || /[\\\r\n]/.test(target)) return "/";
  return target.slice(0, 500);
}

/**
 * Signing in from the docs site, for reading private projects (backend
 * services/visibility.py). The same form as the admin area's -- one place to
 * get right -- inside the public layout, and back to where the reader came
 * from afterwards.
 */
export function PublicLogin() {
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const { status, loading } = useAuth();
  const { t } = useI18n();
  useDocumentTitle(t("login.title"));

  if (loading) return null;
  if (status?.authenticated) return <Navigate to={next} replace />;
  return <Login setupRequired={false} next={next} embedded />;
}
