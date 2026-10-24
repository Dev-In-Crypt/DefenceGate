import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-108 (persona round 4, 24 October 2026, p10): DefenceGate's corrections of a notice are said in the open under its version
 * history, with their date and the fields before and after: "2 corrections (below)" stood over a closed fold. Mock build (lib/mock).
 */

test('a tender page lists its corrections open, each with its date, fields, before and after', async ({ page }) => {
  await visit(page, '/tenders/11-fuel-supply-framework', { title: /fuel supply/i, h1: /fuel supply/i });
  await expect(page.locator('[data-version-count]')).toContainText('corrections by DefenceGate (below)');
  const lines = page.locator('[data-correction-lines] li');
  await expect(lines).toHaveCount(2);
  await expect(lines.first()).toBeVisible();
  await expect(lines.first()).toHaveText(/^Corrected \d{1,2} [A-Z][a-z]{2} 20\d\d: .+ to .+/);
  // the fold keeps the full entries, closed, under the lines
  const fold = page.locator('[data-corrections] details');
  expect(await fold.evaluate((d) => (d as HTMLDetailsElement).open)).toBe(false);
});
