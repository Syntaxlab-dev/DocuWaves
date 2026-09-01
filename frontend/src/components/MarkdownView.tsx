import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

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
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
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
