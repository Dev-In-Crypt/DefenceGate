import { expect, test } from '@playwright/test';
import { pace, visit } from './helpers';

/**
 * WP-152 on the demo build (lib/mock/suppliers.ts supplierCompetition): a supplier page shows its competitors, where it wins and its
 * share, each competitor linked to its own page, a second record under the same name marked; the paid company report is off by default
 * (DGATE_COMPANY_REPORT_OPEN): no link, and its address is a 404. The report itself: e2e/wp152-api.spec.ts against the fake API.
 */
const SLUG = '1-demo-airframes-gmbh';
const PAGE = { title: /Demo Airframes/i, h1: 'Demo Airframes GmbH' } as const;

test('a supplier page: competitors, where it wins and its share, with the totals', async ({ page }) => {
  await visit(page, `/suppliers/${SLUG}`, PAGE);
  const competitors = page.locator('section[aria-labelledby="competitors"]');
  await expect(competitors.getByRole('heading', { name: 'Competitors' })).toBeVisible();
  await expect(competitors.locator('[data-competitor]')).toHaveCount(4);
  await expect(competitors.getByRole('link', { name: 'Demo Ordnance SA' })).toHaveAttribute('href', '/suppliers/2-demo-ordnance-sa');
  await expect(competitors.locator('[data-same-name]')).toHaveCount(1);
  await expect(competitors.locator('[data-same-group]')).toHaveText('Same group: Demo');
  await expect(page.getByRole('heading', { name: 'Where it wins' })).toBeVisible();
  await expect(page.locator('[data-typical-size]')).toContainText('Median EUR 1,500,000, over the 3 contracts with a value in EUR');
  await expect(page.locator('section[aria-labelledby="by-cpv-class"]')).toContainText('3541 Armoured military vehicles');
  const share = page.locator('section[aria-labelledby="share"]');
  await expect(share.locator('[data-share]').first()).toContainText(/of 240 \(\d/);
  await expect(share.locator('[data-share]').last()).toContainText('No value stated');
  // the supplier map's own words stay out: no ranking label, no "market share", no sole source
  await expect(page.getByText(/market share|top supplier|single point of failure|sole source/i)).toHaveCount(0);
  // the report is off by default
  await expect(page.locator('[data-company-report-link]')).toHaveCount(0);
});

test('the company report does not exist while its switch is off', async ({ page }) => {
  const r = await page.goto(`/suppliers/${SLUG}/report`);
  expect(r!.status()).toBe(404);
  await pace(page);
});

test('a competitor row is a row of a table: its name underlines on its own hover only', async ({ page }) => {
  await visit(page, `/suppliers/${SLUG}`, PAGE);
  const link = page.locator('section[aria-labelledby="competitors"] [data-competitor] a').first();
  await page.mouse.move(0, 0);
  expect(await link.evaluate((e) => getComputedStyle(e).textDecorationLine)).toBe('none');
  await link.hover();
  await expect.poll(() => link.evaluate((e) => getComputedStyle(e).textDecorationLine)).toContain('underline');
  // the other cells of the row are not links and never underline
  const cell = page.locator('section[aria-labelledby="competitors"] [data-competitor] td').first();
  expect(await cell.evaluate((e) => getComputedStyle(e).textDecorationLine)).toBe('none');
});

test('no horizontal scroll at 320 px, in both themes', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  for (const theme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: theme });
    await visit(page, `/suppliers/${SLUG}`, PAGE);
  }
});
