import { Rss } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { useSite } from "@/lib/site";

/**
 * "Subscribe": the RSS feed of one category or one page (backend
 * routers/feeds.py). A plain link to the XML -- every feed reader takes the
 * address, and the browser shows what it is. `path` is the public address
 * the feed follows, without /feed.xml.
 */
export function FeedLink({ path, className = "" }: { path: string; className?: string }) {
  const { t } = useI18n();
  const { lang, multilingual } = useContentLang();
  const { site } = useSite();
  const query = multilingual && lang !== site.default_language ? `?lang=${encodeURIComponent(lang)}` : "";
  return (
    <a
      href={`${path}/feed.xml${query}`}
      className={`inline-flex items-center gap-1 text-sm text-[var(--muted)] hover:text-[var(--accent)] ${className}`}
    >
      <Rss className="h-3.5 w-3.5" aria-hidden="true" />
      {t("feed.subscribe")}
    </a>
  );
}
