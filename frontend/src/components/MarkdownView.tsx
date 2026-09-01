import { useEffect, useMemo, useRef, useState, type HTMLAttributes, type ReactNode } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Check, Copy } from "lucide-react";
import { collectHeadings } from "@/lib/headings";
import { useI18n } from "@/lib/i18n";

/**
 * Images are written in a page as a plain relative path
 * (`![Dashboard](../assets/dashboard.png)`) so the same .md still renders on
 * GitHub -- which means the browser can't load them as-is: relative to
 * /p/<project>/<page> they point at nothing. `projectSlug` + `categorySlug`
 * are the page's location in the content repo, and are all that's needed to
 * turn such a path into the public asset URL.
 *
 * Both are optional: without them (nothing renders MarkdownView that way
 * today, but a future caller might) relative images are simply left alone
 * rather than rewritten into a wrong URL.
 *
 * Heading anchors and code-block copy buttons need no props at all, so the
 * admin editor's preview pane gets them too without knowing about them.
 */
export function MarkdownView({
  content,
  projectSlug,
  categorySlug,
}: {
  content: string;
  projectSlug?: string;
  categorySlug?: string;
}) {
  const { t } = useI18n();

  // Keyed by source line, see lib/headings.ts for why that and not a
  // render-order counter.
  const headingIds = useMemo(() => {
    const byLine = new Map<number, string>();
    for (const heading of collectHeadings(content)) byLine.set(heading.line, heading.id);
    return byLine;
  }, [content]);

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        urlTransform={urlTransform}
        components={{
          // `node` is react-markdown's own hast node -- destructured out
          // (and never used) purely so the spread below doesn't put it on
          // the DOM element, which React would warn about.
          img({ node, src, alt, ...props }) {
            void node;
            const resolved = resolveImageSrc(typeof src === "string" ? src : "", projectSlug, categorySlug);
            return (
              <img
                {...props}
                // undefined, never "": a src of "" makes the browser
                // re-request the current page as an image. Empty is what
                // urlTransform returns for a protocol it refuses.
                src={resolved || undefined}
                alt={alt ?? ""}
                loading="lazy"
                decoding="async"
              />
            );
          },
          h2({ node, children, ...props }) {
            return (
              <Heading tag="h2" id={headingIds.get(node?.position?.start.line ?? -1)} label={t("page.headingAnchor")} {...props}>
                {children}
              </Heading>
            );
          },
          h3({ node, children, ...props }) {
            return (
              <Heading tag="h3" id={headingIds.get(node?.position?.start.line ?? -1)} label={t("page.headingAnchor")} {...props}>
                {children}
              </Heading>
            );
          },
          pre({ node, children, ...props }) {
            void node;
            return <CodeBlock {...props}>{children}</CodeBlock>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

/** A heading with no id is one collectHeadings() didn't pick up (a setext
 *  heading, say) -- rendered plain rather than given an ad-hoc id, since
 *  nothing in the contents links to it and an invented id would be the one
 *  thing that could still drift. */
function Heading({
  tag: Tag,
  id,
  label,
  children,
  ...props
}: { tag: "h2" | "h3"; id?: string; label: string; children?: ReactNode } & HTMLAttributes<HTMLHeadingElement>) {
  if (!id) return <Tag {...props}>{children}</Tag>;
  return (
    <Tag {...props} id={id}>
      {children}
      <a href={`#${id}`} className="heading-anchor" aria-label={label}>
        #
      </a>
    </Tag>
  );
}

function CodeBlock({ children, ...props }: HTMLAttributes<HTMLPreElement>) {
  const { t } = useI18n();
  const preRef = useRef<HTMLPreElement>(null);
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (state === "idle") return;
    const timer = window.setTimeout(() => setState("idle"), 2000);
    return () => window.clearTimeout(timer);
  }, [state]);

  async function copy() {
    // textContent of the rendered <pre>, not the Markdown source: by this
    // point rehype-highlight has split the code into nested <span>s, and the
    // DOM is where the block's plain text still exists in one piece.
    setState((await writeToClipboard(preRef.current?.textContent ?? "")) ? "copied" : "failed");
  }

  return (
    <div className="code-block">
      <pre ref={preRef} {...props}>
        {children}
      </pre>
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
    </div>
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

/**
 * react-markdown's own URL sanitizer allows http/https/mailto/tel and
 * nothing else, which also strips a `data:` image -- a perfectly normal way
 * to inline a small diagram in a Markdown file, and harmless in an <img>
 * (an image is a non-scripting context, unlike an <a href>). Widened for
 * exactly that one case; every other URL, and every href anywhere, still
 * goes through the default sanitizer untouched.
 */
const urlTransform = (url: string, key: string, node: { tagName?: string }): string =>
  key === "src" && node.tagName === "img" && /^data:image\//i.test(url) ? url : defaultUrlTransform(url);

/** Anything with its own scheme (http:, https:, data:, blob:), a
 *  protocol-relative `//host/...`, a site-absolute `/foo.png` or a bare
 *  `#anchor` is already a complete address and must survive untouched. */
const ABSOLUTE_SRC = /^([a-z][a-z0-9+.-]*:|\/\/|\/|#)/i;

function resolveImageSrc(src: string, projectSlug?: string, categorySlug?: string): string {
  if (!src || !projectSlug || ABSOLUTE_SRC.test(src)) return src;

  // A query string or fragment is carried over verbatim; only the path part
  // takes part in the ../ resolution below.
  const cut = src.search(/[?#]/);
  const path = cut === -1 ? src : src.slice(0, cut);
  const suffix = cut === -1 ? "" : src.slice(cut);

  // Resolved against the PAGE's directory -- which is the category
  // directory, since a page is content/<project>/<category>/<page>.md.
  const segments: string[] = categorySlug ? [categorySlug] : [];
  for (const part of path.split("/")) {
    if (part === "" || part === ".") continue;
    if (part !== "..") {
      segments.push(part);
      continue;
    }
    // Popping past the project directory means the author pointed at
    // something outside their own project. The server would 404 it anyway;
    // leaving the src untouched makes it visibly broken in the editor
    // preview instead of quietly pointing somewhere unexpected.
    if (segments.length === 0) return src;
    segments.pop();
  }

  // encodeURI, not encodeURIComponent: it escapes a literal space but
  // leaves an already percent-encoded name (`my%20shot.png`, which is how
  // Markdown has to spell one) alone instead of double-encoding it.
  return `/api/public/assets/${encodeURIComponent(projectSlug)}/${encodeURI(segments.join("/"))}${suffix}`;
}
