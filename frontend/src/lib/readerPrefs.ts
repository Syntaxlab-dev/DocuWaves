// How a reader likes to read: text size and line width, remembered in this
// browser only (theme.ts's guarded storage), applied as attributes on <html>
// that index.css turns into sizes, so nothing re-renders to apply them.
import { useSyncExternalStore } from "react";
import { readStored, writeStored } from "@/lib/theme";

export type ReaderSize = "s" | "m" | "l";
export type ReaderWidth = "full" | "narrow";
export interface ReaderPrefs {
  size: ReaderSize;
  width: ReaderWidth;
}

const KEY = "docuwaves-reader";
const listeners = new Set<() => void>();

function load(): ReaderPrefs {
  try {
    const raw = JSON.parse(readStored(KEY) ?? "{}") as Partial<ReaderPrefs>;
    return {
      size: raw.size === "s" || raw.size === "l" ? raw.size : "m",
      width: raw.width === "narrow" ? "narrow" : "full",
    };
  } catch {
    return { size: "m", width: "full" };
  }
}

let current = load();

export function applyReaderPrefs(prefs: ReaderPrefs = current): void {
  const root = document.documentElement;
  root.dataset.readerSize = prefs.size;
  root.dataset.readerWidth = prefs.width;
}

export function setReaderPrefs(next: Partial<ReaderPrefs>): void {
  current = { ...current, ...next };
  writeStored(KEY, JSON.stringify(current));
  applyReaderPrefs(current);
  listeners.forEach((listener) => listener());
}

export function useReaderPrefs(): ReaderPrefs {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
  );
}
