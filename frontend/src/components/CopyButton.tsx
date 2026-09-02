import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { useI18n } from "@/lib/i18n";

/**
 * The copy button that sits in the corner of a `.code-block`.
 *
 * `getText` rather than a plain string: a fenced code block only has its text
 * in one piece once it is in the DOM (the highlighter has split it into
 * nested spans by then), while a diagram has it as the Markdown source it was
 * drawn from. Both are read at click time, so neither has to be kept in sync
 * with what is on screen.
 *
 * Its own file rather than part of MarkdownView, which is where it started:
 * MermaidDiagram needs it too, and MarkdownView already imports
 * MermaidDiagram -- importing back the other way would make a cycle out of
 * what is really just a shared button.
 */
export function CopyButton({ getText }: { getText: () => string }) {
  const { t } = useI18n();
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (state === "idle") return;
    const timer = window.setTimeout(() => setState("idle"), 2000);
    return () => window.clearTimeout(timer);
  }, [state]);

  async function copy() {
    setState((await writeToClipboard(getText())) ? "copied" : "failed");
  }

  return (
    <button
      type="button"
      onClick={copy}
      data-state={state}
      className="code-copy"
      aria-label={t("page.copyCode")}
      title={t("page.copyCode")}
    >
      {state === "copied" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      {state !== "idle" && <span>{state === "copied" ? t("page.copied") : t("page.copyFailed")}</span>}
    </button>
  );
}

/**
 * navigator.clipboard only exists in a secure context, and a self-hosted
 * DocuWaves is very often reached over plain http:// on a LAN (which is
 * exactly what the README's setup steps describe) -- there it is simply
 * undefined. execCommand("copy") is deprecated but is the only thing that
 * still copies on such an origin, so it's the fallback rather than the
 * primary path.
 */
async function writeToClipboard(text: string): Promise<boolean> {
  if (!text) return false;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Blocked by permissions policy or refused -- try the legacy path.
  }

  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  // Off-screen but not display:none, which would make it unselectable.
  area.style.position = "fixed";
  area.style.top = "-1000px";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    document.body.removeChild(area);
  }
}
