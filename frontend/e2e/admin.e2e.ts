import { expect, test, type Page } from "@playwright/test";

/**
 * The path a new operator takes: set the instance up, sign in, write a
 * page, publish it, and find it on the public site. One instance for the
 * whole file (e2e/serve.sh), so each test starts where the last one ended.
 */

const ADMIN = { username: "admin", password: "e2e-password-123" };

/** Console errors and uncaught exceptions, collected per test: a panel
 *  that renders but throws on the way is a failure here too. */
function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

async function signIn(page: Page) {
  await page.goto("/admin");
  await page.getByLabel("Username").fill(ADMIN.username);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
  // The admin opens on the overview; the content has its own address.
  await page.getByRole("navigation", { name: "Admin" }).getByRole("link", { name: "Projects and pages" }).click();
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toHaveCount(0);
}

test.describe.configure({ mode: "serial" });

test("a fresh instance asks for the first admin", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/admin");
  await expect(page.getByText("Create the first admin account.")).toBeVisible();
  await page.getByLabel("Username").fill(ADMIN.username);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Set up" }).click();
  await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("a wrong password is refused, the right one signs in", async ({ page }) => {
  await page.goto("/admin");
  await page.getByLabel("Username").fill(ADMIN.username);
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Incorrect username or password.")).toBeVisible();
  await signIn(page);
});

test("a project, a category and a published page", async ({ page }) => {
  const errors = watchErrors(page);
  await signIn(page);
  await page.getByRole("heading", { name: "Projects" }).locator("..").getByRole("button").click();
  await page.getByRole("textbox", { name: "Name" }).fill("Handbook");
  await page.getByRole("textbox", { name: "Description" }).fill("Everything about the product.");
  await page.getByRole("button", { name: "Save" }).click();
  await page.getByText("Handbook", { exact: true }).click();
  await page.getByRole("heading", { name: "Categories" }).locator("..").getByRole("button").click();
  await page.getByRole("textbox", { name: "Name" }).fill("Getting started");
  await page.getByRole("button", { name: "Save" }).click();
  await page.getByRole("button", { name: "Getting started" }).click();
  await page.getByRole("heading", { name: "Pages" }).locator("..").getByRole("button").first().click();
  await page.getByRole("textbox", { name: "Title" }).fill("Installing the widget");
  await page.getByRole("button", { name: "Markdown" }).click();
  await page.locator("textarea").first().fill("Unpack the widget and plug it in.\n\n## Checking it works\n\nThe light turns green.\n");
  await page.getByRole("button", { name: "Draft" }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "History" })).toBeEnabled();
  expect(errors).toEqual([]);
});

test("the page is on the public site", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  // With one project, the homepage is that project's page.
  await expect(page.getByText("Everything about the product.")).toBeVisible();
  await page.getByRole("link", { name: /Getting started/ }).click();
  await page.getByRole("link", { name: /Installing the widget/ }).first().click();
  await expect(page).toHaveURL(/\/p\/handbook\/pages\/installing-the-widget$/);
  await expect(page.getByRole("heading", { name: "Installing the widget" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Checking it works" })).toBeVisible();
  await expect(page.getByText("The light turns green.")).toBeVisible();
  const feed = page.getByRole("link", { name: "Subscribe via RSS" });
  await expect(feed).toHaveAttribute("href", "/p/handbook/pages/installing-the-widget/feed.xml");
  expect((await page.request.get("/p/handbook/pages/installing-the-widget/feed.xml")).status()).toBe(200);
  expect(errors).toEqual([]);
});

test("search finds it", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("textbox", { name: "Search…" }).fill("green light");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Search results" })).toBeVisible();
  const hit = page.getByRole("link", { name: /Installing the widget/ });
  await expect(hit).toHaveAttribute("href", "/p/handbook/pages/installing-the-widget");
  await expect(hit.locator("mark").first()).toBeVisible();

  // Narrowed to the project, and widened again in one click.
  await page.goto("/search?q=green+light&project=handbook");
  await expect(page.getByLabel("Project")).toHaveValue("handbook");
  await expect(page.getByRole("link", { name: /Installing the widget/ })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page).toHaveURL(/\/search\?q=green\+light$/);
  await expect(page.getByRole("link", { name: /Installing the widget/ })).toBeVisible();
});

test("a glossary term explains itself on the page", async ({ page }) => {
  const errors = watchErrors(page);
  await signIn(page);
  const status = await page.evaluate(async () => {
    const r = await fetch("/api/admin/glossary", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: "handbook", version: "", text: "Plug: The connector on the cable.\n" }),
    });
    return r.status;
  });
  expect(status).toBe(200);
  await page.goto("/p/handbook/pages/installing-the-widget");
  const term = page.locator(".glossary-term", { hasText: "plug" });
  await expect(term).toHaveCount(1);
  await term.hover();
  await expect(page.locator(".glossary-tip")).toContainText("The connector on the cable.");
  await page.goto("/p/handbook/glossary");
  await expect(page.getByRole("heading", { name: "Glossary" })).toBeVisible();
  await expect(page.getByText("The connector on the cable.")).toBeVisible();
  expect(errors).toEqual([]);
});

