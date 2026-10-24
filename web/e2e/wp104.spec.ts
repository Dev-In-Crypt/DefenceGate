import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-104 (persona round of 24 October 2026, entities): a curated company group's view shows the group's total of contract values,
 * per currency and never converted, under the note that the companies stay separate. Mock build (lib/mock).
 */

test('a company group shows its total of contract values per currency', async ({ page }) => {
  await visit(page, '/suppliers?group=demo', { title: /supplier map/i, h1: 'Companies' });
  await expect(page.locator('[data-group-view]')).toContainText('nothing is merged across them');
  const total = page.locator('[data-group-total]');
  await expect(total).toContainText('Group total of contract values: EUR 17,050,000 over 7 contracts; PLN 7,000,000 over 2 contracts');
  await expect(total).toContainText('never converted');
  await visit(page, '/suppliers', { title: /supplier map/i, h1: 'Companies' });
  await expect(page.locator('[data-group-total]')).toHaveCount(0);
});
