/**
 * Unsaved editor text, kept in the browser until it is saved.
 *
 * The page editor holds the Markdown being written in React state, and
 * component state is gone the moment anything unmounts it: a closed tab, a
 * reload, an accidental navigation, a browser crash, a session that expired
 * halfway through a long page. None of those are unusual while writing
 * documentation, and all of them used to mean retyping.
 *
 * What this is NOT: a second source of truth. The content repo is the only
 * thing that stores documentation (see the README) -- a draft here is a
 * private scratch copy in one browser, never uploaded, never shown to a
 * reader, and never restored without the author saying so. On reopening a
 * page the editor loads what the server has, exactly as it always did, and
 * merely OFFERS the draft beside it.
 *
 * Three decisions worth spelling out:
 *
 * 1. THE KEY IDENTIFIES WHAT IS BEING EDITED, all four parts of it: project,
 *    page, language and documentation version. A page's German and English
 *    files are separate files with separate text (and separate histories),
 *    and so is the same page in `current` and in a frozen `v2.0` -- one key
 *    per file is what stops a draft from surfacing under the wrong tab.
 *
 * 2. STALENESS IS DETECTED AGAINST THE TEXT, not against a timestamp. A
 *    draft can easily be older than what the server now holds (a colleague
 *    edited the page, or the same author saved it from another browser), and
 *    offering it as though it were the newer text is how work gets silently
 *    overwritten. `base` is a fingerprint of the server's text at the moment
 *    the draft was started; if the server's text no longer fingerprints the
 *    same, the page moved underneath the draft and the editor says so
 *    instead of offering a plain restore. Page.updated_at would have been
 *    the obvious signal and is deliberately not used: it is a column in the
 *    rebuildable search index, so it moves whenever the index is rebuilt and
 *    would call every draft stale after an ordinary "Sync now".
 *
 * 3. EVERY ACCESS IS WRAPPED. Reading `window.localStorage` at all throws in
 *    a browser configured to block site data, and writing throws when the
 *    quota is full -- both are real, and neither is a reason for the editor
 *    to stop working. Nothing in here ever propagates an exception: the
 *    worst case is an editor with no draft support, which is the editor as
 *    it was before this file existed.
 */

/** Everything a draft is. Deliberately only the two things the author has in
 *  front of them and would have to retype -- not the published flag, not the
 *  category, not anything that came from the server and isn't being edited.
 *  Browser storage is readable by anything running on this origin, so the
 *  rule is that nothing lands here that the author isn't already looking at
 *  in the editor. */
export interface PageDraft {
  /** The Markdown body as the author last left it. */
  text: string;
  /** ...and the title above it, which is unsaved state just the same. */
  title: string;
  /** When it was written, epoch ms -- shown to the author, and what the
   *  expiry sweep below measures. */
  savedAt: number;
  /** Fingerprint of the SERVER's text when this draft was started; see (2). */
  base: string;
}

/** Version prefix in the key, so a future change to the stored shape can
 *  simply stop reading the old one instead of having to migrate drafts that
 *  are, by their nature, days old at most. */
const PREFIX = "docuwaves:draft:v1:";

/** Drafts expire after two weeks. Long enough that a page picked back up
 *  after a holiday still has its text, short enough that a browser doesn't
 *  accumulate the drafts of every page anyone ever half-wrote on it. The
 *  sweep runs when the editor opens -- there is no background job in a
 *  browser tab, and the editor opening is the only moment this matters. */
const MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000;

/** Turned off for the rest of the session once a write has failed for a
 *  reason retrying cannot fix. Without it a full quota would mean a failed
 *  write attempt on every debounce tick, forever, for nothing. */
let writable = true;

function store(): Storage | null {
  try {
    // The property access itself is what throws in a browser with site data
    // blocked, so it has to be inside the try -- and a real read is what
    // proves the object is usable rather than merely present.
    const storage = window.localStorage;
    storage.getItem(PREFIX);
    return storage;
  } catch {
    return null;
  }
}

/** Whether drafts work in this browser at all -- the editor asks so it can
 *  word its "unsaved changes" warning honestly rather than promising a draft
 *  that will never be written. */
export function draftsAvailable(): boolean {
  return writable && store() !== null;
}

