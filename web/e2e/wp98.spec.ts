import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-98 (persona round of 23 October 2026, section C, items 1 to 4), on the demo build (lib/mock): a Portuguese textile maker searches
 * "fardamento", a German machinist "Ersatzteile", a Dutch logistics firm "brandstof"; the words of other languages find the notices, the
 * list says what else it searched, and a search with nothing found offers the product codes of its group.
 */

const TENDERS = { title: /tenders/i, h1: 'Tenders' } as const;

test('a word in another language finds the notices and the list says what else it searched', async ({ page }) => {
  await visit(page, '/tenders?q=fardamento&status=all', TENDERS);
  await expect(page.getByRole('link', { name: 'Uniform textiles framework', exact: true })).toBeVisible();
  await expect(page.locator('[data-also-searched]').first()).toContainText('Also searched, the same product in other languages:');
  await expect(page.locator('[data-also-searched]').first()).toContainText('uniform');
});

test('every word, in any order', async ({ page }) => {
  await visit(page, '/tenders?q=parts%20spare&status=all', TENDERS);
  await expect(page.getByRole('link', { name: /^Prior information: vehicle spare parts framework/ })).toBeVisible();
});

test('nothing found: the product codes of the group the words belong to', async ({ page }) => {
  await visit(page, '/tenders?q=Drohnen', TENDERS);
  const hint = page.locator('[data-search-suggestion]');
  await expect(hint.getByRole('link')).toHaveAttribute('href', '/tenders?cpv=35613');
  await expect(hint).toContainText('Drones and unmanned systems (CPV 35613)');
});

test('the global search reads the same words', async ({ page }) => {
  await visit(page, '/search?q=brandstof', { title: /Search/, h1: 'Search' });
  const tenders = page.locator('[aria-labelledby="group-tenders"]');
  await expect(tenders.locator('[data-also-searched]')).toContainText('fuel');
});
