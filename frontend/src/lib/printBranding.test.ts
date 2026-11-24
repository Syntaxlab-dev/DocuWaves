import { describe, expect, it } from "vitest";
import { cssString, fillPrintLine, printMarginCss, PDF_DEFAULTS } from "./printBranding";

const values = { project: "Handbook", version: "2.0", title: "Install", date: "24.11.2026", site: "ACME Docs" };

describe("fillPrintLine", () => {
  it("fills every placeholder", () => {
    expect(fillPrintLine("{site} · {project} {version} · {title} · {date}", values)).toBe(
      "ACME Docs · Handbook 2.0 · Install · 24.11.2026",
    );
  });
  it("drops the separator of an empty placeholder", () => {
    expect(fillPrintLine("{project} · {version} · {title}", { ...values, version: "" })).toBe("Handbook · Install");
    expect(fillPrintLine("{version} | {title}", { ...values, version: "" })).toBe("Install");
  });
  it("keeps hyphenated words whole", () => {
    expect(fillPrintLine("E-Mail: docs@acme.example - {project}", values)).toBe("E-Mail: docs@acme.example - Handbook");
  });
  it("leaves unknown braces as text", () => {
    expect(fillPrintLine("{nope} {title}", values)).toBe("{nope} Install");
  });
});

describe("cssString", () => {
  it("can't end the string or the style element", () => {
    const s = cssString('a"b\\c</style><script>');
    expect(s).not.toMatch(/<|>/);
    expect(s.slice(1, -1)).not.toMatch(/(^|[^\\])"/);
    expect(s).toBe('"a\\22 b\\5c c\\3c /style\\3e \\3c script\\3e "');
  });
});

describe("printMarginCss", () => {
  it("page numbers only by default", () => {
    const css = printMarginCss(PDF_DEFAULTS, values);
    expect(css).toContain("@bottom-right");
    expect(css).not.toContain("@top-center");
  });
  it("keeps the cover sheet clean", () => {
    expect(printMarginCss(PDF_DEFAULTS, values, true)).toContain("@page :first");
    expect(printMarginCss(PDF_DEFAULTS, values)).not.toContain(":first");
  });
  it("nothing at all when everything is off", () => {
    expect(printMarginCss({ ...PDF_DEFAULTS, page_numbers: false }, values)).toBe("");
  });
  it("header and footer as margin boxes", () => {
    const css = printMarginCss({ ...PDF_DEFAULTS, header: "{project}", footer: "Confidential" }, values);
    expect(css).toContain('@top-center { content: "Handbook"');
    expect(css).toContain('@bottom-left { content: "Confidential"');
  });
});
