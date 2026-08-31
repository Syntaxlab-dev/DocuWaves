import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { Login } from "@/pages/Login";
import { AdminApp } from "@/pages/AdminApp";

export function AdminGate() {
  const { status, loading } = useAuth();
  const { t } = useI18n();

  if (loading || status === null) return <div className="p-8 text-[var(--muted)]">{t("common.loading")}</div>;
  if (!status.authenticated) return <Login setupRequired={status.setup_required} />;
  return <AdminApp />;
}
