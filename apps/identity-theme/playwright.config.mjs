import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: ["**/*.e2e.spec.mjs"],
  outputDir: "./test/artifacts/playwright",
  reporter: [["list"]],
  use: {
    baseURL: process.env.VFBIZ_KEYCLOAK_URL ?? "http://127.0.0.1:8080",
    locale: "vi-VN",
    colorScheme: "light",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
