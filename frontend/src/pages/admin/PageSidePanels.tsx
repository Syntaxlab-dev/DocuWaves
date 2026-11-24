// The panels beside the page editor: review notes, preview links, history and images.
// Split out of pages/AdminApp.tsx, which keeps the layout and state.
import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import { toast } from "sonner";
import {
  BadgeCheck,
  Copy,
  ImagePlus,
  Link2,
  Plus,
  RotateCcw,
  History,
  Lock,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DiffView } from "@/components/DiffView";
import {
  api,
  ApiError,
  type Asset,
  type PageHistory,
  type PageVersion,
  type PreviewLink,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { formatIsoDate } from "@/lib/dates";
import { languageName } from "@/lib/lang";
import { useSite } from "@/lib/site";

/**
 * "Reviewed by X on Y", or the button that makes it say that.
 *
 * The name is ASKED FOR, not taken. A one-click "mark as reviewed" would
 * sign the note with the logged-in account -- which, on a single-account
 * instance, is the account everybody shares, and the one thing this note has
 * to get right is who. So it opens a prompt with that account name filled in
 * and lets it be typed over: the person carrying a change into the repo is
 * often not the person who read it.
 *
 * What this note is NOT -- an identity check, a signature, anything with
 * legal or regulatory weight -- is said in full inside that prompt, which is
 * the moment somebody could otherwise assume the opposite. Under the line
 * itself only the short form stands: it is on screen during every edit of
 * every page, and a four-line disclaimer in that position is one people stop
 * reading by the second page.
 */
export function ReviewNote({
  pageId,
  reviewedBy,
  reviewedAt,
  readOnly,
  onChanged,
}: {
  pageId: number;
  reviewedBy: string;
  reviewedAt: string;
  readOnly: boolean;
  onChanged: (reviewedBy: string, reviewedAt: string) => void;
}) {
  const { t, lang: uiLang } = useI18n();
  const { status } = useAuth();
  const [busy, setBusy] = useState(false);
  const has = Boolean(reviewedBy && reviewedAt);

  async function write(name: string) {
    setBusy(true);
    try {
      const result = await api.adminReviewPage(pageId, name);
      onChanged(result.reviewed_by, result.reviewed_at);
      toast.success(name ? t("admin.reviewSaved") : t("admin.reviewCleared"));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  function onMark() {
    const name = prompt(t("admin.reviewPrompt"), status?.username ?? "");
    // Cancel is null and must do nothing; an empty string typed on purpose
    // is not a way to clear the note either -- that is what the button next
    // to the note is for, and it says what it does.
    if (!name || !name.trim()) return;
    void write(name.trim());
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[var(--muted)]">
      <BadgeCheck className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span>
        {has
          ? t("admin.reviewBy")
              .replace("{name}", reviewedBy)
              .replace("{date}", formatIsoDate(reviewedAt, uiLang))
          : t("admin.reviewNone")}
      </span>
      {!readOnly && (
        <>
          <button
            type="button"
            disabled={busy}
            onClick={onMark}
            className="underline underline-offset-2 hover:text-[var(--accent)] disabled:opacity-50"
          >
            {t("admin.reviewMark")}
          </button>
          {has && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void write("")}
              className="underline underline-offset-2 hover:text-[var(--accent)] disabled:opacity-50"
            >
              {t("admin.reviewClear")}
            </button>
          )}
        </>
      )}
      <span className="w-full text-[var(--muted)]">{t("admin.reviewHint")}</span>
    </div>
  );
}

/**
 * The links that let somebody without a login read this one draft.
 *
 * A `<details>`, closed by default: most saves have nothing to do with
 * sharing, and a panel that is open on every page would be a permanent
 * invitation to hand out links. Its contents are only fetched when it is
 * opened, so the ordinary edit costs no request for it.
 *
 * A created link is shown ONCE and never again -- the server keeps only its
 * hash, exactly like an API token. The list below it is therefore a list of
 * links that EXIST, with their dates, not a list of links to copy: what a
 * lost one costs is one click to make another.
 */
export function PreviewLinksPanel({ pageId }: { pageId: number }) {
  const { t, lang: uiLang } = useI18n();
  const [links, setLinks] = useState<PreviewLink[] | null>(null);
  const [defaults, setDefaults] = useState({ max_days: 90, default_days: 7 });
  /** null until the server has said what its default is, so the number in
   *  the box is the one the backend would have used anyway -- and is never
   *  overwritten again once the author has changed it. */
  const [days, setDays] = useState<number | null>(null);
  const [created, setCreated] = useState<{ url: string; expires_at: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  async function load() {
    try {
      const result = await api.adminListPreviewLinks(pageId);
      setLinks(result.links);
      setDefaults({ max_days: result.max_days, default_days: result.default_days });
      setDays((current) => current ?? result.default_days);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
      setLinks([]);
    }
  }

  useEffect(() => {
    if (!open) return;
    void load();
    // pageId is in the deps because saving a renamed page hands the editor a
    // NEW id for the same page (the reindex reassigns it), and the panel has
    // to follow it rather than keep listing the old row's links.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pageId]);

  // Closing the panel drops the one-time link from the screen. It is not
  // recoverable, and leaving it lying open in a shared screen-share for the
  // rest of the session is not the same thing as showing it once.
  useEffect(() => {
    if (!open) setCreated(null);
  }, [open]);

  async function onCreate() {
    setBusy(true);
    try {
      const link = await api.adminCreatePreviewLink(pageId, days ?? defaults.default_days);
      setCreated({ url: `${window.location.origin}${link.url_path}`, expires_at: link.expires_at });
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function onRevoke(id: number) {
    try {
      await api.adminRevokePreviewLink(id);
      toast.success(t("admin.previewLinkRevoked"));
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    }
  }

  async function onCopy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(t("admin.tokenCopied"));
    } catch {
      // Clipboard access needs a secure context, which a LAN install on
      // plain http has none of. The link is on screen to select by hand.
      toast.error(t("admin.tokenCopyFailed"));
    }
  }

  return (
    <details
      className="mt-3 rounded-lg border border-[var(--border)] px-3 py-2"
      onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="flex cursor-pointer items-center gap-1.5 text-sm font-medium">
        <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
        {t("admin.previewLinks")}
      </summary>

      <p className="mt-2 text-xs text-[var(--muted)]">{t("admin.previewLinksHint")}</p>
      <p className="mt-1 text-xs text-[var(--muted)]">{t("admin.previewLinkEndsWhen")}</p>

      {created && (
        <div className="mt-2 flex flex-col gap-1.5 rounded-lg border border-amber-500/60 bg-amber-500/10 px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <code className="min-w-0 flex-1 break-all rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 font-mono text-xs">
              {created.url}
            </code>
            <Button variant="outline" size="sm" onClick={() => void onCopy(created.url)}>
              <Copy className="h-3.5 w-3.5" />
              {t("admin.previewLinkCopy")}
            </Button>
          </div>
          <span className="text-xs text-[var(--muted)]">{t("admin.previewLinkOnce")}</span>
          <span className="text-xs text-[var(--muted)]">
            {t("admin.previewLinkExpires").replace("{date}", formatIsoDate(created.expires_at, uiLang))}
          </span>
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
          {t("admin.previewLinkDays")}
          <Input
            type="number"
            min={1}
            max={defaults.max_days}
            value={days ?? defaults.default_days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="h-8 w-24"
          />
        </label>
        <Button variant="outline" size="sm" disabled={busy} onClick={() => void onCreate()}>
          <Plus className="h-3.5 w-3.5" />
          {t("admin.previewLinkNew")}
        </Button>
      </div>

      {links === null ? (
        <p className="mt-2 text-xs text-[var(--muted)]">{t("common.loading")}</p>
      ) : links.length === 0 ? (
        <p className="mt-2 text-xs text-[var(--muted)]">{t("admin.previewLinkNone")}</p>
      ) : (
        <div className="mt-2 flex flex-col divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
          {links.map((link) => (
            <div key={link.id} className="flex items-center gap-2 px-2.5 py-1.5 text-xs">
              <span className="flex-1">
                {t("admin.previewLinkExpires").replace("{date}", formatIsoDate(link.expires_at, uiLang))}
                {link.created_by
                  ? ` · ${t("admin.previewLinkCreatedBy").replace("{name}", link.created_by)}`
                  : ""}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6"
                onClick={() => void onRevoke(link.id)}
              >
                {t("admin.previewLinkRevoke")}
              </Button>
            </div>
          ))}
        </div>
      )}
    </details>
  );
}

/**
 * A page's change history, straight out of the content repo.
 *
 * Every page is a file in a git repository and every save is a commit, so the
 * record of who changed what, when and why already exists in full -- this
 * panel only makes it visible from inside the app. It shows the history of
 * ONE FILE: the language currently open in the editor. A page's translations
 * are separate files with separate histories, so the header names the file
 * (its `.de.md` suffix and all) rather than leaving that to be assumed.
 *
 * Selecting a commit shows what the page said then and what that commit
 * changed. Restoring it writes that text back as a NEW commit on top -- the
 * confirmation spells that out, because "restore" in most tools means
 * something was undone, and here nothing is: the history keeps every version
 * it had, including the one being replaced.
 */
export function HistoryPanel({
  pageId,
  readOnly,
  onRestored,
}: {
  pageId: number;
  /** A frozen documentation version: the history reads normally, there is
   *  simply nothing to restore into. The API refuses the write as well. */
  readOnly: boolean;
  onRestored: () => void;
}) {
  const { t, lang: uiLang } = useI18n();
  const { site } = useSite();
  const [history, setHistory] = useState<PageHistory | null>(null);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState<PageVersion | null>(null);
  const [loadingSha, setLoadingSha] = useState("");
  const [restoring, setRestoring] = useState(false);

  useEffect(() => {
    let current = true;
    setHistory(null);
    setSelected(null);
    setFailed(false);
    api
      .adminPageHistory(pageId)
      .then((data) => current && setHistory(data))
      .catch(() => current && setFailed(true));
    return () => {
      current = false;
    };
  }, [pageId]);

  async function onSelect(sha: string) {
    if (selected?.sha === sha) {
      setSelected(null); // clicking the open one closes it again
      return;
    }
    setLoadingSha(sha);
    try {
      setSelected(await api.adminPageVersion(pageId, sha));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setLoadingSha("");
    }
  }

  async function onRestore(version: PageVersion) {
    if (!confirm(t("admin.historyRestoreConfirm").replace("{sha}", version.sha))) return;
    setRestoring(true);
    try {
      await api.adminRestorePage(pageId, version.sha);
      toast.success(t("admin.historyRestored"));
      onRestored();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setRestoring(false);
    }
  }

  if (failed) return <p className="text-sm text-[var(--muted)]">{t("common.error")}</p>;
  if (!history) return <p className="text-sm text-[var(--muted)]">{t("common.loading")}</p>;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <History className="h-4 w-4 text-[var(--muted)]" aria-hidden="true" />
        {/* Which language's history this is, said twice on purpose: as the
            language's own name for a reader, and as the file's actual path
            for anyone who will go looking for it in the repo. */}
        {site.languages.length > 1 && history.language && (
          <span className="rounded border border-[var(--border)] px-1.5 py-0.5 text-xs">
            {languageName(history.language, uiLang)}
          </span>
        )}
        <code className="min-w-0 truncate font-mono text-xs text-[var(--muted)]" title={history.path}>
          {history.path}
        </code>
      </div>

      <p className="text-sm text-[var(--muted)]">{t("admin.historyIntro")}</p>

      {history.frozen && (
        <p className="flex items-start gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--muted)]">
          <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{t("admin.historyRestoreFrozen")}</span>
        </p>
      )}

      {history.commits.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">{t("admin.historyEmpty")}</p>
      ) : (
        <div className="flex flex-col divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
          {history.commits.map((commit) => (
            <div key={commit.sha}>
              <button
                type="button"
                onClick={() => onSelect(commit.sha)}
                aria-expanded={selected?.sha === commit.sha}
                className={`flex w-full flex-wrap items-baseline gap-x-2 gap-y-1 px-3 py-2 text-left text-sm ${
                  selected?.sha === commit.sha ? "bg-[var(--surface-2)]" : ""
                }`}
              >
                <code className="font-mono text-xs text-[var(--accent)]">{commit.sha}</code>
                <span className="min-w-0 flex-1 truncate">{commit.subject}</span>
                <span className="text-xs text-[var(--muted)]">{commit.author}</span>
                <span className="text-xs text-[var(--muted)]">{formatCommitDate(commit.date, uiLang)}</span>
                {/* The two commits that are not plain edits, marked -- the
                    first one, which has nothing before it to compare with,
                    and the one that moved the file. A rename is exactly the
                    point at which a history without --follow would appear to
                    stop, so naming the old file here is what shows it
                    didn't. */}
                {commit.status === "A" && (
                  <span className="rounded border border-[var(--border)] px-1 text-[10px] uppercase text-[var(--muted)]">
                    {t("admin.historyCreated")}
                  </span>
                )}
                {commit.renamed_from && (
                  <span className="w-full font-mono text-[11px] text-[var(--muted)]">
                    {t("admin.historyRenamedFrom")} {commit.renamed_from}
                  </span>
                )}
                {loadingSha === commit.sha && (
                  <span className="text-xs text-[var(--muted)]">{t("common.loading")}</span>
                )}
              </button>

              {selected?.sha === commit.sha && (
                <div className="flex flex-col gap-3 border-t border-[var(--border)] px-3 py-3">
                  {!readOnly && !history.frozen && (
                    <div>
                      <Button variant="outline" size="sm" disabled={restoring} onClick={() => onRestore(selected)}>
                        <RotateCcw className="h-3.5 w-3.5" />
                        {t("admin.historyRestore")}
                      </Button>
                    </div>
                  )}

                  <div>
                    <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
                      {t("admin.historyDiff")}
                    </h4>
                    {selected.status === "A" && (
                      <p className="mb-2 text-xs text-[var(--muted)]">{t("admin.historyFirstVersion")}</p>
                    )}
                    {selected.diff.trim() ? (
                      <DiffView diff={selected.diff} />
                    ) : (
                      <p className="text-sm text-[var(--muted)]">{t("admin.historyDiffNone")}</p>
                    )}
                  </div>

                  <div>
                    <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
                      {t("admin.historyContent")}
                    </h4>
                    <p className="mb-1 text-sm font-medium">{selected.title}</p>
                    <pre className="max-h-[20rem] overflow-auto rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3 font-mono text-xs whitespace-pre-wrap">
                      {selected.markdown_content}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** A commit's ISO timestamp in the reader's locale. Unlike the public page's
 *  date-only line this one has a full timestamp to work with, so `new Date`
 *  parses it correctly -- the offset is in the string. */
export function formatCommitDate(iso: string, locale: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
}

/** Upload button + the project's existing images, so re-using one on a
 *  second page is a click rather than another upload of the same file. An
 *  image belongs to the PROJECT, not to the page being edited -- that's the
 *  on-disk convention (content/<project>/assets/), and it's what makes the
 *  `../assets/x.png` a page pastes work from any of its categories. */
export function ImagesPanel({
  projectSlug,
  version,
  reloadKey,
  onInsert,
}: {
  projectSlug: string;
  /** The documentation version being edited -- images live inside it. Only
   *  ever the writable one in practice (this panel isn't rendered on a
   *  frozen version at all), but passed rather than left to the server's
   *  default so an upload can never end up in a version other than the one
   *  the editor is showing. */
  version: string;
  /** Bumped by the editor after it has uploaded something of its own (a
   *  pasted screenshot, a dropped file), so those appear here too. */
  reloadKey: number;
  onInsert: (asset: Asset) => void;
}) {
  const { t } = useI18n();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function loadAssets() {
    api
      .adminListAssets(projectSlug, version || undefined)
      .then((r) => setAssets(r.assets))
      .catch(() => setAssets([]));
  }
  useEffect(loadAssets, [projectSlug, version, reloadKey]);

  async function onPick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Cleared right away so picking the SAME file again still fires change.
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const asset = await api.adminUploadAsset(projectSlug, file, version || undefined);
      onInsert(asset);
      toast.success(t("admin.imageUploaded"));
      loadAssets();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setUploading(false);
    }
  }

  async function onDelete(filename: string) {
    if (!confirm(t("admin.imageDeleteConfirm"))) return;
    try {
      await api.adminDeleteAsset(projectSlug, filename);
      loadAssets();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    }
  }

  return (
    <div className="mt-3 rounded-lg border border-[var(--border)] p-3">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">{t("admin.images")}</h3>
        <Button
          variant="outline"
          size="sm"
          className="ml-auto"
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          <ImagePlus className="h-3.5 w-3.5" />
          {uploading ? t("admin.uploadingImage") : t("admin.insertImage")}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".png,.jpg,.jpeg,.gif,.webp,.avif,.svg"
          className="hidden"
          onChange={onPick}
        />
      </div>

      {/* The button is not the only way in, and the other two are invisible
          until someone knows about them -- so this says so once, here, next
          to the thing it is an alternative to. */}
      <p className="mt-1.5 text-xs text-[var(--muted)]">{t("admin.imagePasteHint")}</p>

      {assets.length === 0 ? (
        <p className="mt-2 text-sm text-[var(--muted)]">{t("admin.imagesEmpty")}</p>
      ) : (
        <div className="mt-2 flex flex-wrap gap-2">
          {assets.map((a) => (
            <div
              key={a.filename}
              className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1.5 text-xs"
            >
              <img src={a.url} alt="" className="h-8 w-8 rounded object-cover" loading="lazy" decoding="async" />
              <span className="max-w-[10rem] truncate" title={a.filename}>
                {a.filename}
              </span>
              <button type="button" className="text-[var(--accent)]" onClick={() => onInsert(a)}>
                {t("admin.imageInsert")}
              </button>
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onDelete(a.filename)}>
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
