import { useEffect, useState } from "react";

/**
 * The optional cover image on a project tile (home page) or a category tile
 * (project page). One component for both, so the two grids can never drift
 * into two different treatments of the same idea.
 *
 * The treatment, and why:
 *
 * - A **fixed 16:9 strip across the top of the card**, `object-fit: cover`,
 *   with the title and text staying exactly where they already are
 *   underneath. Text over the image would need a scrim over an image nobody
 *   here has seen -- a screenshot that happens to be pale in light mode and
 *   a logo on a dark background are both normal things to upload, and one
 *   overlay cannot be legible on both in both colour schemes. Under the
 *   image, the title is the same `--ink` on `--surface` it always was.
 * - **A tile with no cover renders exactly what it rendered before this
 *   existed**: this component returns null for a null URL, so nothing is
 *   added to the card at all -- not an empty box, not a placeholder.
 * - **Nothing jumps.** The aspect ratio reserves the strip's height before
 *   a single byte of the image has arrived, so a slow image never reflows
 *   the grid. Tiles with and without a cover sit in the same row at the
 *   same height because the card is already `h-full` in a stretch grid --
 *   the cover changes what fills the card, not how tall the row is.
 * - **Never a broken image.** The server only ever hands over a URL it just
 *   resolved to a real file, but a file can be deleted between that answer
 *   and this request -- so a load error removes the strip and the tile
 *   falls back to the no-cover layout, instead of leaving the browser's
 *   broken-image glyph in a card.
 * - `loading="lazy"` and `decoding="async"`: a home page can carry a dozen
 *   of these, and none of them is what the reader came for.
 *
 * `alt` is deliberately empty: the tile's own title is right underneath and
 * says the same thing, so announcing the cover would read the name twice.
 *
 * The image carries no corner radius of its own; the card it sits in adds
 * `overflow-hidden` (and only then, so a card with no cover keeps exactly
 * the classes it had) and clips it to the card's own rounding, which is one
 * radius rather than two that have to be kept equal.
 */
export function CoverImage({ url }: { url: string | null }) {
  const [failed, setFailed] = useState(false);

  // A different tile (or the same tile after its cover was changed) gets a
  // fresh chance to load -- without this, one failure would stick to the
  // component instance for as long as it stays mounted.
  useEffect(() => {
    setFailed(false);
  }, [url]);

  if (!url || failed) return null;

  return (
    <img
      src={url}
      alt=""
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      // The background matters for the honest cases rather than the broken
      // ones: a PNG with transparency, or an image whose aspect ratio the
      // crop doesn't quite fill, sits on the card's own tone instead of on
      // whatever is behind it.
      className="aspect-video w-full bg-[var(--surface-2)] object-cover"
    />
  );
}
