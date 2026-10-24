import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-113 (coverage audit of 24 October 2026): a national notice whose value is taken from its TED twin says so beside the
 * figure (TenderNed shows the TED estimate). Mock build (lib/mock).
 */

test('a value taken from the TED twin says where it is from', async ({ page }) => {
  await visit(page, '/tenders/3-dostawa-materialow-eksploatacyjnych-warsztatow', { title: /./, h1: /./ });
  await expect(page.locator('[data-value-from-twin]')).toHaveText('Not stated in this notice; as given in the TED notice of the same procurement');
});

test('a TED notice whose value is its own carries no such line', async ({ page }) => {
  await visit(page, '/tenders/5-uniform-textiles-framework', { title: /./, h1: /./ });
  await expect(page.locator('[data-value-from-twin]')).toHaveCount(0);
});
