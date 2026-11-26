// An image in the text that opens large on click: a dark overlay with the
// image fitted to the screen, a second click (or the zoom button) shows it
// at full size to pan around in, Escape or a click beside it closes.
// Images inside a link keep being links.
import { createContext, useContext, useEffect, useRef, useState, type ImgHTMLAttributes } from "react";
import { createPortal } from "react-dom";
import { X, ZoomIn, ZoomOut } from "lucide-react";
import { useI18n } from "@/lib/i18n";

/** True inside a Markdown link: an image there is the link's content, and a
 *  button inside an <a> would be invalid markup, so it stays a plain image. */
export const InsideLink = createContext(false);

export function ZoomImage(props: ImgHTMLAttributes<HTMLImageElement>) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [zoomed, setZoomed] = useState(false);
  const closeButton = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const inLink = useContext(InsideLink);

  useEffect(() => {
    if (!open) return;
    closeButton.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const back = opener.current;
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      back?.focus();
    };
  }, [open]);

  const show = () => {
    setZoomed(false);
    setOpen(true);
  };

  return (
    <>
      {inLink ? (
        <img {...props} />
      ) : (
        <button
          type="button"
          ref={opener}
          className="zoom-trigger"
          onClick={show}
          aria-label={props.alt ? `${t("reader.enlarge")}: ${props.alt}` : t("reader.enlarge")}
        >
          <img {...props} />
        </button>
      )}
      {open &&
        createPortal(
          <div
            role="dialog"
            aria-modal="true"
            aria-label={props.alt || t("reader.enlarge")}
            className="lightbox fixed inset-0 z-[90] flex bg-black/85"
            onClick={(e) => e.target === e.currentTarget && setOpen(false)}
          >
            <div className="absolute top-3 right-3 z-10 flex gap-2">
              <button
                type="button"
                aria-label={zoomed ? t("reader.zoomOut") : t("reader.zoomIn")}
                onClick={() => setZoomed((z) => !z)}
                className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15 text-white hover:bg-white/25"
              >
                {zoomed ? <ZoomOut className="h-4 w-4" /> : <ZoomIn className="h-4 w-4" />}
              </button>
              <button
                ref={closeButton}
                type="button"
                aria-label={t("reader.close")}
                onClick={() => setOpen(false)}
                className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15 text-white hover:bg-white/25"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div
              className={`m-auto max-h-full max-w-full ${zoomed ? "overflow-auto" : "flex items-center justify-center p-6"}`}
              onClick={(e) => e.target === e.currentTarget && setOpen(false)}
            >
              <img
                src={props.src}
                alt={props.alt ?? ""}
                onClick={() => setZoomed((z) => !z)}
                className={
                  zoomed
                    ? "max-w-none cursor-zoom-out"
                    : "max-h-[calc(100vh-3rem)] max-w-[calc(100vw-3rem)] cursor-zoom-in rounded object-contain shadow-2xl"
                }
              />
            </div>
            {props.title && (
              <p className="pointer-events-none absolute inset-x-0 bottom-3 text-center text-sm text-white/85">{props.title}</p>
            )}
          </div>,
          document.body,
        )}
    </>
  );
}
