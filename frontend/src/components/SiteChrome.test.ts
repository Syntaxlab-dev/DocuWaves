import { describe, expect, it } from "vitest";
import { footerColumns } from "./SiteChrome";

describe("footerColumns", () => {
  it("groups links by column in first-seen order, the rest stay loose", () => {
    const { columns, loose } = footerColumns([
      { label: "Blog", url: "/blog", column: "Company" },
      { label: "Imprint", url: "/imprint" },
      { label: "Status", url: "https://status.example.com", column: "Help" },
      { label: "Jobs", url: "/jobs", column: " Company " },
    ]);
    expect(columns.map(([title, links]) => [title, links.map((l) => l.label)])).toEqual([
      ["Company", ["Blog", "Jobs"]],
      ["Help", ["Status"]],
    ]);
    expect(loose.map((l) => l.label)).toEqual(["Imprint"]);
  });
});