test("the search widget works on another site", async ({ browser, baseURL }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  // Another origin embedding the widget: this instance under "localhost"
  // while the widget comes from 127.0.0.1. Both real loopback answers, so
  // Chrome's private-network rule (which a mocked page would trip) stays out.
  await page.goto(baseURL!.replace("127.0.0.1", "localhost") + "/robots.txt");
  await page.evaluate((src) => {
    const tag = document.createElement("script");
    tag.src = src;
    tag.dataset.project = "handbook";
    tag.dataset.newTab = "off";
    document.body.append(tag);
  }, `${baseURL}/widget.js`);
  await page.getByRole("button", { name: /Search the docs/ }).click();
  await page.getByRole("combobox", { name: "Search the docs" }).fill("widget");
  const hit = page.getByRole("option", { name: /Installing the widget/ });
  await expect(hit).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(`${baseURL}/p/handbook/pages/installing-the-widget`);
  await context.close();
});

test("a saved project can be read offline", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = watchErrors(page);
  await page.goto("/p/handbook");
  // The service worker takes over this page only once it is active.
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
  await page.getByRole("button", { name: "Save for offline reading" }).click();
  await expect(page.getByRole("button", { name: "Update the offline copy" })).toBeVisible({ timeout: 30_000 });
  expect(errors).toEqual([]);

  await context.setOffline(true);
  await page.goto("/p/handbook/pages/installing-the-widget");
  await expect(page.getByText("You are offline.")).toBeVisible();
  await expect(page.locator(".markdown-body")).toContainText("plug");
  await context.close();
});

async function openPageInEditor(page: Page, title: string) {
  await signIn(page);
  await page.getByRole("button", { name: "Handbook" }).click();
  await page.getByRole("button", { name: "Getting started" }).click();
  await page.getByRole("button", { name: title }).first().click();
  await expect(page.getByRole("textbox", { name: "Title" })).toHaveValue(title);
}

test("renaming a page keeps its old address working", async ({ page }) => {
  await openPageInEditor(page, "Installing the widget");
  await page.getByRole("textbox", { name: "Title" }).fill("Setting up the widget");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  await expect
    .poll(async () => (await page.request.get("/api/public/projects/handbook/pages/installing-the-widget", { maxRedirects: 0 })).status())
    .toBe(301);

  await page.goto("/p/handbook/pages/installing-the-widget");
  await expect(page).toHaveURL(/\/p\/handbook\/pages\/setting-up-the-widget$/);
  await expect(page.getByRole("heading", { name: "Setting up the widget" })).toBeVisible();
});

