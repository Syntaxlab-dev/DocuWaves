import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, X } from "lucide-react";
import { api, ApiError, type SnippetFile } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSite } from "@/lib/site";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Scope = "project" | "site";
/** Which snippet the editor holds: an existing file, or a new one. */
type Selection = { kind: "existing"; name: string; language: string } | { kind: "new" } | null;

/**
 * Snippets and variables (services/snippets.py) for the project version
 * being looked at, or for the whole site.
 *
 * Variables are edited as the YAML file they are, rather than as a table:
 * a value per language is a mapping, and a table would either have to grow
 * a column per language or hide that such values exist. The backend checks
 * the text before writing it and says what is wrong and on which line.
 */
export function SnippetsCard({
  projectSlug,
  version,
  readOnly,
  onClose,
}: {
  projectSlug: string;
  /** The version being looked at ("" for an unversioned project). */
  version: string;
  /** Frozen version or read-only account: shown, not editable. */
  readOnly: boolean;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const { site } = useSite();
  const multilingual = site.languages.length > 1;

  const [scope, setScope] = useState<Scope>("project");
  const [loaded, setLoaded] = useState(false);
  const [variables, setVariables] = useState("");
  const [variablesDirty, setVariablesDirty] = useState(false);
  const [snippets, setSnippets] = useState<SnippetFile[]>([]);
  const [selection, setSelection] = useState<Selection>(null);
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);

  const target = scope === "project" ? { project: projectSlug, version } : { project: "", version: "" };
  // A frozen version is a project-level thing; the site's files are always
  // the working ones.
  const locked = readOnly && scope === "project";

  const load = useCallback(() => {
    setLoaded(false);
    api
      .adminListSnippets(scope === "project" ? projectSlug : "", scope === "project" ? version : "")
      .then((r) => {
        setVariables(r.variables);
        setVariablesDirty(false);
        setSnippets(r.snippets);
        setLoaded(true);
      })
      .catch((err) => toast.error(err instanceof ApiError ? err.message : t("common.error")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, projectSlug, version]);

  useEffect(() => {
    setSelection(null);
    load();
  }, [load]);

  function open(file: SnippetFile) {
    setSelection({ kind: "existing", name: file.name, language: file.language });
    setName(file.name);
    setLanguage(file.language);
    setContent(file.content);
  }

  function startNew() {
    setSelection({ kind: "new" });
    setName("");
    setLanguage("");
    setContent("");
  }

  async function run(action: () => Promise<unknown>, success: Parameters<typeof t>[0]) {
    setBusy(true);
    try {
      await action();
      toast.success(t(success));
      return true;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function saveVariables() {
    if (await run(() => api.adminWriteVariables({ ...target, text: variables }), "snippets.variablesSaved")) {
      setVariablesDirty(false);
    }
  }

  async function saveSnippet() {
    const clean = name.trim();
    if (!clean) return;
    const ok = await run(
      () => api.adminWriteSnippet(clean, { ...target, language, content }),
      "snippets.saved",
    );
    if (ok) {
      setSelection({ kind: "existing", name: clean, language });
      load();
    }
  }

  async function deleteSnippet() {
    if (selection?.kind !== "existing") return;
    if (!confirm(t("snippets.deleteConfirm").replace("{name}", selection.name))) return;
    const ok = await run(
      () => api.adminDeleteSnippet(selection.name, { ...target, language: selection.language }),
      "snippets.deleted",
    );
    if (ok) {
      setSelection(null);
      load();
    }
  }

  const includeLine = `<!-- snippet: ${name.trim() || "name"} -->`;

  return (
    <Card className="mb-4">
      <CardHeader className="flex flex-row flex-wrap items-center gap-2 space-y-0">
        <CardTitle className="mr-auto text-base font-semibold text-[var(--ink)]">{t("snippets.title")}</CardTitle>
        <div role="group" aria-label={t("snippets.scope")} className="flex rounded-lg border border-[var(--border)] p-0.5">
          {(["project", "site"] as const).map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={scope === s}
              onClick={() => setScope(s)}
              className={`rounded-md px-2.5 py-1 text-xs ${
                scope === s ? "bg-[var(--accent-soft)] text-[var(--accent)]" : "text-[var(--muted)]"
              }`}
            >
              {t(s === "project" ? "snippets.scopeProject" : "snippets.scopeSite")}
            </button>
          ))}
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label={t("admin.cancel")}>
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>

      <CardContent className="space-y-6">
        <p className="text-sm text-[var(--muted)]">
          {t(scope === "project" ? "snippets.introProject" : "snippets.introSite")}
        </p>

        {/* ---- Variables ---- */}
        <section className="space-y-2">
          <h3 className="text-sm font-semibold">{t("snippets.variables")}</h3>
          <p className="text-xs text-[var(--muted)]">{t("snippets.variablesHint")}</p>
          <Textarea
            value={variables}
            readOnly={locked || !loaded}
            onChange={(e) => {
              setVariables(e.target.value);
              setVariablesDirty(true);
            }}
            placeholder={"produkt: DocuWaves\nport: 8091\ndownload:\n  de: https://example.com/de\n  en: https://example.com/en"}
            className="min-h-[140px] font-mono text-sm"
            spellCheck={false}
          />
          {!locked && (
            <Button size="sm" onClick={saveVariables} disabled={busy || !variablesDirty}>
              {t("admin.save")}
            </Button>
          )}
        </section>

        {/* ---- Snippets ---- */}
        <section className="space-y-2">
          <h3 className="text-sm font-semibold">{t("snippets.snippets")}</h3>
          <div className="grid gap-3 md:grid-cols-[200px_minmax(0,1fr)]">
            <div className="space-y-1">
              {loaded && snippets.length === 0 && <p className="text-xs text-[var(--muted)]">{t("snippets.none")}</p>}
              {snippets.map((file) => {
                const active =
                  selection?.kind === "existing" && selection.name === file.name && selection.language === file.language;
                return (
                  <button
                    key={`${file.name}.${file.language}`}
                    type="button"
                    onClick={() => open(file)}
                    className={`flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm ${
                      active ? "bg-[var(--accent-soft)] text-[var(--accent)]" : "hover:bg-[var(--surface-2)]"
                    }`}
                  >
                    <span className="truncate font-mono">{file.name}</span>
                    {file.language && (
                      <span className="rounded border border-[var(--border)] px-1 text-[10px] uppercase">{file.language}</span>
                    )}
                  </button>
                );
              })}
              {!locked && (
                <Button variant="outline" size="sm" className="mt-2 w-full" onClick={startNew}>
                  <Plus className="h-3.5 w-3.5" />
                  {t("snippets.new")}
                </Button>
              )}
            </div>

            <div className="min-w-0">
              {selection === null ? (
                <p className="text-sm text-[var(--muted)]">{t("snippets.pick")}</p>
              ) : (
                <div className="space-y-2">
                  <div className="flex flex-wrap gap-2">
                    <Input
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      // Renaming would leave every page that includes the
                      // old name without it; a new name is a new snippet.
                      readOnly={selection.kind === "existing" || locked}
                      placeholder={t("snippets.namePlaceholder")}
                      aria-label={t("snippets.name")}
                      className="max-w-xs font-mono"
                    />
                    {multilingual && (
                      <select
                        aria-label={t("snippets.language")}
                        value={language}
                        disabled={selection.kind === "existing" || locked}
                        onChange={(e) => setLanguage(e.target.value)}
                        className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm"
                      >
                        <option value="">{t("snippets.allLanguages")}</option>
                        {site.languages.map((code) => (
                          <option key={code} value={code}>
                            {code.toUpperCase()}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                  <p className="text-xs text-[var(--muted)]">
                    {t("snippets.includeWith")}{" "}
                    <code className="select-all rounded bg-[var(--surface-2)] px-1 py-0.5">{includeLine}</code>
                  </p>
                  <Textarea
                    value={content}
                    readOnly={locked}
                    onChange={(e) => setContent(e.target.value)}
                    className="min-h-[200px] font-mono text-sm"
                  />
                  {!locked && (
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" onClick={saveSnippet} disabled={busy || !name.trim()}>
                        {t("admin.save")}
                      </Button>
                      {selection.kind === "existing" && (
                        <Button size="sm" variant="outline" onClick={deleteSnippet} disabled={busy}>
                          <Trash2 className="h-3.5 w-3.5" />
                          {t("admin.delete")}
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </section>
      </CardContent>
    </Card>
  );
}
