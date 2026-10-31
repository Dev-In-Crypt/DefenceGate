import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-160 on the demo build (no plan on sale, signed out): the list of contracts ending soon, the contract period line of a notice and
 * the buyer page's block. Every row says where its end date comes from; an estimated end is listed only when asked for; a duration with
 * no start shows no end. The demo clock is pinned (NEXT_PUBLIC_DG_NOW=2026-10-12): the demo periods are relative to it
 * (lib/mock/tenders.ts `mockPeriods`). At 1440 and 375 px, light and dark; no horizontal scroll at 320 px.
 * With WP160_SHOTS=<dir> each state is saved as a screenshot there.
 */
const LIST = { title: /Contracts ending soon/, h1: 'Contracts ending soon' };

async function shot(page: Page, name: string, scheme: string) {
  const dir = process.env.WP160_SHOTS;
  if (!dir) return;
  await page.screenshot({ path: `${dir}/${name}-${page.viewportSize()?.width ?? 0}-${scheme}.png`, fullPage: true });
}

for (const scheme of ['light', 'dark'] as const) {
  test.describe(`${scheme} theme`, () => {
    test.use({ colorScheme: scheme });

    test('the list: soonest end first, each with its basis, estimates only when asked for', async ({ page }) => {
      for (const width of [1440, 375]) {
        await page.setViewportSize({ width, height: 900 });
        await visit(page, '/tenders/ending', LIST);
        const rows = page.locator('[data-ending-list] [data-ending-row]');
        await expect(rows).toHaveCount(2);
        await expect(rows.nth(0)).toContainText('Maintenance services for a vehicle fleet');
        await expect(rows.nth(0).locator('[data-contract-period]')).toHaveAttribute('data-end-basis', 'stated');
        await expect(rows.nth(0).locator('[data-basis]')).toHaveText('Stated end date');
        await expect(rows.nth(0).locator('[data-renewal]')).toHaveText('Renewal options: up to 2 renewals; not added to the end date');
        await expect(rows.nth(1).locator('[data-basis]')).toHaveText('Computed from start + duration');
        await expect(page.locator('[data-why]')).toContainText('the buyer usually tenders again');
        await expect(page.locator('[data-coverage]')).toContainText('Contract periods we can date come from notices of');
        await expect(page.getByText('Packaging and logistics')).toHaveCount(0);           // its end is an estimate
        await shot(page, 'list', scheme);
      }
      await visit(page, '/tenders/ending?estimated=true', LIST);
      const est = page.locator('[data-ending-row]').filter({ hasText: 'Packaging and logistics' });
      await expect(est.locator('[data-basis]')).toHaveText('Estimated: award notice publication date + duration');
      await expect(est.locator('[data-winners]')).toContainText('Demo Logistics B.V.');
      await shot(page, 'list-estimated', scheme);
      await visit(page, '/tenders/ending?within=3', LIST);
      await expect(page.locator('[data-ending-row]')).toHaveCount(1);
      await page.setViewportSize({ width: 320, height: 800 });
      await visit(page, '/tenders/ending', LIST);                                       // visit checks no horizontal scroll
    });

    test('a notice\'s contract period says where its end comes from', async ({ page }) => {
      for (const width of [1440, 375]) {
        await page.setViewportSize({ width, height: 900 });
        await visit(page, '/tenders/4-vehicle-fleet-maintenance-services', { title: /vehicle fleet/i, h1: 'Maintenance services for a vehicle fleet' });
        const cell = page.locator('[data-contract-period]');
        await expect(cell).toHaveAttribute('data-end-basis', 'stated');
        await expect(cell).toContainText('26 Nov 2026');
        await expect(page.getByRole('link', { name: 'Contracts ending soon' }).first()).toBeVisible();
        await shot(page, 'tender-stated', scheme);
      }
      await visit(page, '/tenders/5-uniform-textiles-framework', { title: /Uniform textiles/, h1: 'Uniform textiles' });
      await expect(page.locator('[data-contract-period]')).toHaveAttribute('data-end-basis', 'none');
      await expect(page.locator('[data-contract-period] [data-basis]')).toHaveText('Duration only, no start: no end date');
      await shot(page, 'tender-duration-only', scheme);
      await visit(page, '/tenders/2-workshop-consumables-supply', { title: /workshop consumables/i, h1: 'Supply of workshop consumables' });
      await expect(page.locator('[data-contract-period]')).toHaveCount(0);                // states no period: no line
    });

    test('the buyer page lists its contracts ending in the next 12 months, free', async ({ page }) => {
      for (const width of [1440, 375]) {
        await page.setViewportSize({ width, height: 900 });
        await visit(page, '/buyers/3-demo-logistics-and-support-command', { title: /Demo Logistics and Support Command/, h1: 'Demo Logistics and Support Command' });
        const block = page.locator('[data-buyer-ending]');
        await expect(block.locator('h2')).toHaveText('Contracts ending in the next 12 months');
        await expect(block.locator('[data-ending-row]')).toHaveCount(1);
        await expect(block.getByRole('link', { name: 'All contracts of this buyer ending soon' })).toHaveAttribute('href', '/tenders/ending?buyer=3');
        await shot(page, 'buyer-block', scheme);
      }
    });
  });
}

test('the tenders list links the contracts ending soon', async ({ page }) => {
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.locator('[data-ending-link]')).toHaveAttribute('href', '/tenders/ending');
});
