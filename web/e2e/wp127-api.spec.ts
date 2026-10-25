import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-127 against the fake API (e2e/support/fake-api.mjs): `/tenders?q=ammunition` waited 1.5 s on every view for scope counts that
 * answered 503. A search whose counts take 5 s is served without waiting for them, its scope choices without numbers; counts that
 * answer in time are shown. Skipped unless E2E_FAKE_API=1 (the site started with DG_API_URL pointing at the fake).
 */
test.skip(!process.env.E2E_FAKE_API, 'needs the fake API: E2E_FAKE_API=1 and a site started with DG_API_URL=http://127.0.0.1:4010');

test('slow scope counts do not hold the tender page up; counts in time are shown', async ({ page }) => {
  await page.request.get('/tenders?q=slowcounts');             // the first render of the route (compilation, caches) is not timed
  const t0 = Date.now();
  const slow = await page.request.get('/tenders?q=slowcounts');
  const took = Date.now() - t0;
  expect(slow.status()).toBe(200);
  expect(took, `the page took ${took} ms with counts that take 5 s`).toBeLessThan(3000);
  await visit(page, '/tenders?q=slowcounts', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.locator('#results-heading')).toContainText('1,522');
  expect(await page.content(), 'no scope numbers').not.toContain('(1,274)');
  await visit(page, '/tenders?q=fastcounts', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.getByText('(1,274)').first()).toBeAttached();
});
