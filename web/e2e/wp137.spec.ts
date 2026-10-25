import { expect, test } from '@playwright/test';

/**
 * WP-137, on the demo build (lib/mock): a call whose own conditions limit who may take part (here the China control restriction of a
 * Cluster 3 topic) shows that limit, in the call's own words, at the top of "Who can apply"; a call without one shows none.
 */

test('the call’s own limit on who may take part is shown with the answer', async ({ page }) => {
  expect((await page.goto('/funding/9-horizon-2026-interoperable-border-data-tools'))?.status()).toBe(200);
  const limits = page.locator('[data-who-limits]');
  await expect(limits).toBeVisible();
  await expect(limits).toContainText('limit who may take part');
  await expect(limits).toContainText('Control from elsewhere');
  await expect(limits).toContainText('controlled by China or by a legal entity established in China');
  expect((await page.goto('/funding/8-horizon-2026-advanced-lightweight-materials'))?.status()).toBe(200);
  await expect(page.locator('[data-who-limits]')).toHaveCount(0);
});
