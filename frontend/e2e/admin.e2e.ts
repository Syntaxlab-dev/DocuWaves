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
  const nav = page.getByRole("banner").getByRole("navigation");
  for (const name of ["Branding", "Accounts", "Approvals", "Activity", "Insights", "API tokens", "Diagnostics", "Log", "Import", "Account"]) {
    await nav.getByRole("button", { name, exact: true }).click();
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
  await page.getByRole("banner").getByRole("navigation").getByRole("button", { name: "Accounts", exact: true }).click();
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
