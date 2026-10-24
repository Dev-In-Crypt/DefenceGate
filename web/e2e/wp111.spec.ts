import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-111 (round-4 re-check of 24 October 2026, p04): a buyer page names the variants it includes, behind a fold, and the
 * buyers list writes its counts as the buyer page does (thousands separated).
 */

test('the buyer page lists the names of the rows it includes', async ({ page }) => {
  await visit(page, '/buyers/1-demo-armaments-agency', { title: /Demo Armaments Agency/i, h1: 'Demo Armaments Agency' });
  const fold = page.locator('[data-variant-names]');
  await expect(fold).toBeVisible();
  await expect(fold.locator('summary')).toHaveText(/Includes 2 other name variants of this body: show the names/);
  await fold.locator('summary').click();
  await expect(fold.locator('li')).toHaveText(['Skarb Panstwa - Demo Armaments Agency', 'DEMO ARMAMENTS AGENCY, WARSZAWA']);
});

test('the buyers list writes its counts with the page number format', async ({ page }) => {
  await visit(page, '/buyers', { title: /Buyers/i, h1: /Buyers/i });
  const counts = page.locator('[data-buyer-tenders]');
  await expect(counts.first()).toBeVisible();
  for (const text of await counts.allTextContents()) expect(text).toMatch(/^\d{1,3}(,\d{3})*$/);
});
