import { useMemo, useRef, type HTMLAttributes, type ReactNode } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import type { Element, ElementContent } from "hast";
import { CopyButton } from "@/components/CopyButton";
import { MermaidDiagram } from "@/components/MermaidDiagram";
import { collectHeadings, stripRedundantTitle } from "@/lib/headings";
import { useI18n } from "@/lib/i18n";

/**
 * Images are written in a page as a plain relative path
 * (`![Dashboard](../assets/dashboard.png)`) so the same .md still renders on
 * GitHub -- which means the browser can't load them as-is: relative to
 * /p/<project>/<page> they point at nothing. `projectSlug`, `versionDir` and
 * `categorySlug` are the page's location in the content repo, and are all
 * that's needed to turn such a path into the public asset URL.
 *
 * `versionDir` is the DIRECTORY name of the page's documentation version
 * ("current", "v2.0"), not the URL segment -- "" for an unversioned project,
 * where the path resolved is exactly the one it always was. It matters
 * because assets/ moves under the version with the pages that use it, so
 * v2.0's screenshot and current's are two different files reached by the
 * same `../assets/x.png`.
 *
 * All three are optional: without them (nothing renders MarkdownView that
 * way today, but a future caller might) relative images are simply left
 * alone rather than rewritten into a wrong URL.
 *
 * Heading anchors, code-block copy buttons and Mermaid diagrams need no props
 * at all, so the admin editor's preview pane gets them too without knowing
 * about them.
 */
export function MarkdownView({
  content,
  projectSlug,
  categorySlug,
  versionDir,
  title,
}: {
  content: string;
  projectSlug?: string;
  categorySlug?: string;
  versionDir?: string;
  /** The page's own title, already shown above the body. When the Markdown
   *  opens by repeating it as an `# H1`, that copy is dropped -- see
   *  stripRedundantTitle(). */
  title?: string;
}) {
  const { t } = useI18n();

  // Writing `# Installation` at the top of a page whose title is already
  // "Installation" is the normal thing to do -- it is what every Markdown
  // file outside this CMS looks like, it is what a pasted README looks
  // like, and it is how the file reads on GitHub, where nothing prints the
  // frontmatter title. So the duplicate is dropped here rather than being
  // something authors have to know about and remove by hand.
  const body = useMemo(() => stripRedundantTitle(content, title), [content, title]);

  // Keyed by source line, see lib/headings.ts for why that and not a
  // render-order counter.
  const headingIds = useMemo(() => {
    const byLine = new Map<number, string>();
    for (const heading of collectHeadings(body)) byLine.set(heading.line, heading.id);
    return byLine;
  }, [body]);

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        // plainText: "mermaid" is not a highlight.js language, it's a
        // diagram. Told plainly, the highlighter leaves the block completely
        // alone -- no `hljs` class, no spans -- which keeps its source in one
        // piece for MermaidDiagram and makes the fallback shown when a
        // diagram doesn't parse look like the plain block it is. Without it
        // rehype-highlight instead emits a "not registered" warning per
        // block, per render pass.
        rehypePlugins={[[rehypeHighlight, { plainText: ["mermaid"] }]]}
        urlTransform={urlTransform}
        components={{
          // `node` is react-markdown's own hast node -- destructured out
          // (and never used) purely so the spread below doesn't put it on
          // the DOM element, which React would warn about.
          img({ node, src, alt, ...props }) {
            void node;
            const resolved = resolveImageSrc(typeof src === "string" ? src : "", projectSlug, categorySlug, versionDir);
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
            // A ```mermaid block is a picture, not code -- everything else
            // stays the fenced block it always was.
            const diagram = mermaidSource(node);
            if (diagram !== null) return <MermaidDiagram code={diagram} />;
            return <CodeBlock {...props}>{children}</CodeBlock>;
          },
        }}
      >
        {body}
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
  const preRef = useRef<HTMLPreElement>(null);

  return (
    <div className="code-block">
      <pre ref={preRef} {...props}>
        {children}
      </pre>
      {/* textContent of the rendered <pre>, not the Markdown source: by this
          point rehype-highlight has split the code into nested <span>s, and
          the DOM is where the block's plain text still exists in one piece. */}
      <CopyButton getText={() => preRef.current?.textContent ?? ""} />
    </div>
  );
}

/**
 * The source of a ```mermaid fenced block, or null for every other `<pre>`.
 *
 * Read off the hast node rather than out of the rendered React children: by
 * the time `pre` is called those are React elements, and digging the text
 * back out of them would mean knowing how the highlighter nested its spans.
 * The hast node is the Markdown as it was parsed, which is exactly the string
 * mermaid has to be handed -- fence indentation, blank lines and all.
 */
function mermaidSource(node?: Element): string | null {
  const code = node?.children.find((child) => child.type === "element");
  if (code?.type !== "element" || code.tagName !== "code") return null;
  const className = code.properties?.className;
  if (!Array.isArray(className) || !className.includes("language-mermaid")) return null;
  return nodeText(code);
}

/** All the text under a hast node, in order. Recursive rather than reading
 *  the one child a fenced block normally has: nothing then depends on
 *  whatever the rehype plugins ahead of this did or didn't wrap it in. */
function nodeText(node: ElementContent): string {
  if (node.type === "text") return node.value;
  if (node.type === "element") return node.children.map(nodeText).join("");
  return "";
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

function resolveImageSrc(src: string, projectSlug?: string, categorySlug?: string, versionDir?: string): string {
  if (!src || !projectSlug || ABSOLUTE_SRC.test(src)) return src;

  // A query string or fragment is carried over verbatim; only the path part
  // takes part in the ../ resolution below.
  const cut = src.search(/[?#]/);
  const path = cut === -1 ? src : src.slice(0, cut);
  const suffix = cut === -1 ? "" : src.slice(cut);

  // Resolved against the PAGE's directory -- the category directory, one
  // level below the version's when the project has one, since a page is
  // content/<project>/[<version>/]<category>/<page>.md. Popping past the
  // project directory (not past the version's) is what stays "outside your
  // own project", which is also exactly where the server's own containment
  // check draws the line.
  const segments: string[] = [versionDir, categorySlug].filter((part): part is string => Boolean(part));
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
