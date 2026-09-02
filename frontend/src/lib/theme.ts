import { useSyncExternalStore } from "react";

/**
 * Remembering the theme is a convenience, and it is not allowed to be more
 * than that: `window.localStorage` THROWS on the property access in a
 * browser told to block site data, and `setItem` throws when the quota is
 * full. Unguarded, either one takes the whole app down -- main.tsx calls
 * applyTheme() at module scope, before createRoot(), so the exception
 * happens before anything is rendered and the reader gets a blank page
 * rather than a site in the wrong colour scheme.
 */
function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // The preference simply isn't remembered for the next visit.
  }
}

export function getPreferredTheme(): "light" | "dark" {
  const stored = readStored("docuwaves-theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: "light" | "dark") {
  // The class first, the remembering second: applying the theme is the part
  // that must happen, storing it the part that is allowed to fail.
  document.documentElement.classList.toggle("dark", theme === "dark");
  writeStored("docuwaves-theme", theme);
}

/**
 * The current palette, as a value a component can re-render on.
 *
 * Everything else in this app themes itself in CSS -- `.dark` on <html>
 * swaps the custom properties and the whole page follows without a single
 * component knowing. A Mermaid diagram can't: it is an SVG whose colours are
 * baked in at render time by a library that has to be told which palette to
 * draw, so that one component genuinely needs to know, and needs to hear
 * about it the moment the reader flips the switch.
 *
 * Watching the class attribute rather than exposing a React state from the
 * two header toggles: applyTheme() is the single place the class is set, so
 * the observer sees every change (public site, admin, and any future caller)
 * with nothing to keep in sync. One observer is shared by all subscribers and
 * disconnected again when the last one goes -- a page can hold a dozen
 * diagrams, and a dozen observers on the same attribute would be a dozen
 * times the work for the same answer.
 */
const themeListeners = new Set<() => void>();
let themeObserver: MutationObserver | null = null;

function subscribeToTheme(listener: () => void): () => void {
  themeListeners.add(listener);
  if (!themeObserver) {
    themeObserver = new MutationObserver(() => {
      for (const notify of themeListeners) notify();
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  }
  return () => {
    themeListeners.delete(listener);
    if (themeListeners.size === 0) {
      themeObserver?.disconnect();
      themeObserver = null;
    }
  };
}

export function useIsDarkTheme(): boolean {
  return useSyncExternalStore(
    subscribeToTheme,
    () => document.documentElement.classList.contains("dark"),
    // Server snapshot: nothing here is server-rendered, but useSyncExternalStore
    // insists on the argument and "light" is what an unstyled document is.
    () => false,
  );
}

/** A CSS custom property's live value, or "" when it isn't set. Used to hand
 *  the current palette to something that can't read CSS itself. */
export function cssVariable(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** #rgb / #rrggbb only. The backend already rejects anything else before it
 *  reaches _site.yml, but this value is written straight into a CSS custom
 *  property on the live document, so it is checked again on the way in --
 *  the one thing a stylesheet must never accept is an unvalidated string
 *  from an API response. */
const HEX_COLOR = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const body = hex.slice(1);
  // #abc is shorthand for #aabbcc.
  const full = body.length === 3 ? body.replace(/./g, (c) => c + c) : body;
  return {
    r: parseInt(full.slice(0, 2), 16),
    g: parseInt(full.slice(2, 4), 16),
    b: parseInt(full.slice(4, 6), 16),
  };
}

/** The three custom properties a configured accent expands into, or null if
 *  the value isn't a usable colour. Separate from applying them so the admin
 *  form's live preview can scope the SAME derivation to one element (custom
 *  properties inherit) without touching the document the user is still
 *  editing in.
 *
 *  --accent-ink and --accent-soft are derived rather than configured: the
 *  first is the text colour that sits ON the accent (a light accent with the
 *  built-in white label would be unreadable), the second the translucent
 *  wash behind selected rows, which has to work over both the light and the
 *  dark surface -- an alpha of the accent itself does, a fixed tint doesn't. */
export function accentVariables(accent: string): Record<string, string> | null {
  if (!HEX_COLOR.test(accent)) return null;
  const { r, g, b } = hexToRgb(accent);
  // WCAG relative luminance, the same measure the contrast ratio is built
  // from -- a plain (r+g+b)/3 average calls yellow dark and blue light.
  const channel = (value: number) => {
    const c = value / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const luminance = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  return {
    "--accent": accent,
    "--accent-ink": luminance > 0.45 ? "#12161c" : "#ffffff",
    "--accent-soft": `rgba(${r}, ${g}, ${b}, 0.16)`,
  };
}

/** Applies (or clears) the configured accent colour for the whole document.
 *
 *  Set as inline custom properties on <html>, which beats both the `:root`
 *  and the `.dark` rule in index.css -- one accent for both colour schemes,
 *  chosen by whoever runs the instance, rather than the two built-in ones.
 *  Everything themed by --accent (links, the active sidebar item, the
 *  primary button, focus rings) follows automatically. No configured accent
 *  removes the properties again, which hands both modes back to index.css. */
export function applyAccent(accent: string) {
  const root = document.documentElement;
  const variables = accentVariables(accent);
  if (!variables) {
    root.style.removeProperty("--accent");
    root.style.removeProperty("--accent-ink");
    root.style.removeProperty("--accent-soft");
    return;
  }
  for (const [name, value] of Object.entries(variables)) root.style.setProperty(name, value);
}

const DEFAULT_FAVICON_HREF = "/favicon.svg";
const DEFAULT_FAVICON_TYPE = "image/svg+xml";

/** Points the tab icon at the configured favicon, or back at the shipped
 *  default when there isn't one. The type attribute is dropped for a custom
 *  file: index.html declares image/svg+xml, and leaving that on a .png would
 *  be a lie the browser has to work around. */
export function applyFavicon(url: string | null) {
  let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    document.head.appendChild(link);
  }
  if (url) {
    link.removeAttribute("type");
    link.href = url;
  } else {
    link.type = DEFAULT_FAVICON_TYPE;
    link.href = DEFAULT_FAVICON_HREF;
  }
}
