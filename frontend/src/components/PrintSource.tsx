import { useMemo } from "react";
import qrcode from "qrcode-generator";
import { useI18n } from "@/lib/i18n";

/** The page's address as a QR code, so a printout can be scanned back to the
 *  live version rather than retyped.
 *
 *  Built as an SVG path string rather than a canvas or an <img>: it has to
 *  survive being printed at whatever DPI the printer runs, and it must not
 *  depend on a network round trip -- a QR code fetched from a rendering
 *  service would be the one thing on an offline instance's page that phones
 *  home.
 *
 *  Error correction level M, which tolerates roughly 15% damage. A printout
 *  gets folded, photocopied and coffee-stained, and the size cost over the
 *  lowest level is a few modules. */
function QrPath(url: string): { d: string; size: number } | null {
  try {
    // Type number 0 = "pick the smallest that fits".
    const qr = qrcode(0, "M");
    qr.addData(url);
    qr.make();
    const count = qr.getModuleCount();
    const parts: string[] = [];
    for (let row = 0; row < count; row++) {
      for (let col = 0; col < count; col++) {
        if (qr.isDark(row, col)) parts.push(`M${col} ${row}h1v1h-1z`);
      }
    }
    return { d: parts.join(""), size: count };
  } catch {
    // A URL too long for any QR version, or anything else the encoder
    // refuses. The address is printed as text right beside this, so losing
    // the code costs nothing that matters.
    return null;
  }
}

/**
 * Where a printout came from, and when it was taken.
 *
 * Only ever visible on paper (see `.print-source` in index.css). A printed
 * page otherwise carries no address at all: whoever finds it on a desk in six
 * months cannot get back to the live version, and cannot tell whether what
 * they are reading is still true. The date is the second half of that -- a
 * documentation page is a moving target, and a printout is a photograph of
 * one moment of it.
 *
 * Read from `window.location` rather than from any state: the address bar is
 * the one thing guaranteed to be the address the reader actually used, proxy
 * and language prefix included.
 */
export function PrintSource({ updated }: { updated?: string }) {
  const { t, lang } = useI18n();
  const url = typeof window === "undefined" ? "" : window.location.href;
  const printed = new Date().toLocaleDateString(lang === "de" ? "de-DE" : "en-GB");
  const qr = useMemo(() => (url ? QrPath(url) : null), [url]);

  return (
    <div className="print-source" aria-hidden="true">
      {qr && (
        <svg
          className="print-qr"
          viewBox={`0 0 ${qr.size} ${qr.size}`}
          width="72"
          height="72"
          role="img"
          aria-hidden="true"
        >
          {/* An explicit white ground: a QR code needs its quiet zone and its
              contrast, and a transparent one over coloured paper is a code
              no scanner reads. */}
          <rect width={qr.size} height={qr.size} fill="#fff" />
          <path d={qr.d} fill="#000" shapeRendering="crispEdges" />
        </svg>
      )}
      <div>
        <div>{url}</div>
        <div>
          {t("print.printedOn")} {printed}
          {updated ? ` · ${t("print.lastUpdated")} ${updated}` : ""}
        </div>
      </div>
    </div>
  );
}
