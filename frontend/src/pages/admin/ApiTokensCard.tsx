// API tokens for AI assistants and scripts (the MCP endpoint).
// Split out of pages/AdminApp.tsx, which keeps the layout and state.
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { AlertTriangle, Copy, KeyRound, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError, type ApiToken, type Project } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { askConfirm } from "@/components/ConfirmDialog";
import { SkeletonLines } from "@/components/Skeleton";

/**
 * API tokens -- the credentials an operator hands to an AI assistant so it
 * can read (and, with a write token, edit) these docs through the MCP
 * endpoint at /api/mcp.
 *
 * Two things this panel has to get across, because getting them wrong is
 * expensive in a way nothing else in the admin area is:
 *
 * 1. THE VALUE IS SHOWN ONCE. Only a SHA-256 hash is stored, so there is no
 *    "show token" button anywhere and there never will be. The reveal box
 *    below therefore states that outright, sits there until it is dismissed
 *    (rather than auto-hiding on the next render), and is the only place a
 *    token value ever appears in this UI.
 * 2. A WRITE TOKEN CHANGES THE DOCUMENTATION. Not "has elevated
 *    permissions" -- it means whoever holds it can rewrite a published
 *    page. The warning next to the scope selector says exactly that, in
 *    those words, and appears the moment "read and write" is picked rather
 *    than being a paragraph above the form nobody reads.
 */
