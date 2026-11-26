// The parts of the public frame the instance's owner configures in the
// admin's branding form: the announcement bar on top, the project switcher
// in the header, and the footer with its link columns.
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Check, ChevronDown, Megaphone, X } from "lucide-react";
import { api, type FooterLink, type Project, type SiteBranding } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { readStored, writeStored } from "@/lib/theme";

const DISMISSED_KEY = "docuwaves-announcement-closed";

/** A link the owner configured: off-site ones open in a new tab (the same
 *  rule as the footer has always had), site-relative ones stay in this one. */
function OwnerLink({ link, className, children }: { link: string; className?: string; children: React.ReactNode }) {
  const external = !link.startsWith("/");
  return (
    <a
      href={link}
      className={className}
      {...(external ? { target: "_blank", rel: "noreferrer noopener" } : {})}
    >
      {children}
    </a>
  );
}

/** One line across the top of every public page. A reader who closes it
 *  doesn't see it again -- until the text changes: what is remembered is
 *  the text that was closed, so the next announcement shows. */
export function AnnouncementBar({ site }: { site: SiteBranding }) {
  const { t } = useI18n();
  const { lang } = useContentLang();
  const announcement = site.announcement ?? {};
  const text = (lang && announcement.text_i18n?.[lang]) || announcement.text || "";
  const [closed, setClosed] = useState(() => readStored(DISMISSED_KEY));
  if (!text || closed === text) return null;
  return (
    <div className="announcement-bar border-b border-[var(--border)] bg-[var(--accent-soft)] text-sm text-[var(--ink)]">
      <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-2">
        <Megaphone className="h-4 w-4 shrink-0 text-[var(--accent)]" aria-hidden="true" />
        <p className="min-w-0 flex-1">
          {announcement.link ? (
            <OwnerLink link={announcement.link} className="underline-offset-2 hover:underline">
              {text} →
            </OwnerLink>
          ) : (
            text
          )}
        </p>
        <button
          type="button"
          onClick={() => {
            writeStored(DISMISSED_KEY, text);
            setClosed(text);
          }}
          aria-label={t("site.closeAnnouncement")}
          className="rounded p-1 text-[var(--muted)] hover:bg-[var(--surface)] hover:text-[var(--ink)]"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

/** "Which documentation am I in, and where else could I go": the projects of
 *  this instance, in a menu next to the site name. Only when there is more
 *  than one -- with one project, there is nothing to switch to. */
export function ProjectSwitcher() {
  const { t } = useI18n();
  const { lang, path } = useContentLang();
  const { pathname } = useLocation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .publicListProjects(lang)
      .then((r) => setProjects(r.projects))
      .catch(() => setProjects([]));
  }, [lang]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const [openFor, setOpenFor] = useState(pathname);
  if (openFor !== pathname) {
    setOpenFor(pathname);
    setOpen(false);
  }

  if (projects.length < 2) return null;
  const currentSlug = /\/p\/([^/]+)/.exec(pathname)?.[1];
  const current = projects.find((p) => p.slug === currentSlug);

  return (
    <div ref={box} className="relative hidden sm:block">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 rounded-md border border-[var(--border)] px-2 py-1 text-sm text-[var(--muted)] hover:text-[var(--ink)]"
      >
        {current ? (
          <>
            {current.icon && <span aria-hidden="true">{current.icon}</span>}
            <span className="max-w-[10rem] truncate">{current.name}</span>
          </>
        ) : (
          t("site.projects")
        )}
        <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      {open && (
        <ul className="absolute left-0 z-40 mt-1 w-64 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-1 shadow-lg">
          {projects.map((p) => (
            <li key={p.id}>
              <Link
                to={path(`/p/${p.slug}`)}
                aria-current={p.slug === currentSlug ? "page" : undefined}
                className="flex items-start gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-[var(--surface-2)]"
              >
                <span className="w-5 shrink-0 text-center" aria-hidden="true">
                  {p.icon}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{p.name}</span>
                  {p.description && (
                    <span className="block truncate text-xs text-[var(--muted)]">{p.description}</span>
                  )}
                </span>
                {p.slug === currentSlug && <Check className="mt-0.5 h-4 w-4 text-[var(--accent)]" aria-hidden="true" />}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Links grouped by their column, in the order the columns first appear;
 *  links without one go to the line below. */
export function footerColumns(links: FooterLink[]): { columns: [string, FooterLink[]][]; loose: FooterLink[] } {
  const columns = new Map<string, FooterLink[]>();
  const loose: FooterLink[] = [];
  for (const link of links) {
    const column = link.column?.trim();
    if (!column) loose.push(link);
    else columns.set(column, [...(columns.get(column) ?? []), link]);
  }
  return { columns: [...columns], loose };
}

export function SiteFooter({ site, footerText }: { site: SiteBranding; footerText: string }) {
  const { t } = useI18n();
  const { columns, loose } = footerColumns(site.footer_links);
  const credit = site.powered_by !== false;
  // Nothing configured and the credit switched off: no footer at all, as
  // before -- an empty bar would be a change nobody asked for.
  if (!footerText && site.footer_links.length === 0 && !credit) return null;
  return (
    <footer className="mt-12 border-t border-[var(--border)] bg-[var(--surface)]">
      {columns.length > 0 && (
        <div className="mx-auto grid max-w-5xl grid-cols-2 gap-8 px-4 pt-8 sm:grid-cols-3 lg:grid-cols-4">
          {columns.map(([title, links]) => (
            <div key={title}>
              <h2 className="text-sm font-semibold text-[var(--ink)]">{title}</h2>
              <ul className="mt-3 space-y-2 text-sm">
                {links.map((link) => (
                  <li key={`${link.label}-${link.url}`}>
                    <OwnerLink link={link.url} className="text-[var(--muted)] hover:text-[var(--accent)]">
                      {link.label}
                    </OwnerLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-6 text-sm text-[var(--muted)]">
        {footerText && <span>{footerText}</span>}
        {loose.map((link) => (
          <OwnerLink key={`${link.label}-${link.url}`} link={link.url} className="hover:text-[var(--accent)]">
            {link.label}
          </OwnerLink>
        ))}
        {credit && (
          <span className="ml-auto text-xs">
            {t("site.madeWith")}{" "}
            <a href="https://docuwaves.app/" target="_blank" rel="noopener" className="font-medium hover:text-[var(--accent)]">
              DocuWaves
            </a>
          </span>
        )}
      </div>
    </footer>
  );
}
