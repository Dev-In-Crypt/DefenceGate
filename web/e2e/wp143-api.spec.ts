import { expect, test } from '@playwright/test';

/**
 * WP-143 against the fake API (e2e/support/fake-api.mjs). At the r13 deploy of 26 October 2026 a just-started API answered "busy"
 * (503, Retry-After 2: every database connection taken) 121 times in 40 s and the site turned each into an error page. A busy
 * answer is now asked once more after its wait (web/lib/api.ts `http`); a statement time-out (Retry-After 5) is not retried.
 * Each project reads its own notice, so the fake's "busy the first time" holds for each.
 */

test('a busy answer of the API costs the visitor two seconds, not an error page', { tag: '@fake-api' }, async ({ page }, info) => {
  // a notice no earlier run has read: the site keeps a notice's answer in its fetch cache (.next/cache) across runs of one build
  const n = 777_000 + (info.project.name.includes('mobile') ? 500 : 0) + Math.floor(Math.random() * 500);
  const t0 = Date.now();
  const res = await page.goto(`/tenders/${n}-notice-${n}`);
  const took = Date.now() - t0;
  expect(res?.status()).toBe(200);
  await expect(page.getByRole('heading', { level: 1 })).toContainText(`Notice ${n}`);
  expect(took, `waited ${took} ms`).toBeGreaterThanOrEqual(1900);
  const asked = ((await (await page.request.get(`${apiBase(page.url())}/_requests`)).json()) as string[])
    .filter((r) => r.startsWith(`/v1/tenders/${n}-`) || r.startsWith(`/v1/tenders/${n}?`)).length;
  expect(asked, 'the busy answer was asked again').toBeGreaterThanOrEqual(2);
});

test('a statement time-out is not asked again', { tag: '@fake-api' }, async ({ page }, info) => {
  const n = 778_000 + info.parallelIndex * 10 + info.repeatEachIndex + (info.project.name.includes('mobile') ? 500 : 0);
  const t0 = Date.now();
  const res = await page.request.get(`/tenders/${n}-notice-${n}`);
  const took = Date.now() - t0;
  expect(res.status()).not.toBe(200);
  expect(took, `waited ${took} ms: a time-out must not wait for a retry`).toBeLessThan(1900);
});

test('a buyer withheld as a private person says so, and one removed on request keeps its words', { tag: '@fake-api' }, async ({ page }) => {
  await page.goto('/buyers/779001-x');
  const main = page.locator('main');
  await expect(main).toContainText('Name not shown: it identifies a private person.');
  await expect(main).not.toContainText('on request');
  expect(await page.locator('meta[name="robots"]').getAttribute('content')).toContain('noindex');
  await page.goto('/buyers/779002-x');
  await expect(page.locator('main')).toContainText('removed from DefenceGate on request');
});

/** The fake API is on the site's port + 910 (playwright.config.ts: site E2E_PORT + 100, API E2E_PORT + 1010). */
function apiBase(siteUrl: string): string {
  const u = new URL(siteUrl);
  return `http://127.0.0.1:${Number(u.port) + 910}`;
}
