// Site branding: name, logo, colours, footer and analytics, from _site.yml.
// Split out of pages/AdminApp.tsx, which keeps the layout and state.
import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  api,
  ApiError,
  type FooterLink,
  type SiteAnalytics,
  type SiteAppearance,
  type SiteAsset,
  type SiteBranding,
  type SitePdf,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { languageName } from "@/lib/lang";
import { logoForTheme, useSite } from "@/lib/site";
import { accentVariables } from "@/lib/theme";
import { PDF_DEFAULTS } from "@/lib/printBranding";
import { toFieldValues, fromFieldValues, LocalizedInput } from "./shared";
import { SkeletonLines } from "@/components/Skeleton";

export const APPEARANCE_DEFAULTS: SiteAppearance = { surface: "cool", radius: "medium", header: "plain" };

/** Ready-made looks: one click fills in the accent and the three appearance
 *  choices, which stay editable one by one afterwards. A theme is not saved
 *  as such -- only the values it set -- so nothing changes under an instance
 *  when a later version adds or tunes a theme. */
const THEMES: { id: string; accent: string; appearance: SiteAppearance }[] = [
  { id: "default", accent: "", appearance: APPEARANCE_DEFAULTS },
  { id: "ocean", accent: "#0e7490", appearance: { surface: "cool", radius: "round", header: "accent" } },
  { id: "forest", accent: "#2f7d4f", appearance: { surface: "neutral", radius: "medium", header: "plain" } },
  { id: "sunset", accent: "#c2410c", appearance: { surface: "warm", radius: "round", header: "plain" } },
  { id: "graphite", accent: "#374151", appearance: { surface: "neutral", radius: "sharp", header: "accent" } },
  { id: "plum", accent: "#7c3aed", appearance: { surface: "cool", radius: "round", header: "plain" } },
];

/** The instance's own identity: name, tagline, accent colour, logo/favicon
 *  and footer. Saving writes content/_site.yml (plus any uploaded image into
 *  content/_site/) and pushes it, exactly like every other admin write --
 *  branding is content-repo state, not a database row, so it survives a
 *  reindex and travels with the repo (see the backend's site_branding.py).
 *
 *  The whole form edits a local draft and shows it in the preview above the
 *  fields; nothing reaches the live site until Save, at which point the site
 *  context is reloaded so the surrounding admin header updates too. */
