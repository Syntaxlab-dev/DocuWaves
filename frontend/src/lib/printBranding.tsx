import type { SitePdf } from "@/lib/api";

/**
 * The running header and footer of a printout, from the `pdf:` block of the
 * branding (backend site_branding._pdf): CSS page margin boxes, which the
 * browser fills on every printed sheet. Nothing shows on screen.
 *
 * The lines are the operator's text with {project}, {version}, {title},
 * {date} and {site} filled in here. They reach the stylesheet only as CSS
 * strings (cssString), so a quote or a backslash in them is text, never
 * CSS.
 */
export const PDF_DEFAULTS: SitePdf = { template: "classic", header: "", footer: "", page_numbers: true, logo: true };

export interface PrintValues {
  project: string;
  version: string;
  title: string;
  date: string;
  site: string;
}

export function fillPrintLine(line: string, values: PrintValues): string {
  const filled = line.replace(/\{(project|version|title|date|site)\}/g, (_, key: keyof PrintValues) => values[key] ?? "");
  // A placeholder with nothing to fill ("{version}" of an unversioned
  // project) would leave its separator behind: "Docs ·  · Manual". Rebuild
  // the line from its non-empty parts.
  // "-" only with spaces round it, so "e-mail" stays one word.
  const parts = filled.split(/(\s*[·|–—]\s*|\s+-\s+)/);
  const out: string[] = [];
  for (let i = 0; i < parts.length; i += 2) {
    const text = parts[i].trim();
    if (!text) continue;
    if (out.length) out.push(` ${parts[i - 1].trim()} `);
    out.push(text);
  }
  return out.join("").replace(/\s+/g, " ");
}

/** A CSS string literal. Quotes and backslashes are escaped as CSS escapes,
 *  and so are < and > -- this goes inside a <style> element, where a
 *  literal "</style>" would end it. */
export function cssString(text: string): string {
  const escaped = text
    .replace(/[\n\r\f\t]/g, " ")
    .replace(/[\\"<>]/g, (ch) => `\\${ch.codePointAt(0)!.toString(16)} `);
  return `"${escaped}"`;
}

export function printMarginCss(pdf: SitePdf, values: PrintValues, coverSheet = false): string {
  const header = fillPrintLine(pdf.header, values);
  const footer = fillPrintLine(pdf.footer, values);
  const boxes = [
    header && `@top-center { content: ${cssString(header)}; font-size: 8.5pt; color: #52525b; }`,
    footer && `@bottom-left { content: ${cssString(footer)}; font-size: 8.5pt; color: #52525b; }`,
    pdf.page_numbers && `@bottom-right { content: counter(page) " / " counter(pages); font-size: 8.5pt; color: #52525b; }`,
  ].filter(Boolean);
  if (!boxes.length) return "";
  // A cover sheet carries no running lines: it IS the title.
  const first = coverSheet
    ? " @page :first { @top-center { content: none; } @bottom-left { content: none; } @bottom-right { content: none; } }"
    : "";
  return `@media print { @page { ${boxes.join(" ")} }${first} }`;
}

/** Renders the margin boxes for whatever is on screen right now. */
export function PrintMargins({ pdf, values, coverSheet }: { pdf?: SitePdf; values: PrintValues; coverSheet?: boolean }) {
  const css = printMarginCss(pdf ?? PDF_DEFAULTS, values, coverSheet);
  return css ? <style data-print-margins="">{css}</style> : null;
}
