// The page editor: visual or Markdown, drafts kept in the browser, pasted images.
// Split out of pages/AdminApp.tsx, which keeps the layout and state.
import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
} from "react";
import { toast } from "sonner";
import {
  AlertTriangle,
  Eye,
  EyeOff,
  FileClock,
  GitBranch,
  ImagePlus,
  RotateCcw,
  History,
  Trash2,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { MarkdownView, resolveImageSrc } from "@/components/MarkdownView";
import type { VisualEditorHandle } from "@/components/visual/VisualEditor";
import { MarkdownCheatSheet } from "@/components/MarkdownCheatSheet";
import { PresenceBanner } from "@/components/PresenceBanner";
import { ReviewPanel } from "@/components/ReviewWorkflow";
import { useEditingPresence } from "@/lib/presence";
import {
  api,
  ApiError,
  type Category,
  type PageTemplate,
  type ReviewState,
} from "@/lib/api";
import { usePermissions } from "@/lib/auth";
import {
  clearDraft,
  draftKey,
  draftsAvailable,
  fingerprint,
  readDraft,
  sweepDrafts,
  writeDraft,
  type PageDraft,
} from "@/lib/drafts";
import { useI18n } from "@/lib/i18n";
import { languageName } from "@/lib/lang";
import { useSite } from "@/lib/site";
import { type EditorTarget } from "./PagesPanel";
import { ReviewNote, PreviewLinksPanel, HistoryPanel, ImagesPanel } from "./PageSidePanels";

// The visual editor (components/visual/), loaded only when somebody writes
// with it: ProseMirror is no business of the public site's bundle.
export const VisualEditor = lazy(() => import("@/components/visual/VisualEditor"));

export type EditorMode = "visual" | "markdown";

export const EDITOR_MODE_KEY = "docuwaves.editorMode";

/** The author's choice, per browser. Visual unless they chose Markdown. */
export function storedEditorMode(): EditorMode {
  try {
    return localStorage.getItem(EDITOR_MODE_KEY) === "markdown" ? "markdown" : "visual";
  } catch {
    return "visual";
  }
}

/** The extension an image pasted from the clipboard should get, by the MIME
 *  type the clipboard hands it over as. Exactly the types the content repo
 *  accepts (see the backend's content_assets.CONTENT_TYPES) -- anything else
 *  keeps whatever the browser called it and is refused by the server, which
 *  says so in its own words. */
export const PASTED_IMAGE_EXTENSIONS: Record<string, string> = {
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/gif": ".gif",
  "image/webp": ".webp",
  "image/avif": ".avif",
  "image/svg+xml": ".svg",
};

/**
 * What to call an image that arrived through the clipboard.
 *
 * A pasted screenshot has no filename worth keeping: browsers hand it over
 * as "image.png", or as nothing at all. Taking that at face value would fill
 * a project's assets/ folder with image.png, image-2.png, image-3.png -- a
 * set of names that says nothing about anything, in a directory people
 * browse in GitHub. A timestamp does say something: it reads as a date, it
 * sorts chronologically in the folder listing, and it is derived from the
 * moment of the paste rather than from a random id, so two screenshots taken
 * minutes apart stay distinguishable afterwards.
 *
 *     pasted-2026-09-02-143205.png
 *
 * The stem is already slug-shaped, so the server's slugify leaves it alone;
 * two pastes inside the same second get the server's -2, -3 suffix like any
 * other collision. The extension comes from the clipboard's own MIME type
 * rather than being assumed to be .png -- an image type this app doesn't
 * accept then reaches the server as itself and gets the server's honest
 * "unsupported type" answer instead of a .png that isn't one.
 */
export function pastedImageName(file: File, now: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  const stamp =
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}-` +
    `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  const dot = file.name.lastIndexOf(".");
  const extension = PASTED_IMAGE_EXTENSIONS[file.type] ?? (dot > 0 ? file.name.slice(dot) : "");
  return `pasted-${stamp}${extension}`;
}

/** How long typing has to stop before the draft is written. Long enough that
 *  a burst of typing is one write rather than one per character, short
 *  enough that a crash costs a few words rather than a paragraph. */
export const DRAFT_DEBOUNCE_MS = 800;

/**
 * One page, in one language at a time, with a tab per configured language.
 *
 * The tabs are the whole multi-language story here: a language the page
 * already exists in loads that translation, a language it doesn't exist in
 * yet opens an empty editor that will be SAVED UNDER THE SAME SLUG (see
 * PageInput.slug) -- which is what makes it a translation rather than a
 * second page that happens to say something similar. The slug itself is
 * never editable and never derived from a translated title; only the
 * default language's title steers it, on the backend.
 *
 * A single-language instance sees no tab strip at all: `languages` is empty
 * there, so the editor is exactly the one-language editor it always was.
 */
/** The preview as readers will see it: snippets and variables are filled in
 *  on the server (services/snippets.py), where the snippet files are. Until
 *  that answer arrives -- or if it can't, for a read-only account say -- the
 *  source is shown as it is, which is still the page. */
export function ResolvedPreview({
  content,
  title,
  projectSlug,
  categorySlug,
  version,
  language,
}: {
  content: string;
  title: string;
  projectSlug: string;
  categorySlug?: string;
  version: string;
  language: string;
}) {
  const [resolved, setResolved] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    setResolved(null);
    api
      .resolveMarkdown({ project_slug: projectSlug, version, language, markdown: content })
      .then((r) => current && setResolved(r.markdown))
      .catch(() => current && setResolved(content));
    return () => {
      current = false;
    };
  }, [content, projectSlug, version, language]);

  return (
    <MarkdownView
      content={resolved ?? content}
      title={title}
      projectSlug={projectSlug}
      categorySlug={categorySlug}
      versionDir={version}
    />
  );
}

