import { expect, test } from '@playwright/test';

/**
 * WP-144 item 5 against the fake API (e2e/support/fake-api.mjs; owner's decision of 26 October 2026): a buyer whose defence notices
 * are all outside the default scope (production's 9421, one dual-use notice) has a page. It says the notices are outside the
 * default scope, in the scope words of the site, lists them, and is not indexed (as the notices' own pages are not); the notice's
 * buyer line links to it.
 */

const BUYER = '/buyers/779003-dyrektor-urzedu-morskiego-w-gdyni';

test('a buyer of notices outside the default scope has a page that says so and lists them', { tag: '@fake-api' }, async ({ page }) => {
  const res = await page.goto(BUYER);
  expect(res?.status()).toBe(200);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Dyrektor Urzędu Morskiego w Gdyni');
  const note = page.locator('[data-outside-scope]');
  await expect(note).toContainText('None of this buyer’s notices is in the default scope, All defence (military goods and works and other purchases by armed forces).');
  await expect(note).toContainText('The notices listed here are under All notices: everything, also dual-use purchases of civil buyers');
  await expect(page.locator('section[aria-labelledby="earlier-tenders"] > ul > li')).toHaveCount(1);
  await expect(page.locator('section[aria-labelledby="earlier-tenders"]')).toContainText('Command and control system for the maritime office');
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/);
  await expect(page.locator('[data-top-suppliers-unavailable]')).toHaveCount(0);
  // the page's earlier list asked for All notices (the fake lists the notice only then; its log, as e2e/wp143-api.spec.ts reads
  // it: the site's port + 910, is shared with the other tests, whose notice page asks for this buyer's other notices too)
  const api = `http://127.0.0.1:${Number(new URL(page.url()).port) + 910}`;
  const asked = ((await (await page.request.get(`${api}/_requests`)).json()) as string[])
    .filter((r) => r.startsWith('/v1/tenders?') && r.includes('buyer=779003') && r.includes('status=closed'));
  expect(asked.some((r) => r.includes('scope=all'))).toBe(true);
});

test('the notice page of such a buyer links its buyer line to that page', { tag: '@fake-api' }, async ({ page }) => {
  const res = await page.goto('/tenders/779004-command-and-control-system-for-the-maritime-office');
  expect(res?.status()).toBe(200);
  await expect(page.locator(`main a[href="${BUYER}"]`).first()).toBeVisible();
});
