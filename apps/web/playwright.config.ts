import { defineConfig } from "@playwright/test";

// scripts/test_browser.py owns isolated production servers and disposable PostGIS.
// Manual runs require explicit E2E URLs and the dedicated browser fixture database.
export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: false,
  workers: 1,
  // The first real database connection can consume the API's 5s connect budget.
  expect: { timeout: 10000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    browserName: "chromium",
    viewport: { width: 1440, height: 1050 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
