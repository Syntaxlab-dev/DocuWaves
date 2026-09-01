import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { VersionInfo } from "@/lib/api";
import { useContentLang } from "@/lib/lang";

/**
 * The documentation VERSION a reader is currently in, taken from the URL:
 *
 *     /de/p/cachepanel/v2.0/pages/installation
 *
 * The version segment is OPTIONAL and absent for the project's default
 * version -- which is what keeps every link that existed before a project
 * was versioned pointing at exactly the same page. A project with no
 * `_versions.yml` has no versions at all: `info` is null there, nothing
 * below renders anything, and no URL ever grows a segment.
 *
 * This lives in a context rather than being derived from the URL where it
 * is needed, because the two things that have to know about versions -- the
 * switcher in the header and the "you are reading an old version" banner --
 * sit outside the view that fetched the data. The docs views report what
 * they loaded (useReportProjectVersion); the header and the banner read it
 * back.
 *
 * `tail` is what comes after the version segment (""/"/c/x"/"/pages/y"),
 * reported by the view rather than reconstructed from the pathname here:
 * the view already knows exactly which slug it is showing, and string
 * surgery on a path that may or may not carry a language prefix and may or
 * may not carry a version prefix is the kind of thing that works until the
 * day a slug happens to look like a version id.
 */
export interface ProjectVersionState {
  projectSlug: string;
  /** The version being read: "" for an unversioned project. */
  version: string;
  /** Where in the project the reader is, after the version segment. */
  tail: string;
  /** Null until the view's data has arrived, and for unversioned projects. */
  info: VersionInfo | null;
}

const EMPTY: ProjectVersionState = { projectSlug: "", version: "", tail: "", info: null };

const ProjectVersionContext = createContext<{
  state: ProjectVersionState;
  report: (state: ProjectVersionState | null) => void;
}>({ state: EMPTY, report: () => {} });

export function ProjectVersionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ProjectVersionState>(EMPTY);
  // Stable across renders: the reporting effect below has it in its
  // dependency list, and a fresh identity each render would make that
  // effect re-run, set state, and re-run again forever.
  const report = useCallback((next: ProjectVersionState | null) => setState(next ?? EMPTY), []);
  const value = useMemo(() => ({ state, report }), [state, report]);
  return <ProjectVersionContext.Provider value={value}>{children}</ProjectVersionContext.Provider>;
}

export function useProjectVersion(): ProjectVersionState {
  return useContext(ProjectVersionContext).state;
}

/** Called by each docs view with what it is showing. */
export function useReportProjectVersion(state: ProjectVersionState) {
  const { report } = useContext(ProjectVersionContext);
  const { projectSlug, version, tail, info } = state;

  useEffect(() => {
    report({ projectSlug, version, tail, info });
  }, [report, projectSlug, version, tail, info]);

  // Clearing is its own effect, with empty dependencies, so it runs ONLY on
  // unmount: folded into the one above it would also fire between two docs
  // pages, blanking the header's switcher for a render on every click.
  // Leaving the last project's versions behind, on the other hand, would
  // put its switcher in the home page's header.
  useEffect(() => () => report(null), [report]);
}

/** The URL segment for a version: nothing for the default one (and nothing
 *  at all for an unversioned project), so the default version's addresses
 *  are the addresses the project always had. */
export function versionSegment(version: string, info: VersionInfo | null): string {
  if (!info || !version || version === info.default) return "";
  return `/${version}`;
}

/** A path inside a project, with the version segment where it belongs and
 *  the content-language prefix on the front. Every link into a project goes
 *  through this, so a reader in v2.0 can't be handed one link that quietly
 *  drops them back into current. */
export function useDocPath() {
  const { path } = useContentLang();
  const state = useProjectVersion();
  return (projectSlug: string, rest: string, version?: string, info?: VersionInfo | null): string => {
    // Defaults to whatever the reader is currently in -- right for every
    // link inside the docs they are reading, and overridable for the few
    // (the version switcher, a search hit) that deliberately point
    // somewhere else.
    const targetVersion = version === undefined ? state.version : version;
    const targetInfo = info === undefined ? state.info : info;
    return path(`/p/${projectSlug}${versionSegment(targetVersion, targetInfo)}${rest}`);
  };
}

/** What a typed version id will become on disk -- lowercased, spaces and
 *  anything unexpected turned into `-`. A DISPLAY mirror of the backend's
 *  content_versions.normalize_id(): the server is the authority and refuses
 *  anything this can't tidy (a leading `_` or `.`, a path separator) rather
 *  than repairing it, so all this has to get right is showing the user the
 *  directory name they are about to create before they create it.
 *
 *  Deliberately not slugify: the dot in `v2.0` is the name. */
export function normalizeVersionId(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^[-._]+|[-._]+$/g, "")
    .slice(0, 40);
}
