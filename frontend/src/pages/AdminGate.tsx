import { lazy, Suspense } from "react";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { Login } from "@/pages/Login";
import { ReaderNotice } from "@/pages/ReaderNotice";

// The admin area is most of the app's code, and a reader never opens it: it
// is its own chunk, fetched the first time somebody signs in.
const AdminApp = lazy(() => import("@/pages/AdminApp").then((m) => ({ default: m.AdminApp })));

export function AdminGate() {
  const { status, loading } = useAuth();
  const { t } = useI18n();

  if (loading || status === null) return <div className="p-8 text-[var(--muted)]">{t("common.loading")}</div>;
  if (!status.authenticated) return <Login setupRequired={status.setup_required} setupTokenRequired={status.setup_token_required} />;
  // A reader account reads private projects on the docs site; the admin API
  // refuses it outright, so it gets an explanation instead of a broken UI.
  if (status.role === "reader") return <ReaderNotice username={status.username ?? ""} />;
  return (
    <Suspense fallback={<div className="p-8 text-[var(--muted)]">{t("common.loading")}</div>}>
      <AdminApp />
    </Suspense>
  );
}
