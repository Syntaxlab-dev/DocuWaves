import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { KeyRound, LogIn } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { api, ApiError, type MfaMethod, type OidcStatus } from "@/lib/api";
import { getAssertion, webauthnSupported } from "@/lib/webauthn";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { logoForTheme, siteText, useSite } from "@/lib/site";
import { useIsDarkTheme } from "@/lib/theme";

export function Login({
  setupRequired,
  setupTokenRequired = false,
  next,
  embedded = false,
}: {
  setupRequired: boolean;
  /** The setup screen asks for the installer's setup code. */
  setupTokenRequired?: boolean;
  /** Where to go once signed in -- set by the public /login page, so a
   *  reader who signed in from a private project's page lands back on it.
   *  Already checked to be a path on this site (see PublicLogin). */
  next?: string;
  /** Inside the public layout rather than a screen of its own. */
  embedded?: boolean;
}) {
  const { t, lang } = useI18n();
  const { refresh } = useAuth();
  const { site } = useSite();
  const isDark = useIsDarkTheme();
  const navigate = useNavigate();
  // A demo instance fills in its own login: it is shown to everybody anyway.
  const demo = site.demo?.enabled && !setupRequired ? site.demo : null;
  const [username, setUsername] = useState(demo?.username ?? "");
  const [password, setPassword] = useState(demo?.password ?? "");
  const [setupToken, setSetupToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [oidcStatus, setOidcStatus] = useState<OidcStatus | null>(null);
  // The second step: set once the password was right and the account has
  // two-factor sign-in. `mfaMode` is the factor being asked for right now.
  const [mfaMethods, setMfaMethods] = useState<MfaMethod[] | null>(null);
  const [mfaMode, setMfaMode] = useState<MfaMethod>("webauthn");
  const [code, setCode] = useState("");

  useEffect(() => {
    api.oidcStatus().then(setOidcStatus).catch(() => setOidcStatus(null));

    const params = new URLSearchParams(window.location.search);
    const result = params.get("oidc_login");
    if (result === "failed" || result === "no_account" || result === "setup_token") {
      toast.error(
        result === "no_account"
          ? t("login.oidcNoAccount")
          : result === "setup_token"
            ? t("login.oidcSetupToken")
            : t("login.oidcFailed"),
      );
      window.history.replaceState({}, "", "/admin");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      if (setupRequired) {
        await api.setup(username, password, setupToken);
      } else {
        const result = await api.login(username, password);
        if (!result.ok && result.mfa_required) {
          const usable = result.methods.filter((m) => m !== "webauthn" || webauthnSupported());
          setMfaMethods(usable);
          setMfaMode(usable[0] ?? "recovery");
          setCode("");
          return;
        }
      }
      await finish();
    } catch (err) {
      toast.error(
        err instanceof ApiError
          ? err.message === "setup_token_invalid"
            ? t("setup.tokenInvalid")
            : err.message
          : t("login.failed"),
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function finish() {
    setMfaMethods(null);
    await refresh();
    if (next) navigate(next, { replace: true });
  }

  function mfaError(err: unknown) {
    if (err instanceof ApiError && err.message === "mfa_login_expired") {
      toast.error(t("mfa.loginExpired"));
      setMfaMethods(null);
      setPassword("");
      return;
    }
    toast.error(
      err instanceof ApiError
        ? err.message === "mfa_invalid"
          ? t("mfa.invalid")
          : err.message
        : t("mfa.keyCancelled"),
    );
  }

  async function onKey() {
    setSubmitting(true);
    try {
      const options = await api.mfaLoginKeyOptions();
      const credential = await getAssertion(options);
      await api.mfaLoginKey(credential);
      await finish();
    } catch (err) {
      mfaError(err);
    } finally {
      setSubmitting(false);
    }
  }

  async function onCode(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      if (mfaMode === "recovery") {
        const { recovery_codes_left } = await api.mfaLoginRecovery(code);
        toast.warning(t("mfa.recoveryUsed").replace("{n}", String(recovery_codes_left)));
      } else {
        await api.mfaLoginTotp(code);
      }
      await finish();
    } catch (err) {
      mfaError(err);
    } finally {
      setSubmitting(false);
    }
  }

  const otherMethods = (mfaMethods ?? []).filter((m) => m !== mfaMode);

  return (
    <div
      className={
        embedded
          ? "flex items-center justify-center px-4 py-16"
          : "auth-screen flex min-h-screen flex-col items-center justify-center gap-6 px-4 py-10"
      }
    >
      {/* On a screen of its own, the instance says whose it is: its logo
          and name above the form, on the same soft accent wash as the home
          page. Inside the public layout the header above already does. */}
      {!embedded && (
        <div className="flex flex-col items-center gap-3 text-center">
          {logoForTheme(site, isDark) ? (
            <img src={logoForTheme(site, isDark)!} alt="" className="h-12 w-auto max-w-[14rem] object-contain" />
          ) : null}
          <div className="text-xl font-semibold tracking-tight">{siteText(site, "name", lang)}</div>
        </div>
      )}
      <Card className="w-full max-w-sm shadow-xl">
        <CardHeader>
          <CardTitle className="text-lg font-semibold text-[var(--ink)]">
            {setupRequired ? t("setup.title") : t("login.title")}
          </CardTitle>
          {setupRequired && <p className="text-sm text-[var(--muted)]">{t("setup.subtitle")}</p>}
        </CardHeader>
        <CardContent>
          {mfaMethods ? (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-[var(--muted)]">{t(`mfa.ask.${mfaMode}` as never)}</p>
              {mfaMode === "webauthn" ? (
                <Button type="button" className="w-full" disabled={submitting} onClick={() => void onKey()} autoFocus>
                  <KeyRound className="h-4 w-4" />
                  {t("mfa.useKey")}
                </Button>
              ) : (
                <form onSubmit={onCode} className="flex flex-col gap-3">
                  <Input
                    id="mfa-code"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    autoComplete="one-time-code"
                    inputMode={mfaMode === "totp" ? "numeric" : "text"}
                    spellCheck={false}
                    placeholder={mfaMode === "totp" ? "123456" : "abcde-fghij"}
                    aria-label={t(`mfa.ask.${mfaMode}` as never)}
                    required
                    autoFocus
                  />
                  <Button type="submit" className="w-full" disabled={submitting}>
                    {t("mfa.verify")}
                  </Button>
                </form>
              )}
              {otherMethods.length > 0 && (
                <div className="flex flex-col gap-1 text-xs">
                  {otherMethods.map((m) => (
                    <button
                      key={m}
                      type="button"
                      className="text-left text-[var(--accent)] hover:underline"
                      onClick={() => {
                        setMfaMode(m);
                        setCode("");
                      }}
                    >
                      {t(`mfa.switch.${m}` as never)}
                    </button>
                  ))}
                </div>
              )}
              <button
                type="button"
                className="text-left text-xs text-[var(--muted)] hover:underline"
                onClick={() => {
                  setMfaMethods(null);
                  setPassword("");
                }}
              >
                {t("common.back")}
              </button>
            </div>
          ) : (
          <form onSubmit={onSubmit} className="flex flex-col gap-3">
            {demo && (
              <p className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm">
                {t("demo.login")
                  .replace("{username}", demo.username ?? "")
                  .replace("{password}", demo.password ?? "")}
              </p>
            )}
            {setupRequired && setupTokenRequired && (
              <div className="flex flex-col gap-1.5">
                <label htmlFor="setup-token" className="text-sm font-medium">
                  {t("setup.token")}
                </label>
                <Input
                  id="setup-token"
                  value={setupToken}
                  onChange={(e) => setSetupToken(e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  required
                  autoFocus
                />
                <p className="text-xs text-[var(--muted)]">{t("setup.tokenHint")}</p>
              </div>
            )}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="username" className="text-sm font-medium">
                {setupRequired ? t("setup.username") : t("login.username")}
              </label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus={!(setupRequired && setupTokenRequired)}
              />
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
          )}

          {oidcStatus?.enabled && !mfaMethods && (
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
                onClick={() =>
                  (window.location.href = next
                    ? `/api/auth/oidc/login?next=${encodeURIComponent(next)}`
                    : "/api/auth/oidc/login")
                }
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
