import { defineConfig } from "@playwright/test";

export default defineConfig({
  expect: { timeout: 10_000 },
  forbidOnly: Boolean(process.env.CI),
  fullyParallel: false,
  outputDir: "../../local-data/test-artifacts/customer-portal/playwright",
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  reporter: process.env.CI ? "line" : "list",
  retries: process.env.CI ? 1 : 0,
  testDir: "./tests/e2e",
  timeout: 60_000,
  use: {
    baseURL: process.env.CUSTOMER_E2E_BASE_URL ?? "http://localhost:3001",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  workers: 1,
});
