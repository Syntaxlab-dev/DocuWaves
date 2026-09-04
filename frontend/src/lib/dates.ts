/**
 * "2026-08-31" as the reader's own locale spells a date.
 *
 * Built from the parts rather than handed to `new Date(iso)`: that parses a
 * bare date as UTC midnight, which renders as the PREVIOUS DAY for every
 * reader west of Greenwich. A "last updated" line that is a day off is worse
 * than none, and a preview link's expiry date that is a day early is worse
 * still.
 *
 * An unparseable value is shown as it came, which is also what happens if a
 * backend ever answers with something that isn't a date.
 *
 * Its own module rather than a copy per view: three places render a bare
 * YYYY-MM-DD now (the last-updated line, the review note, a preview link's
 * expiry), and a second implementation of this is a second chance to
 * reintroduce the off-by-one.
 */
export function formatIsoDate(iso: string, locale: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  if (!year || !month || !day) return iso;
  return new Date(year, month - 1, day).toLocaleDateString(locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}
