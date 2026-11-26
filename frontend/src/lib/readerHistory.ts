// "Recently read" and bookmarks: kept in this browser only (theme.ts's
// guarded storage), never sent anywhere. A reader's reading list is theirs;
// an account to keep it would be a much bigger thing than this is worth.
import { useSyncExternalStore } from "react";
import { readStored, writeStored } from "@/lib/theme";

export interface ReadEntry {
  /** The address it was read at, version and language prefix included, so
   *  going back lands on exactly what was read. Also the identity. */
  path: string;
  title: string;
  /** "Project › Category", for telling apart two pages called "Setup". */
  context: string;
  /** ms since epoch. */
  at: number;
}

const HISTORY_KEY = "docuwaves-history";
const BOOKMARKS_KEY = "docuwaves-bookmarks";
/** Enough to find yesterday's page again; more is an archive nobody asked for. */
export const HISTORY_SIZE = 8;
const BOOKMARKS_SIZE = 50;

function load(key: string): ReadEntry[] {
  try {
    const raw = JSON.parse(readStored(key) ?? "[]");
    if (!Array.isArray(raw)) return [];
    return raw.filter(
      (e): e is ReadEntry =>
        e && typeof e.path === "string" && e.path.startsWith("/") && typeof e.title === "string",
    );
  } catch {
    return [];
  }
}

const state = { history: load(HISTORY_KEY), bookmarks: load(BOOKMARKS_KEY) };
let snapshot = { ...state };
const listeners = new Set<() => void>();

function publish() {
  snapshot = { ...state };
  writeStored(HISTORY_KEY, JSON.stringify(state.history));
  writeStored(BOOKMARKS_KEY, JSON.stringify(state.bookmarks));
  listeners.forEach((listener) => listener());
}

/** Newest first, one entry per address, the list capped. */
export function withEntry(list: ReadEntry[], entry: ReadEntry, cap: number): ReadEntry[] {
  return [entry, ...list.filter((e) => e.path !== entry.path)].slice(0, cap);
}

export function recordRead(entry: Omit<ReadEntry, "at">): void {
  const latest = state.history[0];
  // A reload of the page being read changes nothing worth a write.
  if (latest && latest.path === entry.path && latest.title === entry.title) return;
  state.history = withEntry(state.history, { ...entry, at: Date.now() }, HISTORY_SIZE);
  publish();
}

export function toggleBookmark(entry: Omit<ReadEntry, "at">): boolean {
  const had = state.bookmarks.some((e) => e.path === entry.path);
  state.bookmarks = had
    ? state.bookmarks.filter((e) => e.path !== entry.path)
    : withEntry(state.bookmarks, { ...entry, at: Date.now() }, BOOKMARKS_SIZE);
  publish();
  return !had;
}

export function clearHistory(): void {
  state.history = [];
  publish();
}

export function useReaderHistory(): { history: ReadEntry[]; bookmarks: ReadEntry[] } {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => snapshot,
  );
}
