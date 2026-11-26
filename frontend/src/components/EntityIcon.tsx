// A project's or category's icon: an emoji, as it always was, or -- written
// `lucide:<name>` in the YAML -- one of a small set of line icons, for
// documentation that wants one consistent look instead of a mix of emoji
// that every operating system draws differently.
import { useEffect, useRef, useState } from "react";
import {
  Archive, BarChart3, Book, BookOpen, Bot, Boxes, Briefcase, Bug, Cloud, Code, Cog, Compass, Cpu, Database,
  FileText, Flag, FolderOpen, GitBranch, Globe, GraduationCap, Heart, HelpCircle, Home, Key, Languages,
  Layers, LayoutGrid, LifeBuoy, Lightbulb, Lock, Mail, Map, MessageCircle, Package, Palette, Plug, Rocket,
  Search, Server, Shield, ShoppingCart, Smartphone, Sparkles, Star, Tag, Terminal, Users, Wrench, Zap,
  type LucideIcon,
} from "lucide-react";
import { useI18n } from "@/lib/i18n";

export const ICON_PREFIX = "lucide:";

/** The set offered in the picker. Named in kebab-case, the way lucide's own
 *  catalogue names them, so a hand-written `lucide:book-open` just works. */
export const ICONS: Record<string, LucideIcon> = {
  rocket: Rocket, "book-open": BookOpen, book: Book, "file-text": FileText, "folder-open": FolderOpen,
  "graduation-cap": GraduationCap, compass: Compass, map: Map, lightbulb: Lightbulb, sparkles: Sparkles,
  "help-circle": HelpCircle, "life-buoy": LifeBuoy, "message-circle": MessageCircle, users: Users, heart: Heart,
  star: Star, flag: Flag, tag: Tag, home: Home, search: Search,
  code: Code, terminal: Terminal, "git-branch": GitBranch, bug: Bug, plug: Plug, cpu: Cpu, server: Server,
  database: Database, cloud: Cloud, globe: Globe, smartphone: Smartphone, package: Package, boxes: Boxes,
  layers: Layers, "layout-grid": LayoutGrid, cog: Cog, wrench: Wrench, zap: Zap, bot: Bot, palette: Palette,
  languages: Languages, shield: Shield, lock: Lock, key: Key, mail: Mail, "bar-chart": BarChart3,
  "shopping-cart": ShoppingCart, briefcase: Briefcase, archive: Archive,
};

/** Renders the icon, or nothing for an empty one or a `lucide:` name this
 *  version doesn't have (rather than printing the raw name). */
export function EntityIcon({ icon, className = "h-4 w-4" }: { icon?: string | null; className?: string }) {
  if (!icon) return null;
  if (icon.startsWith(ICON_PREFIX)) {
    const Icon = ICONS[icon.slice(ICON_PREFIX.length)];
    return Icon ? <Icon className={`inline-block shrink-0 text-[var(--accent)] ${className}`} aria-hidden="true" /> : null;
  }
  return <span aria-hidden="true">{icon}</span>;
}

/** The icon field of the project and category forms: type an emoji as
 *  before, or pick one of the set. */
export function IconField({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
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

  return (
    <div ref={box} className="relative flex items-center gap-2">
      {value && (
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[var(--border)] text-lg">
          <EntityIcon icon={value} className="h-5 w-5" />
        </span>
      )}
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="h-9 min-w-0 flex-1 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-sm outline-none focus:border-[var(--accent)]"
      />
      <button
        type="button"
        aria-expanded={open}
        aria-label={t("admin.iconPick")}
        title={t("admin.iconPick")}
        onClick={() => setOpen((v) => !v)}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[var(--border)] hover:bg-[var(--surface-2)]"
      >
        <LayoutGrid className="h-4 w-4" aria-hidden="true" />
      </button>
      {open && (
        <div
          role="listbox"
          aria-label={t("admin.iconPick")}
          className="absolute left-0 top-full z-30 mt-1 grid w-72 max-w-[calc(100vw-2rem)] grid-cols-8 gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-2 shadow-lg"
        >
          {Object.entries(ICONS).map(([name, Icon]) => {
            const id = ICON_PREFIX + name;
            return (
              <button
                key={name}
                type="button"
                role="option"
                aria-selected={value === id}
                title={name}
                aria-label={name}
                onClick={() => {
                  onChange(id);
                  setOpen(false);
                }}
                className={`flex h-8 w-8 items-center justify-center rounded-md hover:bg-[var(--surface-2)] ${
                  value === id ? "bg-[var(--accent-soft)] text-[var(--accent)]" : ""
                }`}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
