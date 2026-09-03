import { useI18n } from "@/lib/i18n";

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

  return (
    <div className="print-source" aria-hidden="true">
      <div>{url}</div>
      <div>
        {t("print.printedOn")} {printed}
        {updated ? ` · ${t("print.lastUpdated")} ${updated}` : ""}
      </div>
    </div>
  );
}
