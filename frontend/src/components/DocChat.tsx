import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { MessageCircle, Send, X } from "lucide-react";
import { api, ApiError, type ChatAnswer } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { useContentLang } from "@/lib/lang";
import { useProjectVersion } from "@/lib/version";
import { useSite } from "@/lib/site";

/**
 * Ask the documentation a question.
 *
 * Rendered on every reading page, and only when the operator has configured
 * a model -- an instance that has not gets no button, because a button that
 * explains it does nothing is worse than no button.
 *
 * WHAT IS ON SCREEN, and why it is this and not a chat transcript:
 *
 * - One question, one answer, and the SOURCES under it -- always, whether
 *   the answer cites them or not. The pages are the documentation; the
 *   answer is a summary of them, and a reader who wants to be sure has the
 *   originals one click away rather than having to search for them again.
 * - Which sources the answer actually used are marked. The rest are what it
 *   was offered and passed over, which is exactly what a reader whom the
 *   answer did not help wants to look at next.
 * - No conversation history, here or on the server. Each question is asked
 *   against the documentation, not against the last answer, and pretending
 *   otherwise would promise a memory that does not exist.
 *
 * The scope follows the reader: a question asked inside one project's v2.0
 * documentation is answered out of exactly those pages. That is the same
 * rule the search box follows, and for the same reason -- being answered
 * out of a release you are not reading is worse than not being answered.
 */
export function DocChat() {
  const { t } = useI18n();
  const { site } = useSite();
  const { lang, path } = useContentLang();
  const projectVersion = useProjectVersion();
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<ChatAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const chat = site.chat;

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  if (!chat?.enabled) return null;

  async function onAsk(event: FormEvent) {
    event.preventDefault();
    const asked = question.trim();
    if (!asked || busy) return;
    setBusy(true);
    setError(null);
    setAnswer(null);
    try {
      const result = await api.publicChat(asked, lang, projectVersion.projectSlug, projectVersion.version);
      setAnswer(result);
    } catch (err) {
      // The backend answers with a short token rather than a sentence, so
      // the reader gets one in their own language -- and the operator's
      // provider, model and error body stay in the operator's log.
      const reason = err instanceof ApiError ? err.message : "";
      setError(
        reason === "too_many_questions"
          ? t("chat.tooMany")
          : reason === "timeout"
            ? t("chat.timeout")
            : t("chat.failed"),
      );
    } finally {
      setBusy(false);
    }
  }

  /** Where a source's page lives, by the same rule the search results use:
   *  the version segment only when the reader is inside that project's
   *  non-default version. */
  function sourcePath(source: ChatAnswer["sources"][number]): string {
    const segment =
      projectVersion.projectSlug === source.project_slug && source.version ? `/${source.version}` : "";
    return path(`/p/${source.project_slug}${segment}/pages/${source.page_slug}`);
  }

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="doc-chat-launcher fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm font-medium shadow hover:border-[var(--accent)] hover:text-[var(--accent)]"
        >
          <MessageCircle className="h-4 w-4" aria-hidden="true" />
          {t("chat.launch")}
        </button>
      )}

      {open && (
        <div
          className="doc-chat-panel fixed bottom-4 right-4 z-40 flex max-h-[min(32rem,calc(100vh-2rem))] w-[min(26rem,calc(100vw-2rem))] flex-col rounded-lg border border-[var(--border)] bg-[var(--surface)] shadow"
          role="dialog"
          aria-label={t("chat.launch")}
        >
          <div className="flex items-center gap-2 border-b border-[var(--border)] px-3 py-2">
            <MessageCircle className="h-4 w-4" aria-hidden="true" />
            <span className="flex-1 text-sm font-medium">{t("chat.launch")}</span>
            <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={t("common.back")} onClick={() => setOpen(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto px-3 py-2 text-sm">
            {!answer && !error && !busy && (
              <>
                <p className="text-[var(--muted)]">{t("chat.intro")}</p>
                {/* Said before the first question, not after it: a reader
                    deciding what to type is entitled to know that the text
                    leaves this site, and which model reads it. */}
                <p className="mt-2 text-xs text-[var(--muted)]">
                  {t("chat.disclosure").replace("{model}", chat.model)}
                </p>
              </>
            )}

            {busy && <p className="text-[var(--muted)]">{t("chat.thinking")}</p>}
            {error && <p className="text-[var(--muted)]">{error}</p>}

            {answer?.no_sources && <p className="text-[var(--muted)]">{t("chat.noSources")}</p>}

            {answer && !answer.no_sources && (
              <>
                {/* Plain text, deliberately not rendered as Markdown: this
                    is a model's output on a public page, and the one thing
                    that must not be possible is for it to produce markup
                    that acts. `whitespace-pre-wrap` keeps its paragraphs
                    and lists readable without interpreting anything. */}
                <p className="whitespace-pre-wrap">{answer.answer}</p>

                <div className="mt-3 border-t border-[var(--border)] pt-2">
                  <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                    {t("chat.sources")}
                  </div>
                  <ul className="mt-1 flex flex-col gap-1">
                    {answer.sources.map((source) => (
                      <li key={`${source.project_slug}/${source.page_slug}`} className="text-sm">
                        <Link
                          to={sourcePath(source)}
                          onClick={() => setOpen(false)}
                          className={source.cited ? "text-[var(--accent)]" : "text-[var(--muted)]"}
                        >
                          [{source.n}] {source.title}
                        </Link>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-1.5 text-xs text-[var(--muted)]">{t("chat.checkSources")}</p>
                </div>
              </>
            )}
          </div>

          <form onSubmit={onAsk} className="flex items-center gap-2 border-t border-[var(--border)] px-3 py-2">
            <input
              ref={inputRef}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              maxLength={chat.max_question_length}
              placeholder={t("chat.placeholder")}
              className="h-9 flex-1 rounded-lg border border-[var(--border)] bg-[var(--bg)] px-2 text-sm"
            />
            <Button type="submit" size="icon" disabled={busy || !question.trim()} aria-label={t("chat.ask")}>
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </div>
      )}
    </>
  );
}
