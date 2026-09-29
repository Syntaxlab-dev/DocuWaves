import { Children, isValidElement, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { activeTabIndex, chooseTab, useTabPreferences } from "@/lib/tabs";

/**
 * A tab group from `<!-- tabs -->` in a page (see lib/tabs.ts).
 *
 * `labels` come from the hast node, `children` are the rendered panels in the
 * same order. Inactive panels stay in the DOM (hidden), so printing -- where
 * every panel is shown under its name -- and the page's own layout do not
 * depend on which tab was open.
 */
export function Tabs({ labels, children }: { labels: string[]; children: ReactNode }) {
  const preferences = useTabPreferences();
  const active = activeTabIndex(labels, preferences);
  const baseId = useId();
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  // remark-rehype puts "\n" text between block elements; only the panels count.
  const panels = Children.toArray(children).filter(isValidElement);

  function select(index: number, focus = false) {
    const button = buttons.current[index];
    // Every group with the same tab switches with this one, and those above
    // it change height. Keep the tab that was clicked where it was on screen,
    // or the page jumps away from under the reader's pointer.
    const before = button?.getBoundingClientRect().top;
    if (focus) button?.focus({ preventScroll: true });
    chooseTab(labels[index]);
    requestAnimationFrame(() => {
      if (button && before !== undefined) window.scrollBy(0, button.getBoundingClientRect().top - before);
    });
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const last = labels.length - 1;
    const next =
      e.key === "ArrowRight" ? (active === last ? 0 : active + 1)
      : e.key === "ArrowLeft" ? (active === 0 ? last : active - 1)
      : e.key === "Home" ? 0
      : e.key === "End" ? last
      : null;
    if (next === null) return;
    e.preventDefault();
    select(next, true);
  }

  return (
    <div className="tabs">
      <div role="tablist" className="tabs-list" onKeyDown={onKeyDown}>
        {labels.map((label, index) => (
          <button
            key={index}
            ref={(el) => {
              buttons.current[index] = el;
            }}
            type="button"
            role="tab"
            id={`${baseId}-tab-${index}`}
            aria-selected={index === active}
            aria-controls={`${baseId}-panel-${index}`}
            tabIndex={index === active ? 0 : -1}
            className="tabs-tab"
            onClick={() => select(index)}
          >
            {label}
          </button>
        ))}
      </div>
      {panels.map((panel, index) => (
        <div
          key={index}
          role="tabpanel"
          id={`${baseId}-panel-${index}`}
          aria-labelledby={`${baseId}-tab-${index}`}
          hidden={index !== active}
          className="tabs-panel"
        >
          <p className="tabs-print-label" aria-hidden="true">{labels[index]}</p>
          {panel}
        </div>
      ))}
    </div>
  );
}