/** What identifies the file being edited. `page` is the page's slug, or
 *  `new:<category id>` for one that has never been saved and therefore has
 *  no slug yet -- a category can only have one unsaved new page open at a
 *  time, and a slug can never contain a colon, so the two namespaces cannot
 *  collide. */
export function draftKey(parts: {
  project: string;
  version: string;
  page: string;
  language: string;
}): string {
  return (
    PREFIX +
    [parts.project, parts.version || "-", parts.page, parts.language || "-"]
      .map(encodeURIComponent)
      .join("/")
  );
}

/** A short, stable fingerprint of a string (djb2). Stored instead of the
 *  server's text itself: it answers the only question asked of it -- "is
 *  this still the text the draft was started from?" -- in a few bytes rather
 *  than by keeping a second copy of every page in browser storage. A
 *  collision would show a plain restore offer where a stale warning was due,
 *  which is why the length is part of it too. */
export function fingerprint(text: string): string {
  let hash = 5381;
  for (let i = 0; i < text.length; i += 1) hash = ((hash * 33) ^ text.charCodeAt(i)) >>> 0;
  return `${text.length.toString(36)}-${hash.toString(36)}`;
}

export function readDraft(key: string): PageDraft | null {
  const storage = store();
  if (!storage) return null;
  try {
    const raw = storage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PageDraft>;
    // Anything that isn't the shape written below is treated as absent
    // rather than repaired: a draft is one browser's scratch copy, and the
    // cost of dropping a malformed one is far below the cost of restoring
    // half of it into a page.
    if (typeof parsed.text !== "string" || typeof parsed.savedAt !== "number") return null;
    if (Date.now() - parsed.savedAt > MAX_AGE_MS) {
      remove(storage, key);
      return null;
    }
    return {
      text: parsed.text,
      title: typeof parsed.title === "string" ? parsed.title : "",
      savedAt: parsed.savedAt,
      base: typeof parsed.base === "string" ? parsed.base : "",
    };
  } catch {
    return null;
  }
}

export function writeDraft(key: string, draft: PageDraft): void {
  if (!writable) return;
  const storage = store();
  if (!storage) return;
  const payload = JSON.stringify(draft);
  try {
    storage.setItem(key, payload);
  } catch {
    // Out of quota, most likely. One retry, after throwing away every draft
    // that isn't this one -- the page in front of the author is worth more
    // than every page they are not looking at. Still failing means this
    // browser cannot hold drafts at all; stop trying for the session.
    try {
      sweepDrafts({ keepKey: key, all: true });
      storage.setItem(key, payload);
    } catch {
      writable = false;
    }
  }
}

export function clearDraft(key: string): void {
  const storage = store();
  if (storage) remove(storage, key);
}

function remove(storage: Storage, key: string): void {
  try {
    storage.removeItem(key);
  } catch {
    // Nothing to do about it, and nothing that depends on it having worked.
  }
}

/** Drops expired drafts (or, with `all`, every draft but one). Called when
 *  the editor opens, which is both often enough to keep the store small and
 *  the only moment a browser tab is definitely looking at this feature. */
export function sweepDrafts(options: { keepKey?: string; all?: boolean } = {}): void {
  const storage = store();
  if (!storage) return;
  try {
    const doomed: string[] = [];
    for (let i = 0; i < storage.length; i += 1) {
      const key = storage.key(i);
      if (!key || !key.startsWith(PREFIX) || key === options.keepKey) continue;
      if (options.all) {
        doomed.push(key);
        continue;
      }
      const raw = storage.getItem(key);
      let savedAt = 0;
      try {
        savedAt = (JSON.parse(raw ?? "") as Partial<PageDraft>).savedAt ?? 0;
      } catch {
        // Unparseable: it can never be restored, so it is only taking space.
      }
      if (Date.now() - savedAt > MAX_AGE_MS) doomed.push(key);
    }
    // Collected first, deleted after: removeItem while iterating by index
    // renumbers the keys behind it and would skip every second match.
    for (const key of doomed) remove(storage, key);
  } catch {
    // A storage that throws mid-sweep is a storage with no usable drafts in
    // it; the editor carries on without them.
  }
}
