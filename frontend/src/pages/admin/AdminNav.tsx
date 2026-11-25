import type { ComponentType } from "react";
import { NavLink } from "react-router-dom";
import {
  Activity,
  BarChart3,
  CircleCheckBig,
  Download,
  FileText,
  KeyRound,
  Palette,
  ScrollText,
  Stethoscope,
  UserRound,
  Users,
} from "lucide-react";
import { useI18n } from "@/lib/i18n";

/** The admin's areas. Each has its own address under /admin/, so a link to
 *  one can be shared and the browser's Back button goes where you were. The
 *  content (projects, categories, the editor) is /admin itself. */
export const ADMIN_PANELS = [
  "reviews",
  "import",
  "insights",
  "users",
  "activity",
  "branding",
  "tokens",
  "account",
  "diagnostics",
  "log",
] as const;
export type AdminPanel = (typeof ADMIN_PANELS)[number];

export function panelFromPath(pathname: string): AdminPanel | null {
  const segment = pathname.replace(/^\/admin\/?/, "").split("/")[0];
  return (ADMIN_PANELS as readonly string[]).includes(segment) ? (segment as AdminPanel) : null;
}

type Item = { to: string; label: string; icon: ComponentType<{ className?: string }>; badge?: number };

/** Grouped instead of eleven buttons in one row: what you work on, who you
 *  work with, how the instance looks, and how it runs. Administrator areas
 *  are left out for everybody else -- the API refuses them anyway, so
 *  offering them would be offering a 403. */
export function AdminNav({
  isAdmin,
  canWrite,
  reviewCount,
  onNavigate,
}: {
  isAdmin: boolean;
  canWrite: boolean;
  reviewCount: number;
  onNavigate?: () => void;
}) {
  const { t } = useI18n();
  const groups: { label: string; items: Item[] }[] = [
    {
      label: t("adminNav.content"),
      items: [
        { to: "/admin", label: t("adminNav.pages"), icon: FileText },
        { to: "/admin/reviews", label: t("review.queueButton"), icon: CircleCheckBig, badge: reviewCount },
        ...(canWrite ? [{ to: "/admin/import", label: t("import.title"), icon: Download }] : []),
        { to: "/admin/insights", label: t("admin.insights"), icon: BarChart3 },
      ],
    },
    {
      label: t("adminNav.team"),
      items: [
        ...(isAdmin ? [{ to: "/admin/users", label: t("users.title"), icon: Users }] : []),
        { to: "/admin/activity", label: t("activity.title"), icon: Activity },
      ],
    },
    {
      label: t("adminNav.settings"),
      items: [
        ...(isAdmin
          ? [
              { to: "/admin/branding", label: t("admin.branding"), icon: Palette },
              { to: "/admin/tokens", label: t("admin.tokens"), icon: KeyRound },
            ]
          : []),
        { to: "/admin/account", label: t("admin.account"), icon: UserRound },
      ],
    },
    ...(isAdmin
      ? [
          {
            label: t("adminNav.system"),
            items: [
              { to: "/admin/diagnostics", label: t("diag.title"), icon: Stethoscope },
              { to: "/admin/log", label: t("adminLog.title"), icon: ScrollText },
            ],
          },
        ]
      : []),
  ];

  return (
    <nav aria-label={t("adminNav.label")} className="space-y-5 px-3 py-4">
      {groups
        .filter((group) => group.items.length > 0)
        .map((group) => (
          <div key={group.label}>
            <p className="mb-1 px-2 text-xs font-medium text-[var(--muted)]">{group.label}</p>
            <ul className="space-y-0.5">
              {group.items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors ${
                        isActive
                          ? "bg-[var(--surface-2)] font-medium text-[var(--accent)]"
                          : "text-[var(--ink)] hover:bg-[var(--surface-2)]"
                      }`
                    }
                  >
                    <item.icon className="h-4 w-4 shrink-0 opacity-80" />
                    <span className="truncate">{item.label}</span>
                    {item.badge ? (
                      // Kept out of the link's name ("Approvals", not
                      // "Approvals 3"); the count is said in the title.
                      <span
                        aria-hidden="true"
                        title={String(item.badge)}
                        className="ml-auto rounded-full bg-[var(--accent)] px-1.5 text-[10px] font-semibold leading-4 text-[var(--accent-ink)]"
                      >
                        {item.badge}
                      </span>
                    ) : null}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
    </nav>
  );
}
