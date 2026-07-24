import {defineConfig, devices} from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  outputDir: '../../local-data/test-artifacts/workforce-portal/playwright',
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [
    ['list'],
    [
      'html',
      {
        open: 'never',
        outputFolder:
          '../../local-data/test-artifacts/workforce-portal/playwright-report',
      },
    ],
  ],
  use: {
    baseURL: 'http://127.0.0.1:3002',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:3002',
    reuseExistingServer: !process.env.CI,
  },
  projects: [{name: 'chromium', use: {...devices['Desktop Chrome']}}],
});
