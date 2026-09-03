import { useI18n } from "@/lib/i18n";

/**
 * A syntax reminder under the editor, collapsed by default.
 *
 * Under the box rather than beside it: it is consulted for a few seconds and
 * then ignored for an hour, which is not worth a permanent column of the
 * screen. Collapsed by default for the same reason -- an author who already
 * knows Markdown should not have to look past a reference table to reach the
 * text every time they open a page.
 *
 * Only the labels are translated. The syntax is the syntax.
 */
const ROWS: { key: string; syntax: string }[] = [
  { key: "cheat.heading", syntax: "## Heading" },
  { key: "cheat.bold", syntax: "**bold**" },
  { key: "cheat.italic", syntax: "*italic*" },
  { key: "cheat.code", syntax: "`code`" },
  { key: "cheat.codeBlock", syntax: "```bash\n…\n```" },
  { key: "cheat.link", syntax: "[text](https://example.com)" },
  { key: "cheat.pageLink", syntax: "[text](/p/project/pages/slug)" },
  { key: "cheat.image", syntax: "![alt](../assets/shot.png)" },
  { key: "cheat.media", syntax: "![alt](../assets/tour.mp4)" },
  { key: "cheat.list", syntax: "- one\n- two" },
  { key: "cheat.numbered", syntax: "1. one\n2. two" },
  { key: "cheat.quote", syntax: "> note" },
  { key: "cheat.table", syntax: "| a | b |\n|---|---|\n| 1 | 2 |" },
  { key: "cheat.rule", syntax: "---" },
  { key: "cheat.math", syntax: "$E = mc^2$" },
  { key: "cheat.diagram", syntax: "```mermaid\ngraph TD; A-->B;\n```" },
];

const SHORTCUTS: { key: string; combo: string }[] = [
  { key: "cheat.bold", combo: "Ctrl/⌘ + B" },
  { key: "cheat.italic", combo: "Ctrl/⌘ + I" },
  { key: "cheat.code", combo: "Ctrl/⌘ + E" },
  { key: "cheat.link", combo: "Ctrl/⌘ + K" },
  { key: "cheat.save", combo: "Ctrl/⌘ + S" },
];

export function MarkdownCheatSheet() {
  const { t } = useI18n();

  return (
    <details className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm">
      <summary className="cursor-pointer font-medium">{t("cheat.title")}</summary>

      <div className="mt-3 grid gap-6 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div>
          <table className="w-full">
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.key} className="align-top">
                  <th scope="row" className="w-2/5 py-1 pr-3 text-left font-normal text-[var(--muted)]">
                    {t(row.key as never)}
                  </th>
                  <td className="py-1">
                    <code className="whitespace-pre font-mono text-xs">{row.syntax}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            {t("cheat.shortcuts")}
          </div>
          <table className="w-full">
            <tbody>
              {SHORTCUTS.map((row) => (
                <tr key={row.combo}>
                  <th scope="row" className="py-1 pr-3 text-left font-normal text-[var(--muted)]">
                    {t(row.key as never)}
                  </th>
                  <td className="py-1">
                    <kbd className="rounded border border-[var(--border)] bg-[var(--surface-2)] px-1.5 py-0.5 font-mono text-xs">
                      {row.combo}
                    </kbd>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-[var(--muted)]">{t("cheat.pasteHint")}</p>
        </div>
      </div>
    </details>
  );
}
