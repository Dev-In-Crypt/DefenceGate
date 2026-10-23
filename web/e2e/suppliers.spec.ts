import { expect, test } from '@playwright/test';
import { openAbout, pace, visit } from './helpers';

/**
 * The supplier map (WP-37): /suppliers and a supplier's page. Read-only. The same file runs against a local build
 * with demo data (five invented suppliers, lib/mock/suppliers.ts) and against a real site, so it asks for shapes and checks
 * the content only where there is some.
 */

test('/suppliers: what the map covers, the search, and the list or the honest empty state', async ({ page }) => {
  await visit(page, '/suppliers', {
    title: /supplier map/i,
    h1: 'Companies',
  });
  // WP-88: the method, coverage and caveats are in the collapsed About this data (owner-approved copy change, 22 Oct 2026)
  await openAbout(page);
  for (const t of ['How we count', 'TED holds only part of']) await expect(page.getByText(t).first()).toBeVisible();
  const search = page.getByRole('search', { name: 'Find suppliers' });
  await expect(search.getByLabel('Company name')).toBeVisible();
  await expect(search.getByLabel(/^Supplier's country/)).toBeVisible();
  await expect(search.getByLabel(/^Buyer's country/)).toBeVisible();
  await expect(search.getByLabel(/^CPV code/)).toBeVisible();
  await expect(page.locator('#results-heading')).toBeVisible();
  await pace(page);
});

test('/suppliers?country=XX&q=...: a search that finds nothing says so and offers a way back', async ({ page }) => {
  await visit(page, '/suppliers?country=ZZ&q=nonexistentcompanyname', { title: /supplier map/i, h1: 'Companies' });
  await expect(page.getByText('No suppliers match')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Clear filters' })).toHaveAttribute('href', '/suppliers');
});

test('a supplier page: its notices, the coverage caveat and no ranking, when the map has suppliers', async ({ page }) => {
  await page.goto('/suppliers');
  const first = page.locator('#results-heading').locator('xpath=following::ul[1]//a').first();
  if ((await first.count()) === 0) {
    await expect(page.getByText('No suppliers match')).toBeVisible();
    return;
  }
  await Promise.all([page.waitForURL(/\/suppliers\/\d+/), first.click()]);
  await expect(page.locator('h1').first()).not.toBeEmpty();
  await expect(page.getByRole('heading', { name: 'Contracts per year' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'The notices' })).toBeVisible();
  // WP-88: the method, coverage and caveats are in the collapsed About this data (owner-approved copy change, 22 Oct 2026)
  await openAbout(page);
  await expect(page.getByText(/TED holds only part of European defence/)).toBeVisible();
  // The map carries no ranking, share or contract total: nothing on the page says so.
  await expect(page.getByText(/market share|top supplier|single point of failure|sole source/i)).toHaveCount(0);
  await pace(page);
});

// WP-43 (verification 3): "drone", "explosives" and "body armour" found nothing; "tank" found heating tanks.
for (const [word, code, title] of [['drone', '35613000', 'Unmanned aerial vehicles'], ['explosives', '24600000', 'Explosives'],
  ['body armour', '35815000', 'Garments for anti-ballistic protection'], ['tank', '35411000', 'Battle tanks']] as const) {
  test(`/suppliers?product=${word}: the word is read as CPV codes and the page shows which`, async ({ page }) => {
    await visit(page, `/suppliers?product=${encodeURIComponent(word)}`, { title: /supplier map/i, h1: 'Companies' });
    const status = page.locator('#main').getByRole('status').filter({ hasText: /is read as/ });
    await expect(status).toContainText(`${code} ${title}`);
    await expect(page.locator('#main').getByText(/No code in the CPV finder has/)).toHaveCount(0);
  });
}

test('an address that is not a supplier is a 404', async ({ page }) => {
  const response = await page.goto('/suppliers/999999999-nobody');
  expect(response!.status()).toBe(404);
});