export function BrandingCard({ isDark, onClose }: { isDark: boolean; onClose: () => void }) {
  const { t, lang: uiLang } = useI18n();
  const { reload } = useSite();
  const [draft, setDraft] = useState<SiteBranding | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .adminGetSite()
      .then(setDraft)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : t("common.error")));
    // t is stable for a given language and the form is a one-shot load --
    // re-running this on a language switch would throw away the user's edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function patch(changes: Partial<SiteBranding>) {
    setDraft((current) => (current ? { ...current, ...changes } : current));
  }

  async function onSave() {
    if (!draft) return;
    setSaving(true);
    try {
      // The response is the branding as it now READS BACK -- a value the
      // backend rejected (a colour that isn't a colour, a javascript: link)
      // disappears from the form here rather than sitting in it looking saved.
      const saved = await api.adminUpdateSite({
        name: draft.name,
        name_i18n: draft.name_i18n,
        tagline: draft.tagline,
        tagline_i18n: draft.tagline_i18n,
        logo: draft.logo,
        logo_dark: draft.logo_dark,
        favicon: draft.favicon,
        accent: draft.accent,
        footer_text: draft.footer_text,
        footer_text_i18n: draft.footer_text_i18n,
        footer_links: draft.footer_links,
        powered_by: draft.powered_by !== false,
        announcement: draft.announcement ?? {},
        appearance: draft.appearance ?? APPEARANCE_DEFAULTS,
        custom_css: draft.custom_css ?? "",
        analytics: draft.analytics ?? {},
        pdf: draft.pdf ?? PDF_DEFAULTS,
      });
      setDraft(saved);
      await reload();
      toast.success(t("admin.brandingSaved"));
    } catch (err) {
      toast.error(
        err instanceof ApiError
          ? err.message === "page_changed"
            ? t("admin.pageChangedKept")
            : err.message
          : t("common.error"),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="text-base font-semibold text-[var(--ink)]">{t("admin.branding")}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-sm text-[var(--muted)]">{t("admin.brandingIntro")}</p>

        {!draft ? (
          <SkeletonLines rows={4} label={t("common.loading")} />
        ) : (
          <div className="flex flex-col gap-4">
            <BrandingPreview draft={draft} isDark={isDark} />

            <div className="grid gap-3 sm:grid-cols-2">
              <BrandingTextField
                label={t("admin.brandingName")}
                draft={draft}
                field="name"
                mappingField="name_i18n"
                patch={patch}
              />
              <BrandingTextField
                label={t("admin.brandingTagline")}
                draft={draft}
                field="tagline"
                mappingField="tagline_i18n"
                patch={patch}
              />
            </div>

            {/* Read-only: `languages:` decides how every page file in the
                content repo is named and how every URL is shaped, so it is
                changed in _site.yml (by hand or by pull request) rather
                than by a button that would silently re-language a whole
                repo -- see the backend's write_branding(). */}
            <div className="flex flex-col gap-1">
              <span className="text-sm font-medium">{t("admin.brandingLanguages")}</span>
              <span className="text-sm text-[var(--muted)]">
                {draft.languages.length > 0
                  ? draft.languages.map((code) => `${code} (${languageName(code, uiLang)})`).join(" · ")
                  : t("admin.brandingLanguagesNone")}
              </span>
              <span className="text-xs text-[var(--muted)]">{t("admin.brandingLanguagesHint")}</span>
            </div>

            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">{t("admin.brandingAccent")}</span>
              <div className="flex items-center gap-2">
                {/* The picker always needs a concrete colour to sit on, so
                    it falls back to the built-in light-mode accent while
                    none is configured -- the text field next to it is what
                    actually shows whether one IS ("" = default). */}
                <input
                  type="color"
                  aria-label={t("admin.brandingAccent")}
                  value={draft.accent || "#4f6df5"}
                  onChange={(e) => patch({ accent: e.target.value })}
                  className="h-9 w-12 cursor-pointer rounded-lg border border-[var(--border)] bg-[var(--surface)] p-1"
                />
                <Input
                  value={draft.accent}
                  onChange={(e) => patch({ accent: e.target.value })}
                  placeholder="#4f6df5"
                  className="max-w-[10rem] font-mono"
                />
                <Button variant="outline" size="sm" onClick={() => patch({ accent: "" })}>
                  {t("admin.brandingAccentReset")}
                </Button>
              </div>
            </div>

            <AppearanceFields
              accent={draft.accent}
              appearance={draft.appearance ?? APPEARANCE_DEFAULTS}
              onChange={(changes) => patch(changes)}
            />

            <div className="grid gap-3 sm:grid-cols-3">
              <BrandingImageField
                label={t("admin.brandingLogo")}
                filename={draft.logo}
                url={draft.logo_url}
                onPicked={(asset) => patch({ logo: asset.filename, logo_url: asset.url })}
                onCleared={() => patch({ logo: "", logo_url: null })}
              />
              <BrandingImageField
                label={t("admin.brandingLogoDark")}
                filename={draft.logo_dark}
                url={draft.logo_dark_url}
                onPicked={(asset) => patch({ logo_dark: asset.filename, logo_dark_url: asset.url })}
                onCleared={() => patch({ logo_dark: "", logo_dark_url: null })}
              />
              <BrandingImageField
                label={t("admin.brandingFavicon")}
                filename={draft.favicon}
                url={draft.favicon_url}
                onPicked={(asset) => patch({ favicon: asset.filename, favicon_url: asset.url })}
                onCleared={() => patch({ favicon: "", favicon_url: null })}
              />
            </div>

            <BrandingTextField
              label={t("admin.brandingFooterText")}
              draft={draft}
              field="footer_text"
              mappingField="footer_text_i18n"
              patch={patch}
            />

            <FooterLinksEditor links={draft.footer_links} onChange={(footer_links) => patch({ footer_links })} />
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.powered_by !== false}
                onChange={(e) => patch({ powered_by: e.target.checked })}
              />
              {t("admin.brandingPoweredBy")}
            </label>

            <div className="flex flex-col gap-2">
              <span className="text-sm font-medium">{t("admin.brandingAnnouncement")}</span>
              <p className="text-xs text-[var(--muted)]">{t("admin.brandingAnnouncementHint")}</p>
              <Input
                value={draft.announcement?.text ?? ""}
                placeholder={t("admin.brandingAnnouncementText")}
                aria-label={t("admin.brandingAnnouncementText")}
                onChange={(e) => patch({ announcement: { ...draft.announcement, text: e.target.value } })}
              />
              <Input
                value={draft.announcement?.link ?? ""}
                placeholder={t("admin.brandingLinkUrl")}
                aria-label={t("admin.brandingAnnouncementLink")}
                onChange={(e) => patch({ announcement: { ...draft.announcement, link: e.target.value } })}
              />
            </div>

            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">{t("admin.brandingCustomCss")}</span>
              <span className="text-xs text-[var(--muted)]">{t("admin.brandingCustomCssHint")}</span>
              <textarea
                value={draft.custom_css ?? ""}
                onChange={(e) => patch({ custom_css: e.target.value })}
                rows={5}
                spellCheck={false}
                placeholder=".markdown-body h2 { letter-spacing: -0.01em; }"
                className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-2 font-mono text-xs outline-none focus:border-[var(--accent)]"
              />
            </label>

            <AnalyticsFields
              analytics={draft.analytics ?? {}}
              onChange={(analytics) => patch({ analytics })}
            />

            <PdfFields pdf={draft.pdf ?? PDF_DEFAULTS} onChange={(pdf) => patch({ pdf })} />

            <div className="flex gap-2">
              <Button onClick={onSave} disabled={saving}>
                {t("admin.save")}
              </Button>
              <Button variant="outline" onClick={onClose}>
                {t("admin.cancel")}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * The two fields that turn on analytics, and the only two there are.
 *
 * A named tool with two narrow fields rather than a "paste your tracking
 * snippet" box: that box is a script tag in the head of every public page,
 * writable by anyone with the admin password AND by anyone whose pull
 * request to `_site.yml` gets merged. What this can produce is one shape of
 * tag, and the shape is visible in the code that writes it (the backend's
 * seo.render_analytics).
 *
 * Both fields or neither -- the backend drops half a pair, because a script
 * URL with no website id loads a counter that reports to nowhere and looks,
 * from the settings page, exactly like a working one.
 */
export function AnalyticsFields({
  analytics,
  onChange,
}: {
  analytics: SiteAnalytics;
  onChange: (analytics: SiteAnalytics) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium">{t("admin.analytics")}</span>
      <span className="text-xs text-[var(--muted)]">{t("admin.analyticsHint")}</span>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
          {t("admin.analyticsUrl")}
          <Input
            value={analytics.umami_url ?? ""}
            onChange={(e) => onChange({ ...analytics, umami_url: e.target.value })}
            placeholder="https://umami.example.com/script.js"
            className="font-mono"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
          {t("admin.analyticsWebsiteId")}
          <Input
            value={analytics.umami_website_id ?? ""}
            onChange={(e) => onChange({ ...analytics, umami_website_id: e.target.value })}
            placeholder="2f4a1b0c-1111-2222-3333-444455556666"
            className="font-mono"
          />
        </label>
      </div>
      {/* Not a promise the operator has to take on trust: it is what the tag
          says, and what it does not carry. */}
      <span className="text-xs text-[var(--muted)]">{t("admin.analyticsPrivacy")}</span>
      {(analytics.umami_url || analytics.umami_website_id) && (
        <Button
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() => onChange({})}
        >
          {t("admin.analyticsOff")}
        </Button>
      )}
    </div>
  );
}

/** One of the three translatable branding texts. Exactly the plain input it
 *  has always been on a single-language instance; one input per language
 *  once `languages:` names more than one, with the default language's value
 *  kept in the plain field (which is what an unbranded/untranslated read
 *  falls back to). */
export function BrandingTextField({
  label,
  draft,
  field,
  mappingField,
  patch,
}: {
  label: string;
  draft: SiteBranding;
  field: "name" | "tagline" | "footer_text";
  mappingField: "name_i18n" | "tagline_i18n" | "footer_text_i18n";
  patch: (changes: Partial<SiteBranding>) => void;
}) {
  const values = toFieldValues(draft[field], draft[mappingField], draft.languages, draft.default_language);
  return (
    <LocalizedInput
      label={label}
      values={values}
      languages={draft.languages}
      onChange={(next) => {
        const resolved = fromFieldValues(next, draft.languages, draft.default_language);
        patch({ [field]: resolved.text, [mappingField]: resolved.i18n } as Partial<SiteBranding>);
      }}
    />
  );
}

/** The public header as the current draft would render it -- same logo/name
 *  arrangement as PublicLayout, and the accent scoped to this box through
 *  the same derivation the live site uses, so a colour can be judged before
 *  it is saved onto every page. */
export function BrandingPreview({ draft, isDark }: { draft: SiteBranding; isDark: boolean }) {
  const { t } = useI18n();
  const logoUrl = logoForTheme(draft, isDark);
  const appearance = draft.appearance ?? APPEARANCE_DEFAULTS;
  return (
    <div>
      <span className="text-sm font-medium uppercase tracking-wide text-[var(--muted)]">
        {t("admin.brandingPreview")}
      </span>
      {/* The same data-* attributes the live site gets on <html>, set on
          this box instead: index.css's rules apply to either, so the draft
          shows here before it is saved. */}
      <div
        data-surface={appearance.surface}
        data-radius={appearance.radius}
        data-header={appearance.header}
        className="mt-1.5 overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--bg)]"
        style={accentVariables(draft.accent) ?? undefined}
      >
        <div className="site-header flex items-center gap-3 border-b border-[var(--border)] bg-[var(--surface)] px-3 py-2.5">
          {logoUrl && <img src={logoUrl} alt="" className="h-7 w-auto max-w-[10rem] object-contain" />}
          <span className="text-lg font-semibold">{draft.name || "DocuWaves"}</span>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-sm">{t("nav.public")}</span>
          </div>
        </div>
        <div className="grid gap-3 p-3 sm:grid-cols-[1fr_auto]">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3 shadow-[var(--shadow)]">
            <span className="block font-semibold">{draft.tagline || t("admin.brandingPreviewCard")}</span>
            <span className="mt-1 block text-sm text-[var(--muted)]">{t("admin.brandingPreviewText")}</span>
            <span className="mt-2 inline-block rounded-md bg-[var(--surface-2)] px-2 py-1 font-mono text-xs">
              npm run build
            </span>
          </div>
          <div className="flex items-end">
            <Button size="sm">{t("admin.save")}</Button>
          </div>
        </div>
        {(draft.footer_text || draft.footer_links.length > 0) && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--muted)]">
            {draft.footer_text && <span>{draft.footer_text}</span>}
            {draft.footer_links.map((link) => (
              <span key={`${link.label}-${link.url}`} className="text-[var(--accent)]">
                {link.label}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** Ready-made themes and the three appearance choices, each a row of
 *  buttons: the options are few and visual, a select would hide them. */
function AppearanceFields({
  accent,
  appearance,
  onChange,
}: {
  accent: string;
  appearance: SiteAppearance;
  onChange: (changes: Partial<SiteBranding>) => void;
}) {
  const { t } = useI18n();
  const set = (changes: Partial<SiteAppearance>) => onChange({ appearance: { ...appearance, ...changes } });
  const active = THEMES.find(
    (theme) =>
      theme.accent === accent &&
      theme.appearance.surface === appearance.surface &&
      theme.appearance.radius === appearance.radius &&
      theme.appearance.header === appearance.header,
  )?.id;
  const segment = <K extends keyof SiteAppearance>(key: K, options: SiteAppearance[K][]) => (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium">{t(`admin.appearance.${key}` as never)}</span>
      <div className="flex gap-1 rounded-lg border border-[var(--border)] p-0.5" role="group">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={appearance[key] === option}
            onClick={() => set({ [key]: option } as Partial<SiteAppearance>)}
            className={`flex-1 rounded-md px-2 py-1 text-xs ${
              appearance[key] === option
                ? "bg-[var(--accent)] text-[var(--accent-ink)]"
                : "text-[var(--muted)] hover:bg-[var(--surface-2)]"
            }`}
          >
            {t(`admin.appearance.${key}.${option}` as never)}
          </button>
        ))}
      </div>
    </div>
  );
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">{t("admin.appearance.themes")}</span>
        <div className="flex flex-wrap gap-2">
          {THEMES.map((theme) => (
            <button
              key={theme.id}
              type="button"
              aria-pressed={active === theme.id}
              onClick={() => onChange({ accent: theme.accent, appearance: theme.appearance })}
              className={`flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm ${
                active === theme.id ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--border)] hover:bg-[var(--surface-2)]"
              }`}
            >
              <span
                className="h-4 w-4 rounded-full border border-black/10"
                style={{ background: theme.accent || "#4f6df5" }}
                aria-hidden="true"
              />
              {t(`admin.theme.${theme.id}` as never)}
            </button>
          ))}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {segment("surface", ["cool", "neutral", "warm"])}
        {segment("radius", ["sharp", "medium", "round"])}
        {segment("header", ["plain", "accent"])}
      </div>
    </div>
  );
}

/** One image slot (logo / dark logo / favicon). Uploading commits the file
 *  into content/_site/ immediately -- that's what gives it a URL to preview
 *  -- but which file the SITE uses is only decided when the form is saved. */
export function BrandingImageField({
  label,
  filename,
  url,
  onPicked,
  onCleared,
}: {
  label: string;
  filename: string;
  url: string | null;
  onPicked: (asset: SiteAsset) => void;
  onCleared: () => void;
}) {
  const { t } = useI18n();
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function onPick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Cleared right away so picking the SAME file again still fires change.
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      onPicked(await api.adminUploadSiteAsset(file));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-[var(--border)] p-3">
      <span className="text-sm font-medium">{label}</span>
      <div className="flex items-center gap-2">
        {url ? (
          <img src={url} alt="" className="h-8 w-8 rounded object-contain" />
        ) : (
          <span className="text-xs text-[var(--muted)]">{t("admin.brandingNoImage")}</span>
        )}
        <span className="min-w-0 flex-1 truncate text-xs text-[var(--muted)]" title={filename}>
          {filename}
        </span>
        {filename && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            aria-label={t("admin.brandingRemoveImage")}
            onClick={onCleared}
          >
            <X className="h-3 w-3" />
          </Button>
        )}
      </div>
      <Button variant="outline" size="sm" disabled={uploading} onClick={() => inputRef.current?.click()}>
        <Upload className="h-3.5 w-3.5" />
        {uploading ? t("admin.uploadingImage") : t("admin.brandingUpload")}
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept=".png,.jpg,.jpeg,.gif,.webp,.avif,.svg"
        className="hidden"
        onChange={onPick}
      />
    </div>
  );
}

export function FooterLinksEditor({ links, onChange }: { links: FooterLink[]; onChange: (links: FooterLink[]) => void }) {
  const { t } = useI18n();

  function update(index: number, changes: Partial<FooterLink>) {
    onChange(links.map((link, i) => (i === index ? { ...link, ...changes } : link)));
  }

  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm font-medium">{t("admin.brandingFooterLinks")}</span>
      {links.map((link, index) => (
        // Index-keyed on purpose: these rows have no id of their own and
        // their label/url are exactly what's being edited, so a value-based
        // key would remount the input on every keystroke and lose focus.
        <div key={index} className="flex items-center gap-2">
          <Input
            value={link.label}
            placeholder={t("admin.brandingLinkLabel")}
            onChange={(e) => update(index, { label: e.target.value })}
            className="max-w-[12rem]"
          />
          <Input
            value={link.url}
            placeholder={t("admin.brandingLinkUrl")}
            onChange={(e) => update(index, { url: e.target.value })}
            className="flex-1"
          />
          <Input
            value={link.column ?? ""}
            placeholder={t("admin.brandingLinkColumn")}
            aria-label={t("admin.brandingLinkColumn")}
            onChange={(e) => update(index, { column: e.target.value })}
            className="max-w-[9rem]"
          />
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label={t("admin.delete")}
            onClick={() => onChange(links.filter((_, i) => i !== index))}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        className="self-start"
        onClick={() => onChange([...links, { label: "", url: "" }])}
      >
        <Plus className="h-3.5 w-3.5" />
        {t("admin.brandingAddLink")}
      </Button>
    </div>
  );
}

/**
 * How a printed manual or page looks: the cover template of the whole-project
 * print view, a running header and footer on every sheet, page numbers, and
 * the logo on the cover. All of it is drawn by the browser when printing
 * (lib/printBranding.tsx); nothing here changes the site on screen.
 */
export function PdfFields({ pdf, onChange }: { pdf: SitePdf; onChange: (pdf: SitePdf) => void }) {
  const { t } = useI18n();
  const set = (patch: Partial<SitePdf>) => onChange({ ...pdf, ...patch });
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium">{t("admin.pdf")}</span>
      <span className="text-xs text-[var(--muted)]">{t("admin.pdfHint")}</span>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
          {t("admin.pdfTemplate")}
          <select
            value={pdf.template}
            onChange={(e) => set({ template: e.target.value as SitePdf["template"] })}
            className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm text-[var(--ink)]"
          >
            <option value="classic">{t("admin.pdfClassic")}</option>
            <option value="band">{t("admin.pdfBand")}</option>
            <option value="minimal">{t("admin.pdfMinimal")}</option>
          </select>
        </label>
        <div className="flex flex-col justify-end gap-1 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={pdf.page_numbers} onChange={(e) => set({ page_numbers: e.target.checked })} />
            {t("admin.pdfPageNumbers")}
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={pdf.logo} onChange={(e) => set({ logo: e.target.checked })} />
            {t("admin.pdfLogo")}
          </label>
        </div>
        <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
          {t("admin.pdfHeader")}
          <Input value={pdf.header} onChange={(e) => set({ header: e.target.value })} placeholder="{project} · {version}" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
          {t("admin.pdfFooter")}
          <Input value={pdf.footer} onChange={(e) => set({ footer: e.target.value })} placeholder="{site} · {date}" />
        </label>
      </div>
      <span className="text-xs text-[var(--muted)]">{t("admin.pdfPlaceholders")}</span>
    </div>
  );
}
