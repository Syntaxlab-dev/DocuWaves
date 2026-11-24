import { useId, useState, type ReactNode } from "react";

/**
 * A term from the project's glossary (lib/glossary.ts), with its definition
 * in a bubble on hover, on focus (it is reachable with Tab) and on tap.
 *
 * The definition is also in a `hidden` element the term is described by:
 * a screen reader announces it on focus, while copying the paragraph does
 * not pick it up and the page's text stays what the author wrote.
 */
export function GlossaryTerm({ term, definition, children }: { term: string; definition: string; children: ReactNode }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <span
      className="glossary-term"
      tabIndex={0}
      aria-describedby={id}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={(event) => {
        if (event.key === "Escape") setOpen(false);
      }}
    >
      {children}
      <span id={id} hidden>
        {definition}
      </span>
      {open && (
        <span className="glossary-tip" aria-hidden="true">
          <strong>{term}</strong>
          {definition}
        </span>
      )}
    </span>
  );
}
