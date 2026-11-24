import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { X } from "lucide-react";
import { api, ApiError, type ReplacePreview, type ReplaceQuery } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Search and replace across one project (backend services/search_replace.py).
 *
 * Two steps: Search lists every page with a match and a few lines around
 * each, every page ticked; Replace changes the ticked ones in one commit.
 * Changing the search text throws the preview away, so what is replaced is
 * always what was just shown.
 */
export function ReplaceCard({
  projectId,
  version,
  onClose,
  onChanged,
}: {
  projectId: number;
  version: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [find, setFind] = useState("");
  const [replace, setReplace] = useState("");
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [wholeWord, setWholeWord] = useState(false);
  const [preview, setPreview] = useState<ReplacePreview | null>(null);
  const [ticked, setTicked] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  const query = (): ReplaceQuery => ({
    find,
    replace,
    case_sensitive: caseSensitive,
    whole_word: wholeWord,
    version: version || undefined,
  });

  function invalidate() {
    setPreview(null);
    setTicked(new Set());
  }

  async function onSearch(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const result = await api.adminReplacePreview(projectId, query());
      setPreview(result);
      setTicked(new Set(result.pages.map((p) => p.id)));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function onReplace() {
    if (!preview) return;
    const pages = Object.fromEntries(preview.pages.filter((p) => ticked.has(p.id)).map((p) => [p.id, p.revision]));
    setBusy(true);
    try {
      const result = await api.adminReplace(projectId, query(), pages);
      toast.success(
        t("replace.done").replace("{n}", String(result.replacements)).replace("{pages}", String(result.done.length)),
      );
      if (result.skipped.length > 0) {
        toast.warning(t("replace.skipped").replace("{n}", String(result.skipped.length)));
      }
      invalidate();
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  const tickedCount = preview ? preview.pages.filter((p) => ticked.has(p.id)).length : 0;

  return (
    <Card className="mb-4">
      <CardHeader className="flex flex-row items-center gap-2 space-y-0">
        <CardTitle className="mr-auto text-base font-semibold text-[var(--ink)]">{t("replace.title")}</CardTitle>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label={t("admin.cancel")}>
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-[var(--muted)]">{t("replace.intro")}</p>
        <form onSubmit={onSearch} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
          <Input
            aria-label={t("replace.find")}
            placeholder={t("replace.find")}
            value={find}
            maxLength={200}
            required
            onChange={(e) => {
              setFind(e.target.value);
              invalidate();
            }}
          />
          <Input
            aria-label={t("replace.with")}
            placeholder={t("replace.with")}
            value={replace}
            maxLength={1000}
            onChange={(e) => {
              setReplace(e.target.value);
              invalidate();
            }}
          />
          <Button type="submit" size="sm" disabled={busy || !find.trim()}>
            {t("replace.search")}
          </Button>
          <div className="flex flex-wrap gap-4 text-sm sm:col-span-3">
            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={caseSensitive}
                onChange={(e) => {
                  setCaseSensitive(e.target.checked);
                  invalidate();
                }}
              />
              {t("replace.caseSensitive")}
            </label>
            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={wholeWord}
                onChange={(e) => {
                  setWholeWord(e.target.checked);
                  invalidate();
                }}
              />
              {t("replace.wholeWord")}
            </label>
          </div>
        </form>

        {preview && preview.pages.length === 0 && <p className="text-sm text-[var(--muted)]">{t("replace.none")}</p>}

        {preview && preview.pages.length > 0 && (
          <div className="space-y-3">
            <p className="text-sm">
              {t("replace.found").replace("{n}", String(preview.total)).replace("{pages}", String(preview.pages.length))}
            </p>
            <ul className="space-y-2" aria-label={t("replace.results")}>
              {preview.pages.map((p) => (
                <li key={p.id} className="rounded-lg border border-[var(--border)] p-2 text-sm">
                  <label className="flex items-center gap-2 font-medium">
                    <input
                      type="checkbox"
                      checked={ticked.has(p.id)}
                      onChange={(e) =>
                        setTicked((prev) => {
                          const next = new Set(prev);
                          if (e.target.checked) next.add(p.id);
                          else next.delete(p.id);
                          return next;
                        })
                      }
                    />
                    <span className="min-w-0 truncate">{p.title}</span>
                    <span className="text-xs font-normal text-[var(--muted)]">
                      {p.category}
                      {p.language ? ` · ${p.language}` : ""} · {p.count}×
                    </span>
                    {p.becomes_proposal && (
                      <span className="ml-auto rounded bg-[var(--surface-2)] px-1.5 py-0.5 text-xs font-normal text-[var(--muted)]">
                        {t("replace.becomesProposal")}
                      </span>
                    )}
                  </label>
                  <ul className="mt-1 space-y-0.5 pl-6 font-mono text-xs text-[var(--muted)]">
                    {p.snippets.map((s, i) => (
                      <li key={i} className="break-words">
                        …{s.before}
                        <del className="bg-red-500/15 text-[var(--ink)]">{s.match}</del>
                        {replace && <ins className="bg-green-500/15 text-[var(--ink)] no-underline">{replace}</ins>}
                        {s.after}…
                      </li>
                    ))}
                    {p.count > p.snippets.length && <li>{t("replace.more").replace("{n}", String(p.count - p.snippets.length))}</li>}
                  </ul>
                </li>
              ))}
            </ul>
            <Button size="sm" disabled={busy || tickedCount === 0} onClick={onReplace}>
              {t("replace.apply").replace("{n}", String(tickedCount))}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