test("an unpublished page leaves the public site", async ({ page, request }) => {
  await openPageInEditor(page, "Setting up the widget");
  await page.getByRole("button", { name: "Published" }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "Draft" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();

  // A reader without a session: the editor's own browser may still see drafts.
  // Polled, because the button flips before the server has written the file.
  await expect
    .poll(async () => (await request.get("/api/public/projects/handbook/pages/setting-up-the-widget", { maxRedirects: 0 })).status())
    .toBe(404);
});

test("a draft can be scheduled and unscheduled", async ({ page }) => {
  const errors = watchErrors(page);
  await openPageInEditor(page, "Setting up the widget");
  await page.getByRole("button", { name: "Schedule publishing" }).click();
  await page.getByLabel("Publish on").fill("2031-03-01T09:30");
  await page.getByRole("button", { name: "Schedule", exact: true }).click();
  await expect(page.getByText(/Goes live on .*2031.* \(scheduled by admin\)/)).toBeVisible();
  await page.getByRole("button", { name: "Unschedule" }).click();
  await expect(page.getByRole("button", { name: "Schedule publishing" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("pages are published together from the list", async ({ page, request }) => {
  const errors = watchErrors(page);
  await signIn(page);
  await page.getByRole("button", { name: "Handbook" }).click();
  await page.getByRole("button", { name: "Getting started" }).click();
  await page.getByRole("checkbox", { name: "Select “Setting up the widget”" }).check();
  const toolbar = page.getByRole("toolbar", { name: "Bulk actions" });
  await expect(toolbar.getByText("1 selected")).toBeVisible();
  await toolbar.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(toolbar).toHaveCount(0);
  await expect
    .poll(async () => (await request.get("/api/public/projects/handbook/pages/setting-up-the-widget")).status())
    .toBe(200);
  expect(errors).toEqual([]);
});

test("text is replaced across the project", async ({ page, request }) => {
  const errors = watchErrors(page);
  await signIn(page);
  await page.getByRole("button", { name: "Handbook" }).click();
  await page.getByRole("button", { name: "Search and replace" }).click();
  await page.getByRole("textbox", { name: "Find" }).fill("light turns green");
  await page.getByRole("textbox", { name: "Replace with" }).fill("lamp turns blue");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("1 matches on 1 pages.")).toBeVisible();
  await page.getByRole("button", { name: "Replace in 1 pages" }).click();
  await expect(page.getByText("Replaced 1 occurrences on 1 pages.")).toBeVisible();
  await expect
    .poll(async () => (await (await request.get("/api/public/projects/handbook/pages/setting-up-the-widget")).json()).page?.markdown_content)
    .toContain("The lamp turns blue.");
  expect(errors).toEqual([]);
});

test("every admin panel opens without an error", async ({ page }) => {
  const errors = watchErrors(page);
  await signIn(page);
  const nav = page.getByRole("navigation", { name: "Admin" });
  for (const name of ["Branding", "Accounts", "Approvals", "Activity", "Insights", "API tokens", "Diagnostics", "Log", "Import", "Account"]) {
    await nav.getByRole("link", { name, exact: true }).click();
    // Every panel opens with a card title; seeing one means it rendered.
    await expect(page.locator("main, body").getByRole("heading", { level: 3 }).first()).toBeVisible();
    await page.waitForLoadState("networkidle");
  }
  expect(errors).toEqual([]);
});

test("a read-only account gets Write in one project", async ({ page, browser }) => {
  const errors = watchErrors(page);
  await signIn(page);
  const made = await page.request.post("/api/admin/users", {
    data: { username: "petra", password: "petra-password-123", role: "viewer" },
  });
  expect(made.status()).toBe(201);
  await page.getByRole("navigation", { name: "Admin" }).getByRole("link", { name: "Accounts", exact: true }).click();
  await page.getByRole("button", { name: "Permissions per project" }).click();
  await page.getByRole("combobox", { name: "Permission in Handbook" }).selectOption("editor");
  await expect(page.getByText("1 project exception(s)")).toBeVisible();
  expect(errors).toEqual([]);

  // Petra, in a browser of her own: the editor is writable in Handbook.
  const context = await browser.newContext();
  const petra = await context.newPage();
  await petra.goto("/admin");
  await petra.getByLabel("Username").fill("petra");
  await petra.getByLabel("Password").fill("petra-password-123");
  await petra.getByRole("button", { name: "Sign in" }).click();
  await petra.getByRole("navigation", { name: "Admin" }).getByRole("link", { name: "Projects and pages" }).click();
  await petra.getByText("Handbook", { exact: true }).click();
  await expect(petra.getByRole("heading", { name: "Categories" })).toBeVisible();
  await expect(petra.getByText("Your account can read this project but not change it.")).toHaveCount(0);
  await expect(petra.getByText("Your account can read the admin area but not change anything.")).toHaveCount(0);
  // ...and creating a project, which is instance-wide, is still refused.
  const origin = new URL(petra.url()).origin;
  const refused = await petra.request.post("/api/admin/projects", { data: { name: "Elsewhere" }, headers: { Origin: origin } });
  expect(refused.status()).toBe(403);
  expect((await refused.json()).detail).toMatch(/single projects only/);
  await context.close();
});

test("a screenshot is pixelated in the image editor", async ({ page }) => {
  const errors = watchErrors(page);
  await openPageInEditor(page, "Setting up the widget");
  // A real PNG, drawn in the browser: half white, half black.
  const dataUrl = await page.evaluate(() => {
    const c = document.createElement("canvas");
    c.width = 240;
    c.height = 120;
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, 240, 120);
    ctx.fillStyle = "#000";
    ctx.fillRect(120, 0, 120, 120);
    return c.toDataURL("image/png");
  });
  await page.locator('input[type="file"][accept*=".png"]').setInputFiles({
    name: "secret-shot.png",
    mimeType: "image/png",
    buffer: Buffer.from(dataUrl.split(",")[1], "base64"),
  });
  await expect(page.getByTitle("secret-shot.png")).toBeVisible();

  await page.getByTitle("secret-shot.png").locator("..").getByRole("button", { name: "Edit" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit image" });
  await dialog.getByRole("radio", { name: "Pixelate" }).click();
  const canvas = dialog.getByLabel("The image being edited", { exact: false });
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height * 0.2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.8, { steps: 5 });
  await page.mouse.up();
  await dialog.getByRole("radio", { name: "Crop" }).click();
  await page.mouse.move(box.x + 2, box.y + 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height - 2, { steps: 5 });
  await page.mouse.up();
  await expect(dialog.getByText(/^1\d\d × 1\d\d px/)).toBeVisible();
  await dialog.getByRole("button", { name: "Save as a copy and insert" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByTitle("secret-shot-edited.png")).toBeVisible();
  expect(errors).toEqual([]);
});

test("a reviewer comments on a passage", async ({ page }) => {
  const errors = watchErrors(page);
  await signIn(page);
  await page.getByRole("heading", { name: "Projects" }).locator("..").getByRole("button").click();
  await page.getByRole("textbox", { name: "Name" }).fill("Policies");
  await page.getByLabel("Approval required").check();
  await page.getByRole("button", { name: "Save" }).click();
  await page.getByText("Policies", { exact: true }).click();
  await page.getByRole("heading", { name: "Categories" }).locator("..").getByRole("button").click();
  await page.getByRole("textbox", { name: "Name" }).fill("Rules");
  await page.getByRole("button", { name: "Save" }).click();
  await page.getByRole("button", { name: "Rules" }).click();
  await page.getByRole("heading", { name: "Pages" }).locator("..").getByRole("button").first().click();
  await page.getByRole("textbox", { name: "Title" }).fill("Holidays");
  await page.getByRole("button", { name: "Markdown" }).click();
  const area = page.locator("textarea").first();
  await area.fill("Everyone gets thirty days off. Ask your lead first.\n");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "History" })).toBeEnabled();

  // Select a passage in the Markdown editor, then comment on it.
  await area.evaluate((el: HTMLTextAreaElement) => {
    el.focus();
    const at = el.value.indexOf("thirty days");
    el.setSelectionRange(at, at + "thirty days".length);
  });
  await page.getByRole("button", { name: "Comment on selection" }).click();
  await page.getByLabel("What should change here?").fill("It is twenty-eight.");
  await page.getByRole("button", { name: "Comment", exact: true }).click();
  const item = page.getByRole("listitem").filter({ hasText: "It is twenty-eight." });
  await expect(item).toBeVisible();
  await expect(item.getByText("thirty days", { exact: true })).toBeVisible();
  await expect(page.getByText("Comments (1 open)")).toBeVisible();

  await item.getByRole("button", { name: "Done" }).click();
  await expect(page.getByText("Comments (0 open)")).toBeVisible();
  await page.getByRole("button", { name: "Show 1 done" }).click();
  await expect(page.getByText("done by admin")).toBeVisible();
  expect(errors).toEqual([]);
});

test("a category nests inside another", async ({ page }) => {
  const errors = watchErrors(page);
  await signIn(page);
  await page.getByRole("button", { name: "Handbook" }).click();
  await page.getByRole("heading", { name: "Categories" }).locator("..").getByRole("button").click();
  await page.getByRole("textbox", { name: "Name" }).fill("Wiring");
  await page.getByLabel("Inside").selectOption({ label: "Getting started" });
  await page.getByRole("button", { name: "Save" }).click();
  await page.getByRole("button", { name: "Wiring" }).click();
  await page.getByRole("heading", { name: "Pages" }).locator("..").getByRole("button").first().click();
  await page.getByRole("textbox", { name: "Title" }).fill("Mains connection");
  await page.getByRole("button", { name: "Markdown" }).click();
  await page.locator("textarea").first().fill("Use the supplied cable.\n");
  await page.getByRole("button", { name: "Draft" }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "History" })).toBeEnabled();

  // The project shows only its top level; the subsection is a tile inside.
  await page.goto("/p/handbook");
  // A tile counts what is under it, subsection included.
  await expect(page.getByRole("link", { name: /^Getting started 2 Pages/ })).toBeVisible();
  await expect(page.locator("main").getByRole("link", { name: /^Wiring \d/ })).toHaveCount(0);
  await page.goto("/p/handbook/c/getting-started");
  await page.locator("main").getByRole("link", { name: /^Wiring \d/ }).click();
  await expect(page).toHaveURL(/\/p\/handbook\/c\/wiring$/);
  await expect(page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("link", { name: "Getting started" })).toBeVisible();
  await page.getByRole("link", { name: "Mains connection" }).first().click();
  await expect(page.getByRole("heading", { name: "Mains connection" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("the admin opens on an overview that leads to the work", async ({ page }) => {
  const errors = watchErrors(page);
  await signIn(page);
  await page.getByRole("navigation", { name: "Admin" }).getByRole("link", { name: "Overview" }).click();
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recently edited" })).toBeVisible();
  // A page edited earlier in this run opens straight in the editor.
  await page.getByRole("heading", { name: "Recently edited" }).locator("../..").getByRole("button").first().click();
  await expect(page).toHaveURL(/\/admin\/content\/handbook\/[^?]+\?page=/);
  await expect(page.getByRole("button", { name: "Save" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("deleting asks in the app, and a page can be brought back", async ({ page }) => {
  const errors = watchErrors(page);
  await signIn(page);
  await page.getByRole("button", { name: "Handbook" }).click();
  const cats = page.getByRole("heading", { name: "Categories" }).locator("../..");
  await page.getByRole("heading", { name: "Categories" }).locator("..").getByRole("button").click();
  await page.getByRole("textbox", { name: "Name" }).fill("Scratch");
  await page.getByRole("button", { name: "Save" }).click();
  await cats.getByRole("button", { name: "Scratch" }).click();
  await expect(page.getByText("This category has no pages yet.")).toBeVisible();
  await page.getByRole("heading", { name: "Pages" }).locator("..").getByRole("button").first().click();
  await page.getByRole("textbox", { name: "Title" }).fill("Temporary");
  await page.getByRole("button", { name: "Markdown" }).click();
  await page.locator("textarea").first().fill("Gone soon.\n");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "History" })).toBeEnabled();

  // A page goes at once, with a few seconds to take it back.
  await cats.getByRole("button", { name: "Scratch" }).click();
  const pages = page.getByRole("heading", { name: "Pages" }).locator("../..");
  const row = pages.locator("div.group").filter({ hasText: "Temporary" });
  await row.hover();
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(row).toHaveCount(0);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(row).toHaveCount(1);
  await row.hover();
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(row).toHaveCount(0);
  await page.waitForTimeout(6500);
  // The address keeps the selection: a reload lands in the same category.
  await expect(page).toHaveURL(/\/admin\/content\/handbook\/scratch$/);
  await page.reload();
  await expect(page.getByText("This category has no pages yet.")).toBeVisible();
  const crumbs = page.getByRole("navigation", { name: "Path" });
  await expect(crumbs.getByText("Scratch")).toHaveAttribute("aria-current", "page");
  // A breadcrumb steps up, and Back steps down again.
  await crumbs.getByRole("button", { name: "Handbook" }).click();
  await expect(page).toHaveURL(/\/admin\/content\/handbook$/);
  await expect(page.getByText("This category has no pages yet.")).toHaveCount(0);
  await page.goBack();
  await expect(page).toHaveURL(/\/admin\/content\/handbook\/scratch$/);
  await expect(crumbs.getByText("Scratch")).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("This category has no pages yet.")).toBeVisible();

  // A category asks first, in a dialog of the app's own.
  const category = cats.locator("div.group").filter({ has: page.getByRole("button", { name: "Scratch" }) });
  await category.hover();
  await category.getByRole("button", { name: "Delete" }).click();
  const dialog = page.getByRole("alertdialog", { name: 'Delete the category "Scratch"?' });
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(cats.getByRole("button", { name: "Scratch" })).toBeVisible();
  await category.hover();
  await category.getByRole("button", { name: "Delete" }).click();
  await dialog.getByRole("button", { name: "Delete" }).click();
  await expect(cats.getByRole("button", { name: "Scratch" })).toHaveCount(0);
  expect(errors).toEqual([]);
});
