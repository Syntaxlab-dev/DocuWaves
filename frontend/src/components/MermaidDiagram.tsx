import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { CopyButton } from "@/components/CopyButton";
import { useI18n } from "@/lib/i18n";
import { cssVariable, useIsDarkTheme } from "@/lib/theme";

/**
 * A ```mermaid fenced block, drawn as a diagram.
 *
 * Mermaid is by a wide margin the largest thing this frontend can pull in --
 * on its own bigger than everything else in the bundle put together -- so it
 * is imported DYNAMICALLY, from inside the effect below. That import sits on
 * a code path which only runs once a page actually contains a diagram, which
 * is the whole point: the bundler gives it a chunk of its own, and a reader
 * on a page with no diagram never asks for it. A static
 * `import mermaid from "mermaid"` at the top of this file would undo that in
 * one line.
 *
 * Bundled, never from a CDN: a self-hosted DocuWaves is routinely run on a
 * LAN with no route out, and a documentation page must not go blank because
 * some third party is unreachable. Nothing here needs a Content-Security-
 * Policy exception either -- the app's own HTML is served without one (only
 * uploaded SVGs and branding images get the restrictive header, see
 * public_content.py), and a diagram is inline SVG in the app's own document
 * rather than a loaded resource.
 */

/** Naming the module in a type position is erased at compile time, so this
 *  costs nothing at runtime -- the dynamic import stays the only real one. */
type MermaidApi = (typeof import("mermaid"))["default"];

/**
 * How long the source has to stop changing before it is parsed.
 *
 * The admin editor's preview re-renders on every keystroke, and most of those
 * keystrokes are a half-finished diagram: without this, `graph TD` on its way
 * to `graph TD\n  A-->B` is parsed -- and reported as broken -- once per
 * character typed. A short pause makes that roughly one parse per word, and
 * is what stops the error notice flickering on and off under the author's
 * hands. Short enough to go unnoticed on a published page, which renders once.
 */
const RENDER_DEBOUNCE_MS = 150;

