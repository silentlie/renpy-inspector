import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './runtime-e2e',
  testMatch: '**/*.spec.js',
  timeout: 145000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', {
    open: 'never', outputFolder: 'playwright-runtime-report',
  }]],
  use: {
    ...devices['Desktop Chrome'],
    browserName: 'chromium',
    headless: true,
    viewport: { width: 1366, height: 768 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  outputDir: 'test-results/runtime-playwright',
});
