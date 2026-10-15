import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests of the public site. They only read: no form that stores anything is submitted (the home
 * form is a GET to /tenders), nothing is signed in, and the calls are at human speed (one worker, a pause after
 * each page: E2E_PACE_MS, 700 ms by default).
 *
 *   E2E_BASE_URL   the site to test. Unset: `next start` of the local build on 127.0.0.1:3000.
 *   E2E_PACE_MS    pause after each page in milliseconds (0 in CI against a local build).
 *
 * Against production:  E2E_BASE_URL=https://defencegatehub.com npx playwright test
 * Against a build:     npm run build && npx playwright test        (see .github/workflows/web.yml)
 */
const external = process.env.E2E_BASE_URL;
const port = Number(process.env.E2E_PORT ?? 3000);

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: external ?? `http://127.0.0.1:${port}`,
    trace: 'off',
    // A site we do not own is asked politely and by name.
    userAgent: external ? 'DefenceGate-e2e/1.0 (read-only check)' : undefined,
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } } },
    { name: 'mobile-375', use: { ...devices['Pixel 5'], viewport: { width: 375, height: 812 } } },
  ],
  webServer: external
    ? undefined
    : {
        command: `npx next start -p ${port} -H 127.0.0.1`,
        url: `http://127.0.0.1:${port}/`,
        reuseExistingServer: true,
        timeout: 120_000,
      },
});
