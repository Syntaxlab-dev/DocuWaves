// Grey shimmering stand-ins for content that is still loading: the layout
// is there at once and fills in, instead of a "Loading..." line that jumps.

/** Lines of placeholder text in a block, for cards and panels. */
export function SkeletonLines({ rows = 3, label }: { rows?: number; label: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-3 py-1">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} aria-hidden="true">
          <div className="h-3.5 animate-pulse rounded bg-[var(--surface-2)]" style={{ width: `${70 - (i % 3) * 15}%` }} />
          <div className="mt-2 h-2.5 w-1/3 animate-pulse rounded bg-[var(--surface-2)]" />
        </div>
      ))}
    </div>
  );
}
