import { defineConfig, devices } from '@playwright/test';

/**
 * Gun Del Sol E2E Test Configuration
 * Tests the Next.js frontend (port 3000) against the FastAPI backend (port 5003)
 */
export default defineConfig({
  testDir: './tests/e2e',

  // Maximum time one test can run for
  timeout: 30 * 1000,

  // Test execution settings
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,

  // Reporter to use
  reporter: process.env.CI ? [['html'], ['github']] : [['html'], ['list']],

  // Shared settings for all projects
  use: {
    // Base URL for the Next.js frontend
    baseURL: 'http://localhost:3000',

    // Collect trace when retrying the failed test
    trace: 'on-first-retry',

    // Screenshot on failure
    screenshot: 'only-on-failure',

    // Video on failure
    video: 'retain-on-failure'
  },

  // Configure projects for major browsers
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ],

  // Run your local dev server before starting the tests
  webServer: [
    {
      // Backend server - use cross-platform command
      command: process.env.CI
        ? 'cd ../backend-repo/backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 5003'
        : 'cd ../solscan_hotkey/backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 5003',
      url: 'http://localhost:5003/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120 * 1000,
      stdout: 'pipe',
      stderr: 'pipe'
    },
    {
      command: 'pnpm dev',
      url: 'http://localhost:3000',
      reuseExistingServer: !process.env.CI,
      timeout: 120 * 1000,
      stdout: 'pipe',
      stderr: 'pipe'
    }
  ]
});
