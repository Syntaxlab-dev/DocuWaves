import { useEffect, useRef, useState } from "react";
import { api, type PresenceEntry } from "@/lib/api";

const BEAT_MS = 20_000;

/** One id per browser tab and editor session -- the backend tells "you, in
 *  another tab" apart from "somebody else" by it. */
function newTabId(): string {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Math.random());
  return `tab-${random.replace(/[^A-Za-z0-9]/g, "").slice(0, 32)}`;
}

/**
 * Who else has this page open in the editor (backend
 * services/editing_presence.py). An account that may edit announces itself
 * with a heartbeat -- every 20 s, and at once when the unsaved-changes state
 * flips -- and leaves when the editor closes or the tab goes away. A
 * read-only account only looks: it is not editing, so it says nothing.
 */
export function useEditingPresence(pageId: number | null, dirty: boolean, announce: boolean): PresenceEntry[] {
  const tab = useRef(newTabId()).current;
  const [others, setOthers] = useState<PresenceEntry[]>([]);
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;

  useEffect(() => {
    setOthers([]);
    if (pageId === null) return;
    let alive = true;
    const beat = () => {
      const call = announce ? api.adminPresenceBeat(pageId, tab, dirtyRef.current) : api.adminPresenceRead(pageId, tab);
      call.then((r) => alive && setOthers(r.others)).catch(() => {});
    };
    beat();
    const timer = window.setInterval(beat, BEAT_MS);
    const leave = () => {
      if (announce) api.adminPresenceLeave(pageId, tab).catch(() => {});
    };
    window.addEventListener("pagehide", leave);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener("pagehide", leave);
      leave();
    };
  }, [pageId, announce, tab]);

  // The other side should learn about unsaved changes now, not in 20 s --
  // but only on a real change; opening the page already sent a heartbeat.
  const sentDirty = useRef(dirty);
  useEffect(() => {
    if (pageId === null || !announce || sentDirty.current === dirty) return;
    sentDirty.current = dirty;
    api.adminPresenceBeat(pageId, tab, dirty).then((r) => setOthers(r.others)).catch(() => {});
  }, [dirty, pageId, announce, tab]);

  return others;
}