export function PageEditor({
  target,
  projectSlug,
  categoryId,
  categories,
  version,
  readOnly,
  frozen,
  reviewRequired,
  onSaved,
  onDone,
}: {
  target: EditorTarget;
  projectSlug: string;
  categoryId: number;
  categories: Category[];
  /** Which documentation version this page belongs to: "" for a project
   *  with none, "current" or a frozen id otherwise. Also the directory the
   *  preview resolves `../assets/…` against. */
  version: string;
  /** The version is frozen: the editor reads it and offers no way to save.
   *  The API refuses the write too -- this is what stops anyone reaching
   *  for a button that would only fail. */
  readOnly: boolean;
  /** A frozen version specifically -- unlike `readOnly`, which is also a
   *  read-only ACCOUNT, and such an account may still review. */
  frozen: boolean;
  /** The project publishes through an approval (services/page_review.py). */
  reviewRequired: boolean;
  onSaved: () => void;
  onDone: () => void;
}) {
  const { t, lang: uiLang } = useI18n();
  const { site } = useSite();
  const multilingual = site.languages.length > 1;

  const [slug, setSlug] = useState(target.kind === "new" ? "" : target.slug);
  const [language, setLanguage] = useState(target.kind === "new" ? site.default_language : target.language);
  /** Which languages this page exists in, as the backend last told us --
   *  refreshed on every load and after every save, so a translation created
   *  here immediately becomes a normal tab. */
  const [existing, setExisting] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [targetCategoryId, setTargetCategoryId] = useState(categoryId);
  const [published, setPublished] = useState(false);
  /** Whether the page is live on the server -- the toggle above is what the
   *  next save will ask for. In a project that needs approval, a page that
   *  is not live cannot be switched on here: it goes live by approval. */
  const [livePublished, setLivePublished] = useState(false);
  const [review, setReview] = useState<ReviewState | null>(null);
  /** Docs-as-code: where this page's file can be changed instead. */
  const [sourceEditUrl, setSourceEditUrl] = useState("");
  const [tab, setTab] = useState<"edit" | "preview" | "history">("edit");
  const [saving, setSaving] = useState(false);
  const [loadedId, setLoadedId] = useState<number | null>(null);
  // The server's fingerprint of the page as loaded; sent back on save so a
  // save on top of someone else's newer change is refused, not silent.
  const [revision, setRevision] = useState("");
  const [dirty, setDirty] = useState(false);
  const { canWrite: accountCanWrite } = usePermissions();
  // Who else has this page open (services/editing_presence.py). Only an
  // account that may save announces itself; a frozen version or a
  // read-only account just sees who is there.
  const presence = useEditingPresence(loadedId, dirty, accountCanWrite && !readOnly);
  /** Bumped to re-run the load below when nothing about WHICH page is open
   *  has changed but its content has -- restoring an older version writes a
   *  new one straight into the content repo, so the text in this editor is
   *  stale the moment it succeeds. */
  const [reloadKey, setReloadKey] = useState(0);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  /** Visual or Markdown (see storedEditorMode), and whether THIS text can be
   *  edited visually without losing anything -- checked whenever a text
   *  arrives from somewhere other than the visual editor itself. */
  const [editorMode, setEditorMode] = useState<EditorMode>(storedEditorMode);
  const [visualCheck, setVisualCheck] = useState<"pending" | "ok" | "lossy">("pending");
  const [textArrived, setTextArrived] = useState(0);
  const visualRef = useRef<VisualEditorHandle>(null);
  /** A local draft of unsaved text found for this page, waiting to be
   *  restored or discarded, and whether the page has changed on the server
   *  since it was made. Held in state rather than re-read from storage on
   *  use: the author may well keep typing with the banner open, which
   *  overwrites the stored draft with their newer text -- the offer stays
   *  the snapshot it was when the page opened. */
  const [draftOffer, setDraftOffer] = useState<PageDraft | null>(null);
  const [draftStale, setDraftStale] = useState(false);
  /** Which upload of how many is in flight, or null when none is. The
   *  editor stays fully usable throughout -- an upload is a round trip to a
   *  git push, and blocking the textarea for it would interrupt exactly the
   *  sentence the screenshot is being pasted into. */
  const [uploading, setUploading] = useState<{ done: number; total: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  /** dragenter/dragleave fire for every child element the pointer crosses,
   *  so the drop target has to count them rather than believe the first
   *  leave -- otherwise it flickers off the moment the pointer moves from
   *  the textarea onto its own overlay. */
  const dragDepth = useRef(0);
  /** Bumped after an upload so the image panel below re-lists the project's
   *  assets: a file pasted into the textarea belongs in its thumbnails too. */
  const [assetsKey, setAssetsKey] = useState(0);
  /** The four page skeletons, for the language being written, or null until
   *  they have been asked for. Kept WITH the language they were fetched in:
   *  switching tabs has to fetch them again (a German page must not be
   *  started from English headings), and holding the code next to the list
   *  is what says whether the one in hand is still the right one. */
  const [templates, setTemplates] = useState<{ language: string; list: PageTemplate[] } | null>(null);
  /** The page's review note as the server last told us. Kept in state rather
   *  than read from a loaded page object, because a save can REMOVE it: the
   *  backend drops the note whenever the body changes, and the PUT answers
   *  with what the note is now. */
  const [reviewedBy, setReviewedBy] = useState("");
  const [reviewedAt, setReviewedAt] = useState("");
  /** Fingerprint of the text the SERVER last handed us. A draft records the
   *  one it was started from, and the two disagreeing is what says the page
   *  moved underneath the draft -- see lib/drafts.ts. */
  const serverBase = useRef("");

  // What identifies the file being edited, as far as a local draft is
  // concerned: project, page, language and documentation version, which is
  // exactly the set of things that pick out one .md file in the content
  // repo. A page that has never been saved has no slug to key on, so it is
  // keyed by the category it is being written in instead.
  const localDraftKey = draftKey({
    project: projectSlug,
    version,
    page: slug || `new:${categoryId}`,
    language,
  });

  // The page's own category, not the one it was opened from: the dropdown
  // above can move it, and a `../assets/x.png` in the body has to resolve
  // against wherever the page will actually be saved.
  const targetCategorySlug = categories.find((c) => c.id === targetCategoryId)?.slug;

  /**
   * The local draft for the file just loaded, offered or quietly dropped.
   *
   * Never applied on its own: what the editor shows after a load is what the
   * server has, and the draft sits above it as an offer with a date on it.
   * Silently preferring the draft would mean an author who saved from
   * another browser (or a colleague who edited the page in between) finding
   * their work replaced by older text they never asked for.
   */
  function offerDraft(key: string, serverTitle: string, serverText: string) {
    const base = fingerprint(serverText);
    serverBase.current = base;
    const draft = readOnly ? null : readDraft(key);
    setDraftOffer(draft);
    if (!draft) {
      setDraftStale(false);
      return;
    }
    if (draft.text === serverText && draft.title === serverTitle) {
      // The draft says exactly what the server says -- it was saved from
      // another tab, or restored and saved somewhere else. There is nothing
      // to offer, so it is dropped rather than shown as a decision.
      clearDraft(key);
      setDraftOffer(null);
      setDraftStale(false);
      return;
    }
    // The server's text is no longer the text this draft was written on top
    // of: someone else edited the page, or this author saved it from another
    // browser. That makes the draft the OLDER of the two, which is said out
    // loud rather than presented as a plain restore.
    setDraftStale(draft.base !== base);
  }

  useEffect(() => {
    let current = true;
    setTab("edit");
    setDirty(false);
    if (!slug) {
      // Brand-new page: nothing to load, and no other language to offer
      // until it has been saved once and has a slug of its own.
      setTitle(target.kind === "new" ? target.title ?? "" : "");
      // A draft written from a search gap (backend services/gap_drafts.py):
      // unsaved, so the editor treats it as a change from the start.
      const body = target.kind === "new" ? target.body ?? "" : "";
      setContent(body);
      if (body) setDirty(true);
      setTargetCategoryId(categoryId);
      setPublished(false);
      setLivePublished(false);
      setReview(null);
      setLoadedId(null);
      setRevision("");
      setExisting([]);
      setReviewedBy("");
      setReviewedAt("");
      offerDraft(localDraftKey, "", "");
      return;
    }
    api.adminFindPage(projectSlug, slug, language, version || undefined).then((page) => {
      if (!current) return;
      setExisting(page.languages);
      if (page.page) {
        setTitle(page.page.title);
        setContent(page.page.markdown_content);
        setTargetCategoryId(page.page.category_id);
        setPublished(page.page.published);
        setLivePublished(page.page.published);
        setReview(page.page.review ?? null);
        setSourceEditUrl(page.page.source_edit_url ?? "");
        setLoadedId(page.page.id);
        setRevision(page.page.revision ?? "");
        setReviewedBy(page.page.reviewed_by);
        setReviewedAt(page.page.reviewed_at);
        offerDraft(localDraftKey, page.page.title, page.page.markdown_content);
        setTextArrived((n) => n + 1);
      } else {
        // This language has no version yet: an empty editor, but on the
        // page's own slug and in its own category.
        setTitle("");
        setContent("");
        setPublished(false);
        setLivePublished(false);
        setReview(null);
        setLoadedId(null);
        setRevision("");
        setReviewedBy("");
        setReviewedAt("");
        offerDraft(localDraftKey, "", "");
      }
    });
    return () => {
      current = false;
    };
    // offerDraft closes over nothing that outlives this render, and
    // localDraftKey is derived from the identifiers already listed here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectSlug, slug, language, categoryId, version, reloadKey]);

  /**
   * The draft itself, written a short while after typing stops.
   *
   * Debounced rather than written on every keystroke: one storage write per
   * burst of typing costs nothing, one per character on a long page is a
   * JSON serialization of the whole document per key pressed. Nothing is
   * written until something has actually been changed (`dirty`), so merely
   * opening a page never stores a copy of it, and nothing at all is written
   * for a frozen version, which cannot be saved anyway.
   */
  useEffect(() => {
    if (readOnly || !dirty) return;
    const handle = setTimeout(() => {
      writeDraft(localDraftKey, { text: content, title, savedAt: Date.now(), base: serverBase.current });
    }, DRAFT_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [content, title, dirty, readOnly, localDraftKey]);

  /** Writes the pending draft *now*. The debounce above is a timer, and none
   *  of the moments this editor stops existing wait for timers: a closed
   *  tab, a language tab that reloads from the server, the editor being
   *  closed. Kept in a ref so the listener below always calls the current
   *  one without re-subscribing on every keystroke. */
  const flushDraft = useRef(() => {});
  flushDraft.current = () => {
    if (readOnly || !dirty) return;
    writeDraft(localDraftKey, { text: content, title, savedAt: Date.now(), base: serverBase.current });
  };

  useEffect(() => {
    // Old drafts are swept when the editor opens: a browser tab has no
    // background job, and this is the only moment anything here cares.
    sweepDrafts();
    const onHide = () => flushDraft.current();
    // pagehide rather than beforeunload: it also fires for a tab going into
    // the back/forward cache and for the way mobile browsers close one,
    // neither of which beforeunload reliably sees.
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      // Unmounting is the editor being closed or navigated away from --
      // precisely the case this whole thing exists for.
      flushDraft.current();
    };
  }, []);

  /** An empty page is the only page a template can start: applying one
   *  REPLACES the body, and doing that to text somebody has written would be
   *  the single most destructive button in this editor. So the picker is
   *  only fetched -- and only rendered -- while there is nothing to destroy,
   *  and it disappears the moment the first character is typed.
   *
   *  A failed fetch is swallowed on purpose. The templates are a convenience
   *  on top of a textarea that works perfectly without them; an error toast
   *  over a blank editor would be reporting a problem the author does not
   *  have. */
  const blank = content.trim() === "";
  /** Which language to write the templates in: the page's own content
   *  language when it has one, the interface language otherwise. An instance
   *  that never configured `languages:` writes its pages in SOME language
   *  and has no code to say which -- and on such an instance the person at
   *  the admin UI is the one writing them, so what their interface is set to
   *  is the best guess available. The endpoint treats it as a hint and falls
   *  back to English rather than refusing a code it doesn't know. */
  const templateLanguage = language || uiLang;
  useEffect(() => {
    if (readOnly || !blank || templates?.language === templateLanguage) return;
    let current = true;
    api
      .adminPageTemplates(templateLanguage)
      .then((result) => {
        if (current) setTemplates({ language: templateLanguage, list: result.templates });
      })
      .catch(() => {});
    return () => {
      current = false;
    };
  }, [blank, templateLanguage, readOnly, templates]);

  function applyTemplate(template: PageTemplate) {
    setContent(template.markdown);
    setDirty(true);
    setTab("edit");
    // Caret at the very top, on the title placeholder -- which is the first
    // thing every one of these templates asks to be replaced.
    focusAt(0);
  }

  // Visual editing only for a text it carries through unchanged (see
  // components/visual/milkdown.ts); anything else opens in Markdown, with
  // the reason above it, rather than losing a construct on the next save.
  useEffect(() => {
    if (editorMode !== "visual") return;
    let current = true;
    setVisualCheck("pending");
    import("@/components/visual/milkdown")
      .then(({ editableVisually }) => editableVisually(content))
      .then((ok) => current && setVisualCheck(ok ? "ok" : "lossy"))
      .catch(() => current && setVisualCheck("lossy"));
    return () => {
      current = false;
    };
    // Checked when a text ARRIVES (loaded, restored) or the mode changes --
    // not on every keystroke the visual editor itself produces.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editorMode, textArrived, slug, language]);

  function chooseEditorMode(mode: EditorMode) {
    setEditorMode(mode);
    try {
      localStorage.setItem(EDITOR_MODE_KEY, mode);
    } catch {
      // A browser that keeps nothing simply asks again next time.
    }
  }

  const visualActive = editorMode === "visual" && visualCheck === "ok";

  /** One image from the visual editor (pasted, dropped or picked): the same
   *  upload as everywhere else, answering the Markdown path to it. */
  async function uploadForVisual(file: File): Promise<string | null> {
    const named =
      !file.name || /^image\.\w+$/i.test(file.name)
        ? new File([file], pastedImageName(file, new Date()), { type: file.type })
        : file;
    setUploading({ done: 0, total: 1 });
    try {
      const asset = await api.adminUploadAsset(projectSlug, named, version || undefined);
      setAssetsKey((key) => key + 1);
      toast.success(t("admin.imageUploaded"));
      return asset.markdown_path;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
      return null;
    } finally {
      setUploading(null);
    }
  }

  /** The { } menu of the visual editor: this project's (and the whole
   *  site's) variables and snippets, for the version being edited. */
  async function loadInsertables() {
    const [own, site] = await Promise.all([
      api.adminListSnippets(projectSlug, version || ""),
      api.adminListSnippets("", ""),
    ]);
    const keys = (yaml: string) =>
      yaml
        .split("\n")
        .map((line) => /^([A-Za-z0-9_.-]+)\s*:/.exec(line)?.[1])
        .filter((name): name is string => Boolean(name));
    const variables = new Set(["project", ...(version ? ["version"] : []), ...keys(own.variables), ...keys(site.variables)]);
    const snippets = new Set([...own.snippets, ...site.snippets].map((s) => s.name));
    return { variables: [...variables].sort(), snippets: [...snippets].sort() };
  }

  function onVisualKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    // Formatting shortcuts are the visual editor's own; saving is the page's.
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      void onSave();
    }
  }

  function onRestoreDraft() {
    if (!draftOffer) return;
    setTitle(draftOffer.title);
    setContent(draftOffer.text);
    setDirty(true);
    setTab("edit");
    setTextArrived((n) => n + 1);
    setDraftOffer(null);
    setDraftStale(false);
    // Restored, not saved: the content repo still holds what it held, and
    // the Save button is still the thing that changes that.
    toast.success(t("admin.draftRestored"));
  }

  function onDiscardDraft() {
    clearDraft(localDraftKey);
    setDraftOffer(null);
    setDraftStale(false);
    toast.success(t("admin.draftDiscarded"));
  }

  function switchLanguage(code: string) {
    // Switching tabs reloads from the server, so unsaved text is about to
    // leave the screen. Whether that means it is LOST depends on whether
    // this browser can hold a draft -- so the warning says whichever of the
    // two is actually true here, rather than threatening a loss that no
    // longer happens (or promising a draft that will never be written).
    //
    // Its own string, not admin.deleteConfirm: that one says "Really delete
    // this? This can't be undone." -- which describes deleting a page, not
    // dropping an unsaved draft, and reads as if the tab click were about to
    // destroy the translation.
    if (code === language) return;
    if (dirty && !confirm(draftsAvailable() ? t("admin.switchLanguageDraftKept") : t("admin.discardDraftConfirm"))) {
      return;
    }
    // Written before the reload, or the debounce still pending would be
    // cancelled by it and the last few seconds of typing would be the one
    // thing the draft didn't keep.
    flushDraft.current();
    setLanguage(code);
  }

  async function onSave() {
    // In the visual editor the latest keystrokes may not have reached
    // `content` yet (see VisualEditorHandle.markdown): take the text from
    // the editor itself, and make it the editor's state too.
    const latestVisual = visualActive && tab === "edit" ? visualRef.current?.markdown() : null;
    const text = latestVisual ?? content;
    if (latestVisual != null && latestVisual !== content) setContent(latestVisual);
    setSaving(true);
    try {
      if (loadedId === null) {
        const created = await api.adminCreatePage({
          title,
          markdown_content: text,
          category_id: targetCategoryId,
          // Both only matter on a multilingual instance; the backend reads
          // an empty language as "the default" and an empty slug as "a new
          // page, derive it from the title".
          language,
          slug: slug || undefined,
        });
        // Not in a project that needs approval: a new page there is a
        // draft until somebody approves it.
        if (!reviewRequired) await api.adminPublishPage(created.id, published);
        setLoadedId(created.id);
        setSlug(created.slug);
        setExisting((codes) => (codes.includes(created.language) ? codes : [...codes, created.language]));
      } else {
        const input = { title, markdown_content: text, category_id: targetCategoryId, language };
        let saved;
        try {
          saved = await api.adminUpdatePage(loadedId, { ...input, base_revision: revision || undefined });
        } catch (err) {
          // Somebody else saved this page since it was opened. Ask rather
          // than decide: overwriting is safe to offer, because their version
          // stays in the page's history and can be restored from there.
          const changedMeanwhile =
            err instanceof ApiError && err.status === 409 && err.message === "page_changed";
          if (changedMeanwhile && window.confirm(t("admin.pageChangedConfirm"))) {
            saved = await api.adminUpdatePage(loadedId, input);
          } else {
            throw err;
          }
        }
        // saved.id, not loadedId: renaming the page moved its file, and the
        // row it had is gone. Publishing under the old id 404s on a save
        // that actually worked, and silently drops the published state the
        // author just toggled.
        // Asked only when it changes anything: re-publishing a live page is
        // a no-op, and in a project that needs approval a draft cannot be
        // switched on here at all (the toggle says so).
        if (published !== livePublished) await api.adminPublishPage(saved.id, published);
        setLivePublished(published);
        setLoadedId(saved.id);
        if (saved.review) setReview(saved.review);
        // May well be empty now: editing the body drops the review note.
        setReviewedBy(saved.reviewed_by);
        setReviewedAt(saved.reviewed_at);
        setRevision(saved.revision);
      }
      setDirty(false);
      // The text is in the content repo now, so the local copy of it has
      // nothing left to protect. Cleared under the key this render is using
      // -- for a page that was just created, that is still the `new:<id>`
      // key it was written under, not the slug it is about to get.
      clearDraft(localDraftKey);
      setDraftOffer(null);
      setDraftStale(false);
      // What was just saved is what the server now has, so a draft written
      // from here on is written on top of THIS text.
      serverBase.current = fingerprint(text);
      toast.success(reviewRequired && livePublished ? t("review.savedAsProposal") : t("admin.save"));
      // The list behind the editor is refreshed, but the editor stays open
      // on this page -- writing the other language is the very next thing
      // an author does after saving a translation.
      onSaved();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setSaving(false);
    }
  }

  /** Replaces [from, to) with `snippet`. A functional update, not
   *  `content.slice(...)`: a batch of uploads inserts several snippets in a
   *  row with an await between them, and each one has to build on the last
   *  rather than on the `content` its render closed over. */
  function replaceRange(from: number, to: number, snippet: string) {
    setContent((current) => {
      const start = Math.min(from, current.length);
      const end = Math.min(Math.max(to, start), current.length);
      return current.slice(0, start) + snippet + current.slice(end);
    });
    setDirty(true);
  }

  /** Puts the caret back where the text just inserted ends -- after React
   *  has re-rendered with the new value, or the controlled update would
   *  immediately overwrite it. */
  function focusAt(position: number) {
    requestAnimationFrame(() => {
      const el = editorRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(position, position);
    });
  }

  /** Where an insert goes: the current selection, or the end of the text
   *  when the textarea isn't mounted (the preview tab has no caret of its
   *  own to speak of). */
  function caretRange(): { from: number; to: number } {
    const el = editorRef.current;
    if (!el) return { from: content.length, to: content.length };
    return { from: el.selectionStart, to: el.selectionEnd };
  }

  function insertSnippet(snippet: string) {
    // Always land back on the Markdown tab first -- the textarea isn't
    // mounted while the preview is showing, so there'd be no cursor to
    // insert at and the snippet would silently go to the very end.
    setTab("edit");
    const { from, to } = caretRange();
    replaceRange(from, to, snippet);
    focusAt(from + snippet.length);
  }

  /** Wraps the selection in `before`/`after`, or -- with nothing selected --
   *  inserts the pair and leaves the caret between them, which is what makes
   *  Ctrl+B usable as "start typing bold" and not just "embolden this". */
  function wrapSelection(before: string, after = before) {
    const el = editorRef.current;
    if (!el || readOnly) return;
    const { from, to } = caretRange();
    const selected = content.slice(from, to);
    replaceRange(from, to, `${before}${selected}${after}`);
    requestAnimationFrame(() => {
      const target = editorRef.current;
      if (!target) return;
      target.focus();
      // Selection kept selected so the shortcut can be pressed twice to
      // undo itself; caret placed inside the markers when there was none.
      if (selected) target.setSelectionRange(from + before.length, from + before.length + selected.length);
      else target.setSelectionRange(from + before.length, from + before.length);
    });
  }

  /** The editor's keyboard shortcuts.
   *
   *  The set is deliberately the one every text field on the machine already
   *  uses -- bold, italic, link, and save. Anything more would be a second
   *  vocabulary to learn for a box that is, after all, plain Markdown. */
  function onEditorKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // metaKey on a Mac, ctrlKey everywhere else. Both are checked rather
    // than sniffing the platform, which gets an external keyboard wrong.
    if (!event.metaKey && !event.ctrlKey) return;
    const key = event.key.toLowerCase();
    const handlers: Record<string, () => void> = {
      b: () => wrapSelection("**"),
      i: () => wrapSelection("*"),
      e: () => wrapSelection("`"),
      k: () => {
        const { from, to } = caretRange();
        const selected = content.slice(from, to);
        replaceRange(from, to, `[${selected}](url)`);
        // Straight onto "url", the part that always has to be replaced.
        const start = from + selected.length + 3;
        requestAnimationFrame(() => {
          editorRef.current?.focus();
          editorRef.current?.setSelectionRange(start, start + 3);
        });
      },
      s: () => void onSave(),
    };
    const handler = handlers[key];
    if (!handler) return;
    // Before the handler: Ctrl+S otherwise opens the browser's own save
    // dialog over the page, and Ctrl+B toggles a bookmark sidebar.
    event.preventDefault();
    if (key !== "s" && readOnly) return;
    handler();
  }

  /**
   * Every image from one paste or one drop: uploaded in order, inserted in
   * order, at the caret the event happened at.
   *
   * The upload is the ordinary one -- the same endpoint, the same 10 MB
   * limit, the same magic-number and SVG screening the Insert image button
   * has always gone through, and the same commit-and-push into the content
   * repo. Nothing here validates an image itself: a second copy of those
   * rules in the browser would be one that quietly drifts from the one that
   * matters, and it would rob the author of the server's own message, which
   * is written for a person ("That image is 11264 KB; the limit is 10 MB.")
   * rather than for a log.
   *
   * A rejected file is reported and the batch carries on with the next one:
   * dropping four screenshots of which one is too big should still get three
   * of them in. Anything that isn't about that one file -- a frozen version
   * answering 403, an expired session, an unreachable content repo -- stops
   * the batch, because it would only repeat itself once per file.
   */
  async function uploadImages(files: File[], at: { from: number; to: number }) {
    if (readOnly || files.length === 0 || uploading) return;
    setTab("edit");
    let from = at.from;
    let to = at.to;
    let inserted = 0;
    setUploading({ done: 0, total: files.length });
    try {
      for (const [index, file] of files.entries()) {
        setUploading({ done: index, total: files.length });
        try {
          const asset = await api.adminUploadAsset(projectSlug, file, version || undefined);
          // Each further image onto its own line -- two `![]()` run together
          // are one paragraph of two images, which is nobody's intent when
          // they drop a pair of screenshots.
          const snippet = `${inserted > 0 ? "\n" : ""}![](${asset.markdown_path})`;
          replaceRange(from, to, snippet);
          from += snippet.length;
          to = from;
          inserted += 1;
        } catch (err) {
          toast.error(err instanceof ApiError ? err.message : t("common.error"));
          const aboutThisFile = err instanceof ApiError && (err.status === 400 || err.status === 413);
          if (!aboutThisFile) break;
        }
      }
    } finally {
      setUploading(null);
    }
    if (inserted === 0) return;
    toast.success(
      inserted === 1 ? t("admin.imageUploaded") : t("admin.imagesUploaded").replace("{count}", String(inserted)),
    );
    // The panel below lists the project's images; the ones just uploaded
    // belong in it without a round trip through another page.
    setAssetsKey((key) => key + 1);
    focusAt(from);
  }

  /**
   * A screenshot straight into the page.
   *
   * This is the whole point of the feature for documentation: take the
   * screenshot, put the cursor where it belongs, paste. The clipboard hands
   * over a nameless blob, so the editor names it (see pastedImageName).
   *
   * Text pasting is left completely alone. The handler only takes over when
   * the clipboard holds image files AND no plain text -- copying a
   * paragraph, a URL or a code block has text/plain on it and falls through
   * to the browser's own paste, as does a paste into a read-only frozen
   * version.
   */
  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    if (readOnly) return;
    const data = event.clipboardData;
    if (!data) return;
    const images = Array.from(data.files).filter((file) => file.type.startsWith("image/"));
    if (images.length === 0 || data.getData("text/plain").trim()) return;
    event.preventDefault();
    const now = new Date();
    const named = images.map(
      (file) => new File([file], pastedImageName(file, now), { type: file.type }),
    );
    uploadImages(named, caretRange());
  }

  /** Whether a drag is carrying FILES. A text selection being dragged around
   *  inside the textarea, or a link dragged in from another tab, carries
   *  text/plain and no "Files" -- ignoring those is what leaves drag-to-move
   *  text working exactly as the browser implements it, with no drop target
   *  appearing over it. */
  function isFileDrag(event: DragEvent) {
    return Array.from(event.dataTransfer?.types ?? []).includes("Files");
  }

  /** A drop is only ours on the two tabs that have Markdown behind them, and
   *  never on a frozen version -- there is nothing to upload into there, and
   *  the server would refuse it. */
  const dropTarget = !readOnly && tab !== "history" && !(tab === "edit" && visualActive);

  function onDragEnter(event: DragEvent) {
    if (!dropTarget || !isFileDrag(event)) return;
    event.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  }

  function onDragOver(event: DragEvent) {
    if (!dropTarget || !isFileDrag(event)) return;
    // Without this the browser takes the drop itself and navigates the tab
    // to the dropped file, losing everything unsaved in one gesture.
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }

  function onDragLeave() {
    if (dragDepth.current === 0) return;
    dragDepth.current -= 1;
    if (dragDepth.current === 0) setDragging(false);
  }

  function onDrop(event: DragEvent) {
    if (!dropTarget || !isFileDrag(event)) return;
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    // Dropped files keep their own names (the server slugifies the stem and
    // de-duplicates it) -- unlike a paste, a file dragged out of a folder
    // has a name its author chose.
    uploadImages(Array.from(event.dataTransfer.files), caretRange());
  }

  return (
    <div>
      {multilingual && (
        <div className="mb-3 flex flex-wrap items-center gap-1" aria-label={t("admin.pageLanguages")}>
          {site.languages.map((code) => {
            const exists = existing.includes(code);
            const active = code === language;
            return (
              <button
                key={code}
                type="button"
                onClick={() => switchLanguage(code)}
                disabled={!slug && !active}
                aria-current={active ? "true" : undefined}
                title={
                  !slug && !active
                    ? t("admin.saveFirstForTranslations")
                    : exists
                      ? languageName(code, uiLang)
                      : `${languageName(code, uiLang)} — ${t("admin.createTranslation")}`
                }
                className={[
                  "rounded-t border-b-2 px-3 py-1.5 text-sm",
                  active ? "border-[var(--accent)] font-medium" : "border-transparent text-[var(--muted)]",
                  // Dashed and dimmed = this translation doesn't exist yet.
                  // The same treatment the page list uses, so the two read
                  // as the same fact stated twice.
                  !exists && !active ? "opacity-60" : "",
                  !slug && !active ? "cursor-not-allowed" : "",
                ].join(" ")}
              >
                {languageName(code, uiLang)}
                {!exists && <span className="ml-1.5 text-xs">·</span>}
              </button>
            );
          })}
          <span className="ml-2 text-xs text-[var(--muted)]">
            {existing.includes(language) ? "" : t("admin.translationMissing")}
          </span>
        </div>
      )}

      <PresenceBanner others={presence} />

      {draftOffer && (
        <DraftBanner
          draft={draftOffer}
          stale={draftStale}
          onRestore={onRestoreDraft}
          onDiscard={onDiscardDraft}
        />
      )}

      <div className="flex items-center gap-2">
        <Input
          value={title}
          disabled={readOnly}
          onChange={(e) => {
            setTitle(e.target.value);
            setDirty(true);
          }}
          placeholder={t("admin.pageTitle")}
          className="flex-1 text-base font-medium"
        />
        <select
          value={targetCategoryId}
          disabled={readOnly}
          onChange={(e) => setTargetCategoryId(Number(e.target.value))}
          className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm"
        >
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <Button
          variant="outline"
          size="icon"
          disabled={readOnly || (reviewRequired && !livePublished)}
          onClick={() => setPublished((v) => !v)}
          title={
            reviewRequired && !livePublished
              ? t("review.publishViaApproval")
              : published
                ? t("admin.published")
                : t("admin.draft")
          }
        >
          {published ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
        </Button>
      </div>

      {/* Directly under the title and the publish toggle, because it belongs
          to the same set of facts about this page: is it public, and has
          anyone checked it. Only for a page that has been saved -- a note is
          about a text, and an unsaved editor has none yet. */}
      {loadedId !== null && (
        <ReviewNote
          pageId={loadedId}
          reviewedBy={reviewedBy}
          reviewedAt={reviewedAt}
          readOnly={readOnly}
          onChanged={(by, at) => {
            setReviewedBy(by);
            setReviewedAt(at);
          }}
        />
      )}

      {sourceEditUrl && (
        <a
          href={sourceEditUrl}
          target="_blank"
          rel="noreferrer noopener"
          className="mt-2 inline-flex items-center gap-1.5 self-start rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm hover:bg-[var(--surface-2)]"
        >
          <GitBranch className="h-4 w-4" />
          {t("sync.editInRepo")}
        </a>
      )}

      {loadedId !== null && review && !frozen && (
        <ReviewPanel
          pageId={loadedId}
          review={review}
          published={livePublished}
          dirty={dirty}
          canWrite={!readOnly}
          onChanged={() => {
            setReloadKey((k) => k + 1);
            onSaved();
          }}
        />
      )}

      <div className="mt-3 flex gap-1 border-b border-[var(--border)]">
        <button
          type="button"
          onClick={() => setTab("edit")}
          className={`px-3 py-1.5 text-sm ${tab === "edit" ? "border-b-2 border-[var(--accent)] font-medium" : "text-[var(--muted)]"}`}
        >
          {t("admin.editorTab")}
        </button>
        <button
          type="button"
          onClick={() => setTab("preview")}
          className={`px-3 py-1.5 text-sm ${tab === "preview" ? "border-b-2 border-[var(--accent)] font-medium" : "text-[var(--muted)]"}`}
        >
          {t("admin.previewTab")}
        </button>
        {/* A tab rather than a panel of its own: the history is another view
            of the very page being edited, and it is the one place an author
            goes to answer "what did this say last week". Disabled rather than
            hidden while this language has never been saved -- the reason it
            is empty is worth saying, since an unwritten translation looks
            exactly like a page whose history failed to load. */}
        <button
          type="button"
          onClick={() => setTab("history")}
          disabled={loadedId === null}
          title={loadedId === null ? t("admin.historyNotSavedYet") : undefined}
          className={`flex items-center gap-1.5 px-3 py-1.5 text-sm ${
            tab === "history" ? "border-b-2 border-[var(--accent)] font-medium" : "text-[var(--muted)]"
          } ${loadedId === null ? "cursor-not-allowed opacity-50" : ""}`}
        >
          <History className="h-3.5 w-3.5" aria-hidden="true" />
          {t("admin.historyTab")}
        </button>
        {tab === "edit" && (
          <div
            role="group"
            aria-label={t("visual.modeLabel")}
            className="mb-1 ml-auto inline-flex h-8 items-center self-center rounded-lg border border-[var(--border)] p-0.5 text-xs font-medium"
          >
            {(["visual", "markdown"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                aria-pressed={editorMode === mode}
                onClick={() => chooseEditorMode(mode)}
                className={`rounded-md px-2 py-1 transition-colors ${
                  editorMode === mode
                    ? "bg-[var(--accent)] text-[var(--accent-ink)]"
                    : "text-[var(--muted)] hover:text-[var(--ink)]"
                }`}
              >
                {mode === "visual" ? t("visual.modeVisual") : t("visual.modeMarkdown")}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Only while the body is empty, and gone for good once it isn't:
          applying a template replaces the whole text. Placed under the tabs
          rather than in a dialog on "new page", so it is equally available
          on an empty TRANSLATION tab -- which is a blank page too, and the
          one an author is most likely to want a structure for. */}
      {!readOnly && blank && templates && templates.list.length > 0 && (
        <div className="mt-3 rounded-lg border border-dashed border-[var(--border)] px-3 py-2">
          <div className="text-xs font-medium">{t("admin.templatesTitle")}</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {templates.list.map((template) => (
              <button
                key={template.id}
                type="button"
                title={template.description}
                onClick={() => applyTemplate(template)}
                className="rounded-full border border-[var(--border)] px-2.5 py-1 text-xs hover:border-[var(--accent)] hover:text-[var(--accent)]"
              >
                {template.name}
              </button>
            ))}
          </div>
          <p className="mt-1.5 text-xs text-[var(--muted)]">{t("admin.templatesHint")}</p>
        </div>
      )}

      {/* The uploader writes into the version being EDITED, so it has no
          place on a frozen one -- and its "insert" would paste a snippet
          into a textarea that can't be saved anyway. Nor on the history tab,
          where there is no textarea to insert into at all. */}
      {!readOnly && tab !== "history" && (
        <ImagesPanel
          projectSlug={projectSlug}
          version={version}
          reloadKey={assetsKey}
          onInsert={(asset) =>
            visualActive && tab === "edit"
              ? visualRef.current?.insertImage(asset.markdown_path)
              : insertSnippet(`![](${asset.markdown_path})`)
          }
        />
      )}

      {/* Progress, not a blocker: an upload is a round trip that ends in a
          git push, and freezing the textarea for it would interrupt the very
          sentence the screenshot is being pasted into. */}
      {uploading && (
        <div className="mt-2 flex items-center gap-2 text-sm text-[var(--muted)]" role="status" aria-live="polite">
          <Upload className="h-3.5 w-3.5 animate-pulse" aria-hidden="true" />
          {t("admin.imageUploadProgress")
            .replace("{n}", String(uploading.done + 1))
            .replace("{total}", String(uploading.total))}
        </div>
      )}

      {/* The drop target wraps the whole tab body rather than just the
          textarea, so a file aimed at the preview lands too -- it is the
          same page either way. The handlers ignore any drag that isn't
          carrying files, which is what leaves dragging a text selection
          around inside the textarea working as it always did. */}
      <div
        className="relative mt-3"
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        {tab === "edit" && editorMode === "visual" && visualCheck === "lossy" && (
          <p className="mb-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--muted)]">
            {t("visual.lossyNotice")}
          </p>
        )}
        {tab === "edit" && editorMode === "visual" && visualCheck === "pending" && (
          <p className="min-h-[420px] px-1 py-2 text-sm text-[var(--muted)]">{t("visual.loading")}</p>
        )}
        {tab === "edit" && visualActive && (
          <Suspense fallback={<p className="min-h-[420px] px-1 py-2 text-sm text-[var(--muted)]">{t("visual.loading")}</p>}>
            <VisualEditor
              // A fresh editor per page and language: undo history must not
              // reach back into another page's text.
              key={`${slug}:${language}:${reloadKey}`}
              ref={visualRef}
              value={content}
              readOnly={readOnly}
              onChange={(markdown) => {
                setContent(markdown);
                setDirty(true);
              }}
              uploadImage={uploadForVisual}
              resolveImage={(src) => resolveImageSrc(src, projectSlug, targetCategorySlug, version || undefined)}
              onKeyDown={onVisualKeyDown}
              insertables={loadInsertables}
            />
          </Suspense>
        )}
        {tab === "edit" && (editorMode === "markdown" || visualCheck === "lossy") && (
          <Textarea
            ref={editorRef}
            value={content}
            readOnly={readOnly}
            onPaste={onPaste}
            onKeyDown={onEditorKeyDown}
            onChange={(e) => {
              setContent(e.target.value);
              setDirty(true);
            }}
            className="min-h-[420px] font-mono"
          />
        )}
        {tab === "edit" && (editorMode === "markdown" || visualCheck === "lossy") && <MarkdownCheatSheet />}
        {tab === "preview" && (
          <div className="min-h-[420px] rounded-lg border border-[var(--border)] p-4">
            <ResolvedPreview
              content={content}
              title={title}
              projectSlug={projectSlug}
              categorySlug={targetCategorySlug}
              version={version}
              language={multilingual ? language : ""}
            />
          </div>
        )}
        {tab === "history" && loadedId !== null && (
          <HistoryPanel
            pageId={loadedId}
            readOnly={readOnly}
            onRestored={() => {
              // The restore wrote a new version into the content repo, so
              // both the text in this editor and the list behind it are now
              // out of date. Back to the Markdown tab, on the restored text.
              setReloadKey((key) => key + 1);
              setTab("edit");
              onSaved();
            }}
          />
        )}

        {/* pointer-events-none on purpose: the overlay is a label, and a
            drop has to reach the element underneath it that is listening. */}
        {dragging && (
          <div
            className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-lg border-2 border-dashed border-[var(--accent)] bg-[var(--accent-soft)]"
            data-testid="editor-drop-target"
          >
            <span className="flex items-center gap-2 rounded-lg bg-[var(--surface)] px-3 py-2 text-sm font-medium shadow">
              <ImagePlus className="h-4 w-4" aria-hidden="true" />
              {t("admin.imageDropHere")}
            </span>
          </div>
        )}
      </div>

      {/* Below the text rather than beside the publish toggle: making a link
          is something an author does once the draft is worth showing, which
          is after they have written it, not before. Nothing on a frozen
          version -- there is no draft in a released version to preview. */}
      {loadedId !== null && !readOnly && tab !== "history" && <PreviewLinksPanel pageId={loadedId} />}

      <div className="mt-3 flex gap-2">
        {/* No Save at all on a frozen version, rather than one that errors:
            the notice above the panels already says why, and the way to
            correct an old page is a file edit in the content repo. */}
        {!readOnly && (
          <Button onClick={onSave} disabled={saving || !title.trim()}>
            {t("admin.save")}
          </Button>
        )}
        <Button variant="outline" onClick={onDone}>
          {readOnly ? t("common.back") : t("admin.cancel")}
        </Button>
      </div>
    </div>
  );
}

/**
 * The offer to bring back unsaved text this browser kept.
 *
 * An offer, never an action: the editor shows what the content repo has, and
 * this sits above it saying that something else exists and when it was
 * written. Restoring and discarding are the same size, next to each other,
 * because neither is the obviously right answer -- only the author knows
 * which of the two texts is the one they meant.
 *
 * The `stale` case is the one worth getting right. A draft is not
 * automatically the newer text: the page may have been edited by someone
 * else, or by this same author from another browser, since the draft was
 * made. Then restoring is not "get my work back", it is "replace newer text
 * with older text", and the banner says exactly that, in amber, with the
 * button relabelled -- rather than offering a cheerful restore that quietly
 * undoes a colleague's afternoon.
 */
export function DraftBanner({
  draft,
  stale,
  onRestore,
  onDiscard,
}: {
  draft: PageDraft;
  stale: boolean;
  onRestore: () => void;
  onDiscard: () => void;
}) {
  const { t, lang: uiLang } = useI18n();
  const when = new Date(draft.savedAt).toLocaleString(uiLang, { dateStyle: "medium", timeStyle: "short" });

  return (
    <div
      className={`mb-3 flex flex-col gap-2 rounded-lg border px-3 py-2.5 text-sm ${
        stale ? "border-amber-500/60 bg-amber-500/10" : "border-[var(--border)] bg-[var(--surface-2)]"
      }`}
      data-testid={stale ? "draft-banner-stale" : "draft-banner"}
    >
      <span className="flex items-start gap-2 font-medium">
        {stale ? (
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
        ) : (
          <FileClock className="mt-0.5 h-4 w-4 shrink-0 text-[var(--muted)]" aria-hidden="true" />
        )}
        {stale ? t("admin.draftStaleTitle") : t("admin.draftFoundTitle")}
      </span>
      <span className="text-[var(--muted)]">
        {(stale ? t("admin.draftStaleBody") : t("admin.draftFoundBody")).replace("{when}", when)}
      </span>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={onRestore}>
          <RotateCcw className="h-3.5 w-3.5" />
          {stale ? t("admin.draftRestoreAnyway") : t("admin.draftRestore")}
        </Button>
        {/* Exactly as easy to reach as the restore, and it removes the
            stored copy for good -- an offer that can only be accepted is a
            banner that comes back on every visit. */}
        <Button size="sm" variant="ghost" onClick={onDiscard}>
          <Trash2 className="h-3.5 w-3.5" />
          {t("admin.draftDiscard")}
        </Button>
      </div>
    </div>
  );
}
