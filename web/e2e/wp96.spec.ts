import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-96 (persona round of 23 October 2026, A2): a buyer counts what its tender list shows and names the military goods among
 * them; a supplier names its curated company group with the source, and the group lists its companies; the market names the set
 * it counts and waits with the amendment share; the search leads from a buyer's name to its own open tenders. Mock build (lib/mock).
 */

test('a buyer page counts its open tenders in the list default and names the military goods and works among them', async ({ page }) => {
  await visit(page, '/buyers/1-demo-armaments-agency', { title: /Demo Armaments Agency/i, h1: 'Demo Armaments Agency' });
  await expect(page.locator('[data-open-core]')).toHaveText(/^\d+ of them military goods and works$/);
  await expect(page.getByText(/Counts cover the notices the tender list shows for this buyer under All defence/)).toBeVisible();
});

test('a supplier names its curated group and its source, and the group view lists the companies', async ({ page }) => {
  await visit(page, '/suppliers/1-demo-airframes-gmbh', { title: /Demo Airframes GmbH/, h1: 'Demo Airframes GmbH' });
  const group = page.locator('[data-company-group]');
  await expect(group).toContainText('Part of the Demo group');
  await expect(group).toContainText('Source of the list: Demo group list (demo data).');
  await group.getByRole('link', { name: 'Demo group' }).click();
  await expect(page).toHaveURL(/\/suppliers\?group=demo$/);
  await expect(page.locator('[data-group-view]')).toContainText('nothing is merged across them');
});

test('the market names the set it counts, links it in the tender list, and waits with the amendment share', async ({ page }) => {
  await visit(page, '/market', { title: /Market overview/, h1: 'Market overview' });
  const scope = page.locator('[data-market-scope]');
  await expect(scope).toContainText('military goods and works only');
  await expect(scope.getByRole('link')).toHaveAttribute('href', '/tenders?status=all&scope=core');
  await expect(page.locator('[data-amendments-pending]')).toContainText('Not shown yet');
});

test('a search for a buyer leads to the buyer\'s own open tenders', async ({ page }) => {
  await visit(page, '/search?q=Demo%20Armaments', { title: /Search/, h1: 'Search' });
  const line = page.locator('[data-buyer-tenders]');
  await expect(line.getByRole('link')).toHaveAttribute('href', '/buyers/1-demo-armaments-agency');
  await expect(line).toContainText(/Demo Armaments Agency: \d+ open tenders?/);
});
