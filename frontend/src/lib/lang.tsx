import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { isUiLang, useI18n } from "@/lib/i18n";

/**
 * The CONTENT language a reader is currently reading in -- which language
 * the documentation itself is served in, taken from the URL:
 *
 *     /de/p/cachepanel/pages/installation
 *
 * Not the same thing as the interface language in lib/i18n.tsx, which
 * translates button labels and lives only in the browser. They are kept
 * separate deliberately (a reader can read German docs in an English UI on
 * a single-language instance), with one link between them: on a
 * multilingual instance the interface follows whatever content language the
 * reader picked, because there the two questions have the same answer --
 * see ContentLangProvider's effect below.
 *
 * On a single-language instance (`languages` empty, or holding one entry)
 * every value here collapses: no prefix is ever added to a path, no
 * redirect happens, no switcher renders, and every URL stays exactly what
 * it was before this file existed.
 *
 * The provider takes the language list as props rather than reading the
 * branding itself, so that lib/site.tsx can use this module (the tab title
 * needs the translated site name) without the two importing each other.
 */
export interface ContentLang {
  /** The language being read: the URL's prefix, or the site's default. "" on
   *  an instance that configured none. */
  lang: string;
  languages: string[];
  defaultLanguage: string;
  /** Whether the multi-language UI (prefix, switcher, notices) is on at all. */
  multilingual: boolean;
  /** False until the branding request has answered -- see lib/site.tsx. */
  ready: boolean;
  /** A public path with the language prefix this instance needs, if any:
   *  path("/p/x") is "/de/p/x" when multilingual, "/p/x" when not. Always
   *  used instead of a hand-built string, so adding a language to an
   *  instance can't leave a stale unprefixed link behind. */
  path: (to: string) => string;
}

const ContentLangContext = createContext<ContentLang>({
  lang: "",
  languages: [],
  defaultLanguage: "",
  multilingual: false,
  ready: false,
  path: (to) => to,
});

/** The admin UI is not a reading surface: it has no language prefix and
 *  must never be redirected into one. */
const ADMIN_PREFIX = "/admin";

function buildPath(to: string, lang: string, multilingual: boolean): string {
  if (!multilingual || !lang) return to;
  return to === "/" ? `/${lang}` : `/${lang}${to}`;
}

export function ContentLangProvider({
  languages,
  defaultLanguage,
  ready,
  children,
}: {
  languages: string[];
  defaultLanguage: string;
  ready: boolean;
  children: ReactNode;
}) {
  const { pathname, search, hash } = useLocation();
  const navigate = useNavigate();
  const { lang: uiLang, setLang: setUiLang } = useI18n();

  const multilingual = languages.length > 1;
  const firstSegment = pathname.split("/")[1] || "";
  // Only a CONFIGURED code counts as a prefix. Anything else is a normal
  // path segment (`/search`) or a wrong URL -- App.tsx's LanguageGate is
  // what turns the wrong-URL case into a 404, since only a route match
  // knows whether the segment was meant as a language at all.
  const urlLang = languages.includes(firstSegment) ? firstSegment : "";
  const lang = multilingual ? urlLang || defaultLanguage : defaultLanguage;
  // A two-letter first segment that ISN'T configured was clearly meant as a
  // language: `/fr/p/x` is a wrong URL, not an unprefixed one. Redirecting
  // it would produce `/de/fr/p/x` -- still a 404, but at an address that
  // now looks like it was the reader's own typo. Left alone, so the route
  // below matches `:lang` and LanguageGate answers 404 on the URL they
  // actually asked for.
  const looksLikeLanguage = /^[a-z]{2}$/.test(firstSegment);

  // An unprefixed URL is a perfectly good link (every link that existed
  // before this instance became multilingual is one) -- it just belongs at
  // the default language's address, so that a reader who then switches
  // language has somewhere to switch FROM. replace: true keeps the redirect
  // out of the back button's history.
  const needsPrefix =
    ready && multilingual && !urlLang && !looksLikeLanguage && !pathname.startsWith(ADMIN_PREFIX);
  useEffect(() => {
    if (!needsPrefix) return;
    navigate(`${buildPath(pathname, defaultLanguage, true)}${search}${hash}`, { replace: true });
  }, [needsPrefix, pathname, search, hash, defaultLanguage, navigate]);

  // <html lang> follows the content language too. The server already sets it
  // on the first response (backend/app/services/seo.py, which knows the
  // language the page was actually served in), and this is what keeps it
  // right afterwards: a reader who switches from German to English navigates
  // client-side, so without this the document would keep claiming to be in
  // the language it was first loaded in -- which is what a screen reader
  // pronounces it as and what a browser offers to translate it from.
  // Untouched on a single-language instance, where `lang` is "" and the
  // bundle's own value is the only statement there is.
  useEffect(() => {
    if (!lang) return;
    document.documentElement.lang = lang;
  }, [lang]);

  // The interface follows the content language on a multilingual instance,
  // for the languages the interface actually has words for -- a reader who
  // switched the docs to English should not be left with German buttons
  // around them. Instances whose content language has no dictionary keep
  // whatever interface language the reader had.
  useEffect(() => {
    if (!multilingual || !isUiLang(lang) || lang === uiLang) return;
    setUiLang(lang);
  }, [multilingual, lang, uiLang, setUiLang]);

  const value: ContentLang = {
    lang,
    languages,
    defaultLanguage,
    multilingual,
    ready,
    path: (to) => buildPath(to, lang, multilingual),
  };

  return <ContentLangContext.Provider value={value}>{children}</ContentLangContext.Provider>;
}

export function useContentLang() {
  return useContext(ContentLangContext);
}

/** The reader-facing name of a language code ("Deutsch", "German"), written
 *  in `inLang` -- Intl.DisplayNames is in every browser this app already
 *  requires, so no list of language names has to be shipped or maintained
 *  here. Falls back to the bare code if the runtime doesn't know it. */
export function languageName(code: string, inLang: string): string {
  try {
    return new Intl.DisplayNames([inLang || "en"], { type: "language" }).of(code) || code.toUpperCase();
  } catch {
    return code.toUpperCase();
  }
}
