import { useEffect, useMemo, useState, type FormEvent } from "react";
import qrcode from "qrcode-generator";
import { toast } from "sonner";
import { KeyRound, ShieldCheck, Smartphone, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CopyButton } from "@/components/CopyButton";
import { api, ApiError, type MfaStatus } from "@/lib/api";
import { createCredential, webauthnSupported } from "@/lib/webauthn";
import { useI18n } from "@/lib/i18n";
import { formatIsoDate } from "@/lib/dates";

/**
 * Two-factor sign-in for the signed-in account: security keys and passkeys
 * (WebAuthn -- a YubiKey, Touch ID, Windows Hello, a phone), an
 * authenticator app, and the recovery codes. What each one is, and what 2FA
 * does not cover (SSO, API tokens), is in backend services/mfa_store.py.
 *
 * Removing anything asks for the password: a session left open on somebody
 * else's screen must not be enough to switch 2FA off. Adding does not, since
 * adding a factor only ever makes the account harder to get into.
 */
export function TwoFactorCard() {
  const { t, lang } = useI18n();
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [keyName, setKeyName] = useState("");
  const [totpSetup, setTotpSetup] = useState<{ secret: string; uri: string } | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.mfaStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  function apply(next: MfaStatus) {
    setStatus(next);
    if (next.recovery_codes) setCodes(next.recovery_codes);
  }

  function fail(err: unknown) {
    toast.error(
      err instanceof ApiError
        ? err.message === "mfa_invalid"
          ? t("mfa.invalid")
          : err.message
        : t("mfa.keyCancelled"),
    );
  }

  function askPassword(): string | null {
    const password = prompt(t("mfa.passwordPrompt"), "");
    return password ? password : null;
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    try {
      await action();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  const onAddKey = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      const options = await api.mfaKeyOptions();
      const credential = await createCredential(options);
      apply(await api.mfaAddKey(keyName || t("mfa.keyDefaultName"), credential));
      setKeyName("");
      toast.success(t("mfa.keyAdded"));
    });
  };

  const onDeleteKey = (id: number, name: string) => {
    if (!confirm(t("mfa.keyDeleteConfirm").replace("{name}", name))) return;
    const password = askPassword();
    if (!password) return;
    void run(async () => apply(await api.mfaDeleteKey(id, password)));
  };

  const onTotpStart = () => void run(async () => setTotpSetup(await api.mfaTotpSetup()));

  const onTotpConfirm = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      apply(await api.mfaTotpConfirm(totpCode));
      setTotpSetup(null);
      setTotpCode("");
      toast.success(t("mfa.totpOn"));
    });
  };

  const onTotpDisable = () => {
    const password = askPassword();
    if (!password) return;
    void run(async () => apply(await api.mfaTotpDisable(password)));
  };

  const onNewCodes = () => {
    if (!confirm(t("mfa.newCodesConfirm"))) return;
    const password = askPassword();
    if (!password) return;
    void run(async () => apply(await api.mfaNewRecoveryCodes(password)));
  };

  const qr = useMemo(() => {
    if (!totpSetup) return null;
    const code = qrcode(0, "M");
    code.addData(totpSetup.uri);
    code.make();
    const count = code.getModuleCount();
    const parts: string[] = [];
    for (let row = 0; row < count; row++) {
      for (let col = 0; col < count; col++) if (code.isDark(row, col)) parts.push(`M${col} ${row}h1v1h-1z`);
    }
    return { d: parts.join(""), size: count };
  }, [totpSetup]);

  if (!status) return null;
  const keysSupported = webauthnSupported();

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-semibold text-[var(--ink)]">
          <ShieldCheck className="h-4 w-4" />
          {t("mfa.title")}
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              status.enabled ? "bg-green-500/15 text-green-700 dark:text-green-400" : "bg-[var(--border)] text-[var(--muted)]"
            }`}
          >
            {status.enabled ? t("mfa.on") : t("mfa.off")}
          </span>
        </CardTitle>
        <p className="text-sm text-[var(--muted)]">{t("mfa.intro")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {codes && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
            <p className="mb-2 font-medium">{t("mfa.codesTitle")}</p>
            <p className="mb-2 text-xs text-[var(--muted)]">{t("mfa.codesHint")}</p>
            <ul className="mb-2 grid max-w-sm grid-cols-2 gap-x-6 gap-y-0.5 font-mono text-sm">
              {codes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
            <div className="flex gap-2">
              <CopyButton getText={() => codes.join("\n")} />
              <Button size="sm" variant="ghost" onClick={() => setCodes(null)}>
                {t("mfa.codesSaved")}
              </Button>
            </div>
          </div>
        )}

        <section className="flex flex-col gap-2">
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <KeyRound className="h-4 w-4" />
            {t("mfa.keysTitle")}
          </h3>
          <p className="text-xs text-[var(--muted)]">{t("mfa.keysHint")}</p>
          {status.keys.length > 0 && (
            <ul className="flex flex-col divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
              {status.keys.map((key) => (
                <li key={key.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                  <span className="font-medium">{key.name}</span>
                  <span className="flex-1 text-xs text-[var(--muted)]">
                    {t("mfa.keyAddedOn").replace("{date}", formatIsoDate(key.created_at.slice(0, 10), lang))}
                    {key.last_used_at &&
                      ` · ${t("mfa.keyUsedOn").replace("{date}", formatIsoDate(key.last_used_at.slice(0, 10), lang))}`}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    aria-label={t("admin.delete")}
                    disabled={busy}
                    onClick={() => onDeleteKey(key.id, key.name)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {keysSupported ? (
            <form onSubmit={onAddKey} className="flex flex-wrap items-end gap-2">
              <Input
                className="max-w-xs flex-1"
                value={keyName}
                onChange={(e) => setKeyName(e.target.value)}
                placeholder={t("mfa.keyNamePlaceholder")}
                aria-label={t("mfa.keyName")}
                maxLength={60}
              />
              <Button type="submit" variant="outline" disabled={busy}>
                {t("mfa.addKey")}
              </Button>
            </form>
          ) : (
            <p className="text-xs text-[var(--muted)]">{t("mfa.keysUnsupported")}</p>
          )}
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <Smartphone className="h-4 w-4" />
            {t("mfa.totpTitle")}
          </h3>
          {status.totp ? (
            <div className="flex items-center gap-2 text-sm">
              <span className="flex-1">{t("mfa.totpActive")}</span>
              <Button variant="outline" size="sm" disabled={busy} onClick={onTotpDisable}>
                {t("mfa.totpRemove")}
              </Button>
            </div>
          ) : totpSetup && qr ? (
            <form onSubmit={onTotpConfirm} className="flex flex-col gap-3 sm:flex-row sm:items-start">
              <svg
                viewBox={`-2 -2 ${qr.size + 4} ${qr.size + 4}`}
                className="h-40 w-40 shrink-0 rounded-lg bg-white"
                role="img"
                aria-label={t("mfa.qrLabel")}
                shapeRendering="crispEdges"
              >
                <path d={qr.d} fill="#000" />
              </svg>
              <div className="flex flex-1 flex-col gap-2 text-sm">
                <p className="text-xs text-[var(--muted)]">{t("mfa.totpScan")}</p>
                <code className="break-all rounded bg-[var(--border)] px-2 py-1 text-xs">{totpSetup.secret}</code>
                <Input
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value)}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="123456"
                  aria-label={t("mfa.ask.totp")}
                  required
                />
                <div className="flex gap-2">
                  <Button type="submit" disabled={busy}>
                    {t("mfa.totpConfirm")}
                  </Button>
                  <Button type="button" variant="ghost" onClick={() => setTotpSetup(null)}>
                    {t("admin.cancel")}
                  </Button>
                </div>
              </div>
            </form>
          ) : (
            <div className="flex items-center gap-2 text-sm">
              <span className="flex-1 text-xs text-[var(--muted)]">{t("mfa.totpHint")}</span>
              <Button variant="outline" size="sm" disabled={busy} onClick={onTotpStart}>
                {t("mfa.totpSetup")}
              </Button>
            </div>
          )}
        </section>

        {status.enabled && (
          <section className="flex items-center gap-2 text-sm">
            <span className="flex-1">
              {t("mfa.codesLeft").replace("{n}", String(status.recovery_codes_left))}
            </span>
            <Button variant="outline" size="sm" disabled={busy} onClick={onNewCodes}>
              {t("mfa.newCodes")}
            </Button>
          </section>
        )}

        <p className="text-xs text-[var(--muted)]">{t("mfa.ssoNote")}</p>
      </CardContent>
    </Card>
  );
}
