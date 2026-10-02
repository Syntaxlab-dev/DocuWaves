/** Which of the four kinds of line this is. Order matters: `+++` and `---`
 *  are the diff's own file headers and would otherwise be read as an added
 *  and a removed line. Anything that is neither content nor a hunk header
 *  (`diff --git`, `index`, `similarity`/`rename`, `new file mode`, git's
 *  "\ No newline at end of file") is git talking about the file rather than
 *  quoting it. */
function diffLineClass(line: string): string {
  if (line.startsWith("@@")) return "diff-line diff-line-hunk";
  if (line.startsWith("+++") || line.startsWith("---")) return "diff-line diff-line-meta";
  if (line.startsWith("+")) return "diff-line diff-line-add";
  if (line.startsWith("-")) return "diff-line diff-line-del";
  if (line.startsWith(" ")) return "diff-line";
  return "diff-line diff-line-meta";
}

/** A unified diff, rendered by hand -- see the .diff-* rules in index.css for
 *  why there is no library here. Each line keeps its own leading +/-, so
 *  added and removed stay distinguishable without relying on the colour. */
export function DiffView({ diff }: { diff: string }) {
  const lines = diff.replace(/\n+$/, "").split("\n");
  return (
    <div className="diff-view max-h-[26rem] overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--surface-2)] py-2">
      {lines.map((line, index) => (
        // An empty line still needs a box to draw its background in.
        <span key={index} className={diffLineClass(line)}>
          {line || " "}
        </span>
      ))}
    </div>
  );
}
