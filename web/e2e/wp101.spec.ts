import { expect, test } from '@playwright/test';
import { visit } from './helpers';
import { DEMO_UNAVAILABLE } from '../lib/mock/tenders';

/**
 * WP-101 (persona round of 24 October 2026, search; docs/verification/round3/wp101-selfcheck.md): a list that could not be read is
 * an error with "Try again", never "No tenders match"; a notice number opens the list on every status; the CPV picker's words
 * reach the supplier filter (ammunition is the group 353 and 2461, cyber the security software and audit codes).
 */

test('a tender list the data service could not answer is an error with Try again, not an empty result', async ({ page }) => {
  const res = await page.goto(`/tenders?q=${DEMO_UNAVAILABLE}`, { waitUntil: 'load' });
  expect(res?.status()).toBe(200);
  const main = page.locator('#main');
  await expect(main.getByRole('heading', { name: 'We could not load tenders' })).toBeVisible();
  await expect(main.getByText('No tenders match these filters')).toHaveCount(0);
  const retry = main.getByRole('button', { name: 'Try again' });
  await expect(retry).toBeVisible();
  // the filters are kept, and Try again reads the list again (here it fails again, so the error stays)
  await expect(main.getByRole('searchbox').first()).toHaveValue(DEMO_UNAVAILABLE);
  await retry.click();
  await expect(main.getByRole('heading', { name: 'We could not load tenders' })).toBeVisible();
});

test('a notice number is looked for in every status', async ({ page }) => {
  await page.goto('/tenders?q=220199-2026', { waitUntil: 'load' });
  await expect(page).toHaveURL(/[?&]status=all(&|$)/);
  // a status chosen is kept
  await page.goto('/tenders?q=220199-2026&status=open', { waitUntil: 'load' });
  await expect(page).toHaveURL(/status=open/);
  // the global search reads it in every status too, and its tenders' See all opens the list so (a notice of the demo data)
  await page.goto('/search?q=561204-2026', { waitUntil: 'load' });
  await expect(page.locator('#main a[href="/tenders?q=561204-2026&status=all"]').first()).toBeVisible();
});

test('the supplier filter reads ammunition and cyber as their codes', async ({ page }) => {
  await visit(page, '/suppliers?product=ammunition', { title: /supplier map/i, h1: 'Companies' });
  const status = page.locator('#main').getByRole('status').filter({ hasText: /“ammunition” is read as/ });
  await expect(status).toContainText('35300000');
  await expect(status).toContainText('24610000');
  await visit(page, '/suppliers?product=cyber', { title: /supplier map/i, h1: 'Companies' });
  await expect(page.locator('#main').getByRole('status').filter({ hasText: /“cyber” is read as/ })).toContainText('48730000');
});
