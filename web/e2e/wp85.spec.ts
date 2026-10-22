import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-85 (owner decision of 22 October 2026): the supplier map counts the contracts the supplier report counts in "who to approach",
 * over the same three years. What this proves on the demo build (lib/mock): the page says so, the supplier's country and the buyer's
 * country are two labelled filters, a buyer country that is no country is an answer, and the profile counts contracts. The counts
 * themselves are proved against Postgres (backend/tests/integration/test_wp80_approach.py, test_supplier_map.py).
 */

const SUPPLIERS = { title: /supplier map/i, h1: 'Defence supplier map' } as const;

test('/suppliers says it covers the contracts of "who to approach", over three years', async ({ page }) => {
  await visit(page, '/suppliers', { ...SUPPLIERS, text: ['published in the last three years', 'the same contracts the supplier report counts'] });
  await expect(page.getByText(/from 2023|2023 is thin|main CPV code starts/)).toHaveCount(0);
  await expect(page.getByText(/with any CPV code starting with one of them/)).toBeVisible();
});

test("the supplier's country and the buyer's country are two filters, each labelled", async ({ page }) => {
  await visit(page, '/suppliers?buyerCountry=France', SUPPLIERS);
  const search = page.getByRole('search', { name: 'Find suppliers' });
  await expect(search.getByLabel(/^Supplier's country/)).toHaveValue('');
  await expect(search.getByLabel(/^Buyer's country/)).toHaveValue('France');
  await expect(page.locator('#results-heading')).toHaveText(/^Suppliers \(\d+\)$/);
  await expect(page.getByText(/The buyer's country is the country of the buyer that awarded the contract/)).toBeVisible();
  await visit(page, '/suppliers?buyerCountry=Atlantis', SUPPLIERS);
  await expect(page.getByText('Not a country', { exact: true })).toBeVisible();
});

test('a supplier page counts contracts over the last three years', async ({ page }) => {
  await visit(page, '/suppliers/1-demo-airframes-gmbh', { title: /Demo Airframes/i, h1: 'Demo Airframes GmbH' });
  await expect(page.getByText('Contracts won, last three years')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Contracts per year' })).toBeVisible();
  await expect(page.getByText(/the same contracts the supplier report counts in “who to approach”/)).toBeVisible();
  await expect(page.getByText(/from 2023/)).toHaveCount(0);
});
