import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests of the public site. They only read: no form that stores anything is submitted (the home
 * form is a GET to /tenders), nothing is signed in, and the calls are at human speed (one worker, a pause after
 * each page: E2E_PACE_MS, 700 ms by default).
 *
 *   E2E_BASE_URL   the site to test. Unset: `next start` of the local build on 127.0.0.1:3000.
 *   E2E_PACE_MS    pause after each page in milliseconds (0 in CI against a local build).
 *   E2E_PORT       the local site's port (3000). The fake-API site is on E2E_PORT + 100, the fake API on E2E_PORT + 1010.
 *
 * Against production:  E2E_BASE_URL=https://defencegatehub.com npx playwright test
 * Against a build:     npm run build && npx playwright test        (see .github/workflows/web.yml)
 *
 * WP-128: the tests tagged @fake-api read numbers no demo data has (e2e/support/fake-api.mjs: 593 deadlines in a month, a closed
 * list of 287,634, a paged feed of 2,311 changes). Against a local build they run in every run, in their own projects, on a second
 * `next start` of the same build that reads the fake API (DG_API_URL); they used to need E2E_FAKE_API=1 and a site started by
 * hand, no run set it, and three of them went stale unnoticed. Against E2E_BASE_URL they run only with E2E_FAKE_API=1 (that site
 * must read the fake).
 */
const external = process.env.E2E_BASE_URL;
const port = Number(process.env.E2E_PORT ?? 3000);
const fakeSitePort = port + 100;
const fakeApiPort = port + 1010;
const FAKE = /@fake-api/;
const desktop = { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } };
const mobile = { ...devices['Pixel 5'], viewport: { width: 375, height: 812 } };
const others = external && process.env.E2E_FAKE_API ? {} : { grepInvert: FAKE };
const fake = { grep: FAKE, testMatch: ['wp52b-api.spec.ts', 'wp127-api.spec.ts', 'wp63.spec.ts', 'wp132-api.spec.ts'] };

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
    { name: 'desktop', use: desktop, ...others },
    { name: 'mobile-375', use: mobile, ...others },
    ...(external ? [] : [
      { name: 'fake-api-desktop', use: { ...desktop, baseURL: `http://127.0.0.1:${fakeSitePort}` }, ...fake },
      { name: 'fake-api-mobile-375', use: { ...mobile, baseURL: `http://127.0.0.1:${fakeSitePort}` }, ...fake },
    ]),
  ],
  webServer: external
    ? undefined
    : [
        {
          command: `npx next start -p ${port} -H 127.0.0.1`,
          url: `http://127.0.0.1:${port}/`,
          reuseExistingServer: true,
          timeout: 120_000,
        },
        { command: `node e2e/support/fake-api.mjs ${fakeApiPort}`, url: `http://127.0.0.1:${fakeApiPort}/v1/sources`, reuseExistingServer: true, timeout: 30_000 },
        {
          command: `npx next start -p ${fakeSitePort} -H 127.0.0.1`,
          url: `http://127.0.0.1:${fakeSitePort}/calendar`,
          env: { DG_API_URL: `http://127.0.0.1:${fakeApiPort}` },
          reuseExistingServer: true,
          timeout: 120_000,
        },
      ],
});
