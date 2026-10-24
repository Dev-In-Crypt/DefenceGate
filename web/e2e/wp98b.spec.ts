import { mkdirSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-98b (persona round of 23 October 2026, section C items 5 to 7), on the demo build (lib/mock, NEXT_PUBLIC_DG_NOW 12 October 2026).
 * The product groups of /tenders in two rows (goods, services) with the widened uniforms and ammunition groups; the deadline presets in
 * sight; on a phone Apply folds the filters and brings the results up, the filters as chips; /buyers?cpv= ordered by the tenders under
 * the codes, with that count; the supplier list's contract values, value order and TED view; a coverage line per chosen country on
 * /tenders, /buyers, /suppliers and /market. Screenshots go to WP98B_SHOTS when it is set (the self-check).
 */

const SHOTS = process.env.WP98B_SHOTS;
const TENDERS = { title: /tenders/i, h1: 'Tenders' } as const;

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: `${SHOTS}/${name}-${page.viewportSize()!.width}.png`, fullPage: false });
}

async function openFilters(page: Page) {
  const button = page.getByRole('button', { name: /^(Show|Hide) filters/ });
  if (await button.isVisible() && (await button.getAttribute('aria-expanded')) !== 'true') await button.click();
}

test('product groups for goods and services, and the deadline presets in sight', async ({ page }) => {
  await visit(page, '/tenders', TENDERS);
  await openFilters(page);
  const presets = page.locator('[data-cpv-presets]');
  await expect(presets.locator('[data-preset-group="goods"] a')).toHaveText([
    'Military electronics', 'Radar and sonar', 'Communications', 'Vehicles and parts', 'Ammunition, weapons, explosives and pyrotechnics',
    'Uniforms, footwear and protective gear', 'Machined parts and spare parts', 'Ships and naval', 'Aircraft and aviation']);   // WP-105
  await expect(presets.locator('[data-preset-group="services"] a')).toHaveText([
    'Transport and logistics', 'Fuel', 'Facility management and cleaning', 'Catering', 'Vehicle repair and maintenance', 'Training', 'IT services']);
  await expect(presets.getByRole('link', { name: 'Uniforms, footwear and protective gear' }))
    .toHaveAttribute('href', `/tenders?cpv=${encodeURIComponent('3581,181,182,183,188,351134,395')}`);
  await expect(presets.getByRole('link', { name: /^Ammunition/ })).toHaveAttribute('href', `/tenders?cpv=${encodeURIComponent('353,2461')}`);
  // the deadline presets are not inside the folded date range
  const seven = page.locator('[data-deadline-presets] a', { hasText: 'Next 7 days' });
  await expect(seven).toBeVisible();
  await expect(page.locator('details [data-deadline-presets]')).toHaveCount(0);
  await shot(page, 'tenders-presets');
  await presets.getByRole('link', { name: 'Transport and logistics' }).click();
  await expect(page).toHaveURL(/cpv=601%2C631%2C6352%2C637$/);
  await openFilters(page);
  await expect(page.locator('[data-cpv-presets] a[aria-current="true"]')).toHaveText('Transport and logistics');
});

test('on a phone, Apply folds the filters, brings the results up and shows the filters as chips', async ({ page }) => {
  test.skip(page.viewportSize()!.width >= 1024, 'the filter column is beside the results from lg');
  await visit(page, '/tenders', TENDERS);
  await openFilters(page);
  const form = page.getByRole('search', { name: 'Filter tenders' });
  await form.getByLabel('Search', { exact: true }).fill('vehicle');
  await form.getByRole('button', { name: 'Apply filters' }).click();
  await expect(page).toHaveURL(/q=vehicle/);
  await expect(page.getByRole('button', { name: /^Show filters/ })).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('#filter-panel')).toBeHidden();
  await expect(page.locator('#results-heading')).toBeInViewport();
  const chips = page.locator('[data-filter-chips] a');
  await expect(chips).toHaveText(['“vehicle” (remove this filter)']);
  await expect(chips.first()).toBeInViewport();
  await shot(page, 'tenders-chips');
  await chips.first().click();
  await expect(page).toHaveURL(/\/tenders$/);
  await expect(page.locator('[data-filter-chips]')).toHaveCount(0);
});

