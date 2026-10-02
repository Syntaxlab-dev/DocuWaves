/** Import a ZIP of Markdown (backend services/importer.py): pick the file
 *  and where it goes, look at the preview, then import. The preview and the
 *  import run the same plan on the server, so what is shown is what
 *  happens -- every page as a draft, in one commit. */
import { useState } from "react";
import { toast } from "sonner";
import { FileArchive, X } from "lucide-react";
import { api, ApiError, type ImportSummary, type ImportTarget, type Project } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TOOL_NAMES: Record<ImportSummary["tool"], string> = {
  markdown: "Markdown",
  mkdocs: "MkDocs",
  gitbook: "GitBook",
  docusaurus: "Docusaurus",
  obsidian: "Obsidian",
  confluence: "Confluence",
};
const LIST_LIMIT = 30;

export function ImportCard({
  projects,
  onClose,
  onImported,
}: {
  projects: Project[];
  onClose: () => void;
  onImported: (projectSlug: string) => void;
}) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [name, setName] = useState("");
  const [project, setProject] = useState(projects[0]?.slug ?? "");
  const [preview, setPreview] = useState<ImportSummary | null>(null);
  const [busy, setBusy] = useState(false);

  const target: ImportTarget = mode === "new" ? { name: name.trim() } : { project };
  const ready = Boolean(file) && (mode === "new" ? Boolean(name.trim()) : Boolean(project));

  function choose(next: File | null) {
    setFile(next);
    setPreview(null);
    if (next && !name.trim()) setName(next.name.replace(/\.zip$/i, "").replace(/[-_]+/g, " "));
  }

  async function run(apply: boolean) {
    if (!file || !ready) return;
    setBusy(true);
    try {
      if (apply) {
        const done = await api.adminImport(file, target);
        toast.success(t("import.done").replace("{n}", String(done.pages)));
        onImported(done.project.slug);
      } else {
        setPreview(await api.adminImportPreview(file, target));
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          <FileArchive className="h-4 w-4" />
          {t("import.title")}
        </CardTitle>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label={t("admin.cancel")}>
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <p className="text-xs text-[var(--muted)]">{t("import.hint")}</p>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-[var(--muted)]">{t("import.file")}</span>
          <input
            type="file"
            accept=".zip,application/zip"
            onChange={(e) => choose(e.target.files?.[0] ?? null)}
            className="text-sm"
          />
        </label>

        <fieldset className="flex flex-col gap-2 rounded-md border border-[var(--border)] p-2">
          <legend className="px-1 text-xs font-medium text-[var(--muted)]">{t("import.target")}</legend>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="import-target"
              checked={mode === "new"}
              onChange={() => {
                setMode("new");
                setPreview(null);
              }}
            />
            {t("import.newProject")}
          </label>
          {mode === "new" && (
            <Input
              value={name}
              placeholder={t("import.projectName")}
              onChange={(e) => {
                setName(e.target.value);
                setPreview(null);
              }}
            />
          )}
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="import-target"
              checked={mode === "existing"}
              disabled={projects.length === 0}
              onChange={() => {
                setMode("existing");
                setPreview(null);
              }}
            />
            {t("import.existingProject")}
          </label>
          {mode === "existing" && (
            <select
              value={project}
              onChange={(e) => {
                setProject(e.target.value);
                setPreview(null);
              }}
              className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm"
            >
              {projects.map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </fieldset>

        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={!ready || busy} onClick={() => void run(false)}>
            {t("import.preview")}
          </Button>
          <Button size="sm" disabled={!preview || busy} onClick={() => void run(true)}>
            {t("import.run").replace("{n}", String(preview?.pages ?? 0))}
          </Button>
          {busy && <span className="self-center text-xs text-[var(--muted)]">{t("import.working")}</span>}
        </div>

        {preview && (
          <div className="flex flex-col gap-3 rounded-lg border border-[var(--border)] p-3">
            <p>
              {t("import.summary")
                .replace("{tool}", TOOL_NAMES[preview.tool])
                .replace("{pages}", String(preview.pages))
                .replace("{categories}", String(preview.categories.length))
                .replace("{assets}", String(preview.assets))}
            </p>
            <p className="text-xs text-[var(--muted)]">{t("import.drafts")}</p>
            <ul className="flex flex-col gap-1">
              {preview.categories.map((c) => (
                <li key={c.slug}>
                  <details>
                    <summary className="cursor-pointer">
                      <span className="font-medium">{c.name}</span>{" "}
                      <span className="text-xs text-[var(--muted)]">
                        {t("import.pagesCount").replace("{n}", String(c.pages.length))}
                      </span>
                    </summary>
                    <ul className="ml-4 mt-1 list-disc text-xs">
                      {c.pages.map((p) => (
                        <li key={p.slug}>
                          {p.title} <span className="text-[var(--muted)]">← {p.source}</span>
                        </li>
                      ))}
                    </ul>
                  </details>
                </li>
              ))}
            </ul>
            {preview.warnings.length > 0 && (
              <details>
                <summary className="cursor-pointer text-amber-700 dark:text-amber-400">
                  {t("import.warnings").replace("{n}", String(preview.warnings.length))}
                </summary>
                <ul className="ml-4 mt-1 list-disc text-xs">
                  {preview.warnings.slice(0, LIST_LIMIT).map((w, i) => (
                    <li key={i}>
                      <code>{w.source}</code>: {w.message}
                    </li>
                  ))}
                  {preview.warnings.length > LIST_LIMIT && <li>…</li>}
                </ul>
              </details>
            )}
            {preview.skipped.length > 0 && (
              <details>
                <summary className="cursor-pointer text-[var(--muted)]">
                  {t("import.skipped").replace("{n}", String(preview.skipped.length))}
                </summary>
                <ul className="ml-4 mt-1 list-disc text-xs">
                  {preview.skipped.slice(0, LIST_LIMIT).map((s, i) => (
                    <li key={i}>
                      <code>{s.path}</code> – {s.reason}
                    </li>
                  ))}
                  {preview.skipped.length > LIST_LIMIT && <li>…</li>}
                </ul>
              </details>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
