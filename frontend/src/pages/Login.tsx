import { useEffect, useState, type FormEvent } from "react";
import { LogIn } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { api, ApiError, type OidcStatus } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

export function Login({ setupRequired }: { setupRequired: boolean }) {
  const { t } = useI18n();
  const { refresh } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [oidcStatus, setOidcStatus] = useState<OidcStatus | null>(null);

  useEffect(() => {
    api.oidcStatus().then(setOidcStatus).catch(() => setOidcStatus(null));

    const params = new URLSearchParams(window.location.search);
    const result = params.get("oidc_login");
    if (result === "failed" || result === "no_account") {
      toast.error(result === "no_account" ? t("login.oidcNoAccount") : t("login.oidcFailed"));
      window.history.replaceState({}, "", "/admin");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      if (setupRequired) {
        await api.setup(username, password);
      } else {
        await api.login(username, password);
      }
      await refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("login.failed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--bg)] px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-lg font-semibold text-[var(--ink)]">
            {setupRequired ? t("setup.title") : t("login.title")}
          </CardTitle>
          {setupRequired && <p className="text-sm text-[var(--muted)]">{t("setup.subtitle")}</p>}
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="username" className="text-sm font-medium">
                {setupRequired ? t("setup.username") : t("login.username")}
              </label>
              <Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="password" className="text-sm font-medium">
                {setupRequired ? t("setup.password") : t("login.password")}
              </label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={setupRequired ? 8 : undefined}
                required
              />
            </div>
            <Button type="submit" className="mt-2 w-full" disabled={submitting}>
              {setupRequired ? t("setup.submit") : t("login.submit")}
            </Button>
          </form>

          {oidcStatus?.enabled && (
            <>
              <div className="my-4 flex items-center gap-3 text-xs text-[var(--muted)]">
                <div className="h-px flex-1 bg-[var(--border)]" />
                {t("login.orDivider")}
                <div className="h-px flex-1 bg-[var(--border)]" />
              </div>
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={() => (window.location.href = "/api/auth/oidc/login")}
              >
                <LogIn className="h-4 w-4" />
                {t("login.oidcPrefix")}
                {oidcStatus.provider_name}
                {t("login.oidcSuffix")}
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