test('a chosen country says what we collect for it, also over an empty list', async ({ page }) => {
  await visit(page, '/tenders?country=PT', TENDERS);
  await expect(page.locator('[data-coverage-note]')).toHaveText('Portugal: TED only; the national portal is not collected. Sources we collect');
  await expect(page.getByText('No tenders match these filters')).toBeVisible();
  await shot(page, 'tenders-pt-coverage');
  await visit(page, '/tenders?country=ES,NL', TENDERS);
  await expect(page.locator('[data-coverage-note]')).toContainText('Spain: TED + PLACSP, awards too.');
  await expect(page.locator('[data-coverage-note]')).toContainText('Netherlands: TED + TenderNed (since January 2026)');
  await visit(page, '/tenders', TENDERS);
  await expect(page.locator('[data-coverage-note]')).toHaveCount(0);
  await visit(page, '/buyers?country=IT', { title: /buyers/i, h1: 'Buyers' });
  await expect(page.locator('[data-coverage-note]')).toContainText('Italy: TED only');
  await visit(page, '/market?country=IT', { title: /market/i, h1: 'Market overview' });
  await expect(page.locator('[data-coverage-note]')).toContainText('Italy: TED only; the national portal is not collected.');
  await visit(page, '/suppliers?buyerCountry=IT', { title: /supplier/i, h1: 'Companies' });
  await expect(page.locator('[data-coverage-note]')).toContainText('Italy: winners from TED only');
});

test('buyers under a code are ordered by their tenders under it, and say how many', async ({ page }) => {
  await visit(page, '/buyers?cpv=44,34,60', { title: /buyers/i, h1: 'Buyers' });
  const counts = await page.locator('[data-cpv-count]').allTextContents();
  expect(counts.length).toBeGreaterThan(1);
  expect(counts.map(Number)).toEqual([...counts.map(Number)].sort((a, b) => b - a));
  await expect(page.getByText(/except “Under these codes”: those under the codes/)).toBeVisible();
  await shot(page, 'buyers-cpv-order');
  await visit(page, '/buyers', { title: /buyers/i, h1: 'Buyers' });
  await expect(page.locator('[data-cpv-count]')).toHaveCount(0);
});

test('the supplier list gives contract values, orders by them in one currency, and has a TED view', async ({ page }) => {
  const SUPPLIERS = { title: /supplier/i, h1: 'Companies' } as const;
  await visit(page, '/suppliers', SUPPLIERS);
  const first = page.locator('main li', { hasText: 'Demo Airframes GmbH' });
  // WP-112 (p06, p07): the line accounts for the contracts it does not sum
  await expect(first.locator('[data-contract-values]')).toHaveText('Contract values: EUR 4,500,000 over 3 of 14 contracts; 11 more with a framework ceiling, an estimate or no value of their own (not added)');
  await expect(page.locator('main li', { hasText: 'Demo Logistics B.V.' }).locator('[data-contract-values]'))
    .toHaveText('Contract values: none stated for this company alone (a framework ceiling or an estimate is not added)');
  await visit(page, '/suppliers?sort=value-EUR', SUPPLIERS);
  await expect(page.locator('main li a[href^="/suppliers/"]').first()).toHaveText('Demo Ordnance SA');
  await expect(page.getByText(/Ignored filter/)).toHaveCount(0);
  await shot(page, 'suppliers-values');
  await visit(page, '/suppliers?sort=value-PLN', SUPPLIERS);
  await expect(page.locator('main li a[href^="/suppliers/"]').first()).toHaveText('Demo Protective Textiles sp. z o.o.');
  await visit(page, '/suppliers?source=ted', SUPPLIERS);
  await expect(page.locator('main li', { hasText: 'Demo Sensors S.L.' })).toHaveCount(0);
  await expect(page.locator('main li', { hasText: 'Demo Airframes GmbH' })).toHaveCount(1);
});