export function MermaidDiagram({ code }: { code: string }) {
  const { t } = useI18n();
  const isDark = useIsDarkTheme();
  const [svg, setSvg] = useState<string | null>(null);
  /** null = fine so far; a string = the diagram could not be drawn, and the
   *  string is mermaid's own explanation (empty when there isn't a useful
   *  one). */
  const [error, setError] = useState<string | null>(null);
  const hostRef = useRef<HTMLDivElement>(null);

  // Mermaid builds `#id ...` CSS selectors out of this, so it has to be a
  // valid one -- React's useId is unique per component instance (two diagrams
  // on the same page can never collide) but spells it "«r1»".
  const domId = `mermaid-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;

  useEffect(() => {
    let cancelled = false;

    async function draw() {
      let mermaid: MermaidApi;
      try {
        mermaid = (await import("mermaid")).default;
      } catch {
        // The chunk itself didn't load (offline mid-session, a half-deployed
        // update). There is nothing to say beyond "no diagram here" -- the
        // browser's own message would only confuse a documentation reader --
        // and the source is shown either way.
        if (!cancelled) setError("");
        return;
      }
      if (cancelled) return;
      configure(mermaid, isDark);

      try {
        // parse() runs the grammar and touches no DOM at all, so an
        // unfinished diagram cannot leave anything behind -- and the message
        // it throws ("Parse error on line 3: ...") names the line, which is
        // the one thing the author needs. That is why the syntax is checked
        // here rather than left for render() to discover.
        await mermaid.parse(code);
        const result = await mermaid.render(domId, code);
        if (cancelled) return;
        setSvg(result.svg);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        // The previous drawing goes with it: leaving the last version that
        // happened to parse sitting above source that no longer produces it
        // would be a quietly wrong page.
        setSvg(null);
        setError(err instanceof Error ? err.message : String(err));
      }
    }

    const timer = window.setTimeout(() => void draw(), RENDER_DEBOUNCE_MS);
    return () => {
      // Both halves matter: clearTimeout drops a render that has not started
      // yet, `cancelled` drops the result of one already in flight. Without
      // the second, a slow diagram finishing after the author has typed on
      // would paint an older picture over the newer one.
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [code, isDark, domId]);

  useLayoutEffect(() => {
    // Mermaid sizes its <svg> to fit whatever box it lands in (width="100%"
    // plus an inline max-width), so a wide diagram is SHRUNK until its labels
    // are unreadable instead of being allowed to overflow. On a docs page a
    // wide thing scrolls -- which is what a wide table and a long code line
    // already do here -- so the svg is pinned back to the natural size its
    // own viewBox declares, and .mermaid-block scrolls it.
    const el = hostRef.current?.firstElementChild;
    if (!(el instanceof SVGSVGElement)) return;
    const box = el.viewBox.baseVal;
    if (!box.width || !box.height) return;
    el.setAttribute("width", String(box.width));
    el.setAttribute("height", String(box.height));
    el.style.maxWidth = "none";
  }, [svg]);

  if (error !== null) {
    // The source, then why there is no picture of it. The same <pre> and the
    // same copy button as any other fenced block, so a diagram that does not
    // parse degrades to exactly what the block would have looked like without
    // this component at all -- and one bad diagram never takes the rest of
    // the page with it.
    return (
      <DiagramFrame code={code}>
        <pre>
          <code>{code}</code>
        </pre>
        <p className="mermaid-error">
          <strong>{t("page.diagramFailed")}</strong>
          {error && <span className="mermaid-error-detail">{error}</span>}
        </p>
      </DiagramFrame>
    );
  }

  return (
    <DiagramFrame code={code}>
      {svg === null ? (
        <p className="mermaid-pending">{t("page.diagramRendering")}</p>
      ) : (
        <div
          className="mermaid-block"
          ref={hostRef}
          // Mermaid's own output, drawn from Markdown that is already trusted
          // enough to be rendered as this page, with securityLevel "strict"
          // (see configure()) -- which encodes any HTML inside a diagram's
          // labels rather than passing it through.
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      )}
    </DiagramFrame>
  );
}

/** What both states share: whatever is being shown, plus a copy button over
 *  the Mermaid SOURCE -- see the README on why the source and not the
 *  picture. */
function DiagramFrame({ code, children }: { code: string; children: ReactNode }) {
  return (
    <div className="code-block">
      {children}
      <CopyButton getText={() => code} />
    </div>
  );
}

/**
 * mermaid.initialize() is global and rebuilds the whole theme, so it runs
 * once per PALETTE rather than once per diagram: ten diagrams on a page share
 * a single initialisation, and a reader flipping to dark mode causes exactly
 * one more.
 */
let configuredTheme: string | null = null;

function configure(mermaid: MermaidApi, dark: boolean) {
  const theme = dark ? "dark" : "default";
  if (configuredTheme === theme) return;

  // The two things mermaid cannot work out for itself. `background` is the
  // colour the diagram will actually sit on: mermaid derives its line and
  // text colours by inverting this, so leaving it at the built-in grey is
  // what produces dark arrows on a dark page. `fontFamily` keeps a diagram
  // set in the same typeface as the prose around it, instead of looking like
  // a pasted screenshot. Both are read from the live custom properties, so an
  // instance's own palette carries over; an empty one is left out rather than
  // handed to mermaid, which expects a real colour.
  const themeVariables: Record<string, string> = {};
  const background = cssVariable("--bg");
  const fontFamily = cssVariable("--font-sans");
  if (background) themeVariables.background = background;
  if (fontFamily) themeVariables.fontFamily = fontFamily;

  mermaid.initialize({
    // Nothing on this page is a `<div class="mermaid">` for mermaid to find
    // by itself; every diagram is rendered explicitly by the component above.
    startOnLoad: false,
    theme,
    themeVariables,
    securityLevel: "strict",
    // Without this, a diagram that fails to parse or draw makes mermaid
    // render its own "syntax error" bomb graphic into a temporary <div> it
    // appends to <body> -- and then leave that div behind as it throws. In
    // the editor preview, where a failed parse is the NORMAL state while
    // someone is typing, that is one orphaned node per attempt. With it,
    // mermaid cleans up after itself and simply throws, which is what this
    // caller wants: the error is shown as text, in place, by us.
    suppressErrorRendering: true,
  });
  configuredTheme = theme;
}
