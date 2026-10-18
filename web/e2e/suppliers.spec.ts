import { expect, test } from '@playwright/test';
import { pace, visit } from './helpers';

/**
 * The supplier map (WP-37): /suppliers and a supplier's page. Read-only. The same file runs against a local build
 * with demo data (no suppliers there: the page says so) and against a real site, so it asks for shapes and checks
 * the content only where there is some.
 */

test('/suppliers: what the map covers, the search, and the list or the honest empty state', async ({ page }) => {
  await visit(page, '/suppliers', {
    title: /supplier map/i,
    h1: 'Defence supplier map',
    text: ['What this map covers', 'TED holds only part of'],
  });
  const search = page.getByRole('search', { name: 'Find suppliers' });
  await expect(search.getByLabel('Company name')).toBeVisible();
  await expect(search.getByLabel(/^Country code/)).toBeVisible();
  await expect(search.getByLabel(/^CPV code/)).toBeVisible();
  await expect(page.locator('#results-heading')).toBeVisible();
  await pace(page);
});

test('/suppliers?country=XX&q=...: a search that finds nothing says so and offers a way back', async ({ page }) => {
  await visit(page, '/suppliers?country=ZZ&q=nonexistentcompanyname', { title: /supplier map/i, h1: 'Defence supplier map' });
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
  await expect(page.getByRole('heading', { name: 'Notices per year' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'The notices' })).toBeVisible();
  await expect(page.getByText(/TED holds only part of European defence/)).toBeVisible();
  // The map carries no ranking, share or contract total: nothing on the page says so.
  await expect(page.getByText(/market share|top supplier|single point of failure|sole source/i)).toHaveCount(0);
  await pace(page);
});

test('an address that is not a supplier is a 404', async ({ page }) => {
  const response = await page.goto('/suppliers/999999999-nobody');
  expect(response!.status()).toBe(404);
});
