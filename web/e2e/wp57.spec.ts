import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-57, suppliers and organisations (UX audit 19 October 2026): the country filter reads names and three-letter codes (M6), a product
 * word is a word of a CPV title (M7), organisation names keep their acronyms and legal forms (M8), and a project that states no
 * coordinator says so (M9). Read-only; runs against the demo data of the CI build (lib/mock).
 */

const SUPPLIERS = { title: /supplier map/i, h1: 'Companies' } as const;

test('/suppliers?country=Germany and ?country=DEU list what ?country=DE lists, and are not a 404', async ({ page }) => {
  await visit(page, '/suppliers?country=DE', SUPPLIERS);
  const byCode = await page.locator('#results-heading').innerText();
  expect(byCode).toMatch(/^Suppliers \(\d+\)$/);
  for (const given of ['Germany', 'germany', 'DEU', 'Deutschland']) {
    await visit(page, `/suppliers?country=${encodeURIComponent(given)}`, SUPPLIERS);
    await expect(page.locator('#results-heading')).toHaveText(byCode);
    await expect(page.getByRole('search', { name: 'Find suppliers' }).getByLabel(/^Supplier's country/)).toHaveValue(given);
  }
});

test('/suppliers?country=Atlantis is an answer that says it is not a country', async ({ page }) => {
  await visit(page, '/suppliers?country=Atlantis', SUPPLIERS);
  await expect(page.locator('#results-heading')).toHaveText('No suppliers');
  await expect(page.getByText('Not a country', { exact: true })).toBeVisible();
  await expect(page.getByText(/“Atlantis” is not a country code or an English country name/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Clear filters' })).toHaveAttribute('href', '/suppliers');
  // a good and a bad part together are not silently narrowed to the good one
  await visit(page, '/suppliers?country=DE,Atlantis', SUPPLIERS);
  await expect(page.getByText('Not a country', { exact: true })).toBeVisible();
});

test('/suppliers?product=gun reads guns, not gunmetal pipe fittings; ?product=fuel reads fuel, not fuelled submarines', async ({ page }) => {
  await visit(page, '/suppliers?product=gun', SUPPLIERS);
  const status = page.locator('#main').getByRole('status').filter({ hasText: /“gun”/ });
  await expect(status).toContainText(/Machine guns|Hand guns/);
  await expect(status).not.toContainText(/Gunmetal|35341100/);
  await visit(page, '/suppliers?product=fuel', SUPPLIERS);
  const fuel = page.locator('#main').getByRole('status').filter({ hasText: /“fuel”/ });
  await expect(fuel).not.toContainText(/nuclear fuelled|diesel fuelled/);
  await visit(page, '/suppliers?product=radar', SUPPLIERS);
  await expect(page.locator('#main').getByRole('status').filter({ hasText: /is read as/ })).toContainText('35722000 Radar');
});

test('organisation names keep the acronyms and legal forms of the source ("Sas" is SAS)', async ({ page }) => {
  await visit(page, '/organisations', { title: /organisations/i, h1: 'Companies' });
  await expect(page.getByRole('link', { name: 'Bravo Ingénierie SAS' }).first()).toBeVisible();
  await expect(page.getByText(/Ingénierie Sas\b/)).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Alpha Systems GmbH' }).first()).toBeVisible();
});

test('a project that states no coordinator says "Coordinator not stated"', async ({ page }) => {
  await visit(page, '/projects/299-delta', { title: /DELTA/, h1: 'DELTA' });
  await expect(page.getByText('Coordinator not stated.')).toBeVisible();
  await expect(page.getByText(/Coordinated by/)).toHaveCount(0);
  const members = page.getByRole('table', { name: /Members of the consortium/i });
  await expect(members.getByRole('row')).toHaveCount(3);
  await expect(members.getByText('Coordinator', { exact: true })).toHaveCount(0);
  // and a project that has one still says who
  await visit(page, '/projects/201-alpha', { title: /ALPHA/, h1: 'ALPHA' });
  await expect(page.getByText(/Coordinated by/i)).toContainText(/Alpha Systems/i);
  await expect(page.getByText('Coordinator not stated.')).toHaveCount(0);
});