export function ApiTokensCard({ projects, onClose }: { projects: Project[]; onClose: () => void }) {
  const { t } = useI18n();
  const [tokens, setTokens] = useState<ApiToken[] | null>(null);
  const [name, setName] = useState("");
  const [scope, setScope] = useState("read");
  // A sync token is for exactly one project (backend services/docs_sync.py).
  const [syncProject, setSyncProject] = useState(projects[0]?.slug ?? "");
  const [expiresAt, setExpiresAt] = useState("");
  const [creating, setCreating] = useState(false);
  /** The plaintext of the token just created. Held in component state and
   *  nowhere else -- closing this panel or reloading the page loses it, as
   *  it must, because the server cannot produce it again. */
  const [revealed, setRevealed] = useState<{ name: string; token: string } | null>(null);

  function load() {
    api
      .adminListTokens()
      .then((r) => setTokens(r.tokens))
      .catch((err) => toast.error(err instanceof ApiError ? err.message : t("common.error")));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      const created = await api.adminCreateToken(name.trim(), scope, expiresAt, scope === "sync" ? syncProject : "");
      setRevealed({ name: created.name, token: created.token });
      setName("");
      setExpiresAt("");
      toast.success(t("admin.tokenCreated"));
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setCreating(false);
    }
  }

  async function onRevoke(token: ApiToken) {
    if (!(await askConfirm({ title: t("admin.tokenRevokeConfirm").replace("{name}", token.name), danger: true }))) return;
    try {
      await api.adminRevokeToken(token.id);
      toast.success(t("admin.tokenRevoked"));
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    }
  }

  async function onCopy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(t("admin.tokenCopied"));
    } catch {
      // Clipboard access needs a secure context; a LAN install served over
      // plain http has none. Say so rather than failing silently -- the
      // value is right there to select by hand.
      toast.error(t("admin.tokenCopyFailed"));
    }
  }

  const endpointUrl = `${window.location.origin}/api/mcp`;

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-semibold text-[var(--ink)]">
          <KeyRound className="h-4 w-4" aria-hidden="true" />
          {t("admin.tokens")}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-[var(--muted)]">{t("admin.tokensIntro")}</p>
        {/* Said here rather than only in the README: this is the moment
            someone is about to hand a token to an assistant, and "will this
            cost me anything" is the question they actually have. Stating the
            boundary plainly -- we charge nothing, your own AI access is
            between you and your provider -- is worth more than a promise of
            "free" that would be wrong for anyone billing per token. */}
        <p className="text-sm text-[var(--muted)]">{t("admin.tokensCost")}</p>

        {revealed && (
          <div className="flex flex-col gap-2 rounded-lg border border-[var(--accent)] bg-[var(--accent-soft)] p-3">
            <span className="text-sm font-medium">{t("admin.tokenRevealTitle")}</span>
            <div className="flex flex-wrap items-center gap-2">
              <code className="min-w-0 flex-1 break-all rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 font-mono text-xs">
                {revealed.token}
              </code>
              <Button variant="outline" size="sm" onClick={() => onCopy(revealed.token)}>
                <Copy className="h-3.5 w-3.5" />
                {t("admin.tokenCopy")}
              </Button>
            </div>
            <span className="text-xs text-[var(--muted)]">{t("admin.tokenRevealBody")}</span>

            <span className="mt-1 text-sm font-medium">{t("admin.tokenEndpointTitle")}</span>
            <span className="text-xs text-[var(--muted)]">{t("admin.tokenEndpointBody")}</span>
            <code className="break-all rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 font-mono text-xs">
              {endpointUrl}
              <br />
              Authorization: Bearer {revealed.token}
            </code>

            <Button variant="outline" size="sm" className="self-start" onClick={() => setRevealed(null)}>
              {t("admin.tokenRevealDone")}
            </Button>
          </div>
        )}

        {tokens === null ? (
          <SkeletonLines rows={2} label={t("common.loading")} />
        ) : tokens.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">{t("admin.tokensEmpty")}</p>
        ) : (
          <div className="flex flex-col divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
            {tokens.map((token) => (
              <TokenRow key={token.id} token={token} onRevoke={() => onRevoke(token)} />
            ))}
          </div>
        )}

        <form onSubmit={onCreate} className="flex flex-col gap-2 rounded-lg border border-[var(--border)] p-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex flex-1 flex-col gap-1.5">
              <label className="text-sm font-medium" htmlFor="token-name">
                {t("admin.tokenName")}
              </label>
              <Input id="token-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium" htmlFor="token-scope">
                {t("admin.tokenScope")}
              </label>
              <select
                id="token-scope"
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm"
              >
                <option value="read">{t("admin.tokenScopeRead")}</option>
                <option value="write">{t("admin.tokenScopeWrite")}</option>
                <option value="sync">{t("sync.scope")}</option>
              </select>
            </div>
            {scope === "sync" && (
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium" htmlFor="token-project">
                  {t("sync.project")}
                </label>
                <select
                  id="token-project"
                  value={syncProject}
                  onChange={(e) => setSyncProject(e.target.value)}
                  className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm"
                >
                  {projects.map((p) => (
                    <option key={p.slug} value={p.slug}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium" htmlFor="token-expires">
                {t("admin.tokenExpires")}
              </label>
              <Input
                id="token-expires"
                type="date"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                className="max-w-[11rem]"
              />
            </div>
            <Button type="submit" disabled={creating || !name.trim()}>
              {t("admin.tokenCreate")}
            </Button>
          </div>

          {/* The consequence of the choice, next to the choice. A write
              token is the one thing in this panel that can change what
              readers see, so it says so in plain words rather than leaving
              "write" to speak for itself. */}
          {scope === "sync" ? (
            <p className="flex items-start gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
              <span>{t("sync.scopeHint")}</span>
            </p>
          ) : scope === "write" ? (
            <p className="flex items-start gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
              <span>{t("admin.tokenScopeWriteHint")}</span>
            </p>
          ) : (
            <p className="text-xs text-[var(--muted)]">{t("admin.tokenScopeReadHint")}</p>
          )}
          <p className="text-xs text-[var(--muted)]">{t("admin.tokenExpiresHint")}</p>
        </form>

        <Button variant="outline" className="self-start" onClick={onClose}>
          {t("admin.cancel")}
        </Button>
      </CardContent>
    </Card>
  );
}

/** One token in the list: everything a decision to revoke needs (what it is
 *  called, what it may do, whether it still works, whether anything has ever
 *  used it) and, deliberately, nothing that identifies the value. */
export function TokenRow({ token, onRevoke }: { token: ApiToken; onRevoke: () => void }) {
  const { t } = useI18n();
  const write = token.scope === "write" || token.scope === "sync";
  // Compared as dates, matching the backend: a token expires at the END of
  // its expiry day, so today's date is still valid.
  const expired = Boolean(token.expires_at) && token.expires_at < new Date().toISOString().slice(0, 10);

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
      <KeyRound className="h-3.5 w-3.5 shrink-0 text-[var(--muted)]" aria-hidden="true" />
      <span className="font-medium">{token.name}</span>
      <span
        className={`rounded border px-1.5 text-xs uppercase leading-5 ${
          write ? "border-amber-500/60 text-amber-600" : "border-[var(--border)] text-[var(--muted)]"
        }`}
      >
        {token.scope === "sync"
          ? `${t("sync.scope")}: ${token.project}`
          : write
            ? t("admin.tokenScopeWrite")
            : t("admin.tokenScopeRead")}
      </span>
      <span className={`text-xs ${expired ? "text-red-500" : "text-[var(--muted)]"}`}>
        {!token.expires_at
          ? t("admin.tokenNoExpiry")
          : expired
            ? t("admin.tokenExpired")
            : `${t("admin.tokenExpiresOn")} ${token.expires_at}`}
      </span>
      <span className="text-xs text-[var(--muted)]">
        {t("admin.tokenLastUsed")}:{" "}
        {token.last_used_at ? token.last_used_at.slice(0, 16).replace("T", " ") : t("admin.tokenNeverUsed")}
      </span>
      <span className="text-xs text-[var(--muted)]">
        {t("admin.tokenCreatedOn")} {token.created_at.slice(0, 10)}
      </span>
      <Button variant="ghost" size="sm" className="ml-auto" onClick={onRevoke}>
        <Trash2 className="h-3.5 w-3.5" />
        {t("admin.tokenRevoke")}
      </Button>
    </div>
  );
}
