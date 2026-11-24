import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests: a real browser against a real DocuWaves (backend plus
 * the built frontend), started fresh by e2e/serve.sh. Run them with
 * `npm run build && npm run e2e`.
 *
 * The files are named *.e2e.ts so vitest (`npm test`) never picks them up.
 * One worker, in order: the tests share one instance and build on what the
 * one before created, the way a person would use it.
 */
const port = Number(process.env.E2E_PORT ?? 8790);

export default defineConfig({
  testDir: "e2e",
  testMatch: "*.e2e.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    locale: "en-US",
    // Wide enough for the admin header to show every item instead of a menu.
    viewport: { width: 1400, height: 900 },
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1400, height: 900 } } }],
  webServer: {
    command: "bash e2e/serve.sh",
    url: `http://127.0.0.1:${port}/health`,
    reuseExistingServer: false,
    timeout: 60_000,
    env: { E2E_PORT: String(port) },
  },
});
