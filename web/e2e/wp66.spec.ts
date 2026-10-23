import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-66: "Who buys what you make" in the supplier report and its short version on the results page. What this proves: the browser sends
 * the CPV codes of the supplier page and the five countries, and nothing else of the profile; the report shows the map per country (counts,
 * buyers, named winners only above the mosaic threshold, the rest as a count, links to the notices) with the coverage line, and prints
 * with a page of its own; the results page shows one row per country and the way to the report; a profile without codes asks nothing; a
 * failure is said and the rest of the report stands. The answer is the demo build's (lib/mock/demand.json: the API's answer on production
 * data of 22 October 2026 for these codes).
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
const DEMO = JSON.parse(readFileSync(path.join(__dirname, '..', 'lib', 'mock', 'demand.json'), 'utf8'));
const COUNTRIES = ['ES', 'DE', 'FR', 'PL', 'NL'];

async function asSupplier(page: Page, profile: unknown): Promise<unknown[]> {
  const sent: unknown[] = [];
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, profile);
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('assess-es-sup-civil.json')) }));
  page.on('request', (r) => { if (r.url().endsWith('/api/readiness/demand')) sent.push(r.postDataJSON()); });
  return sent;
}

test('the report maps who buys the codes, per country, from the codes alone', async ({ page }) => {
  const profile = fixture('profile-es-sup-civil.json');
  const sent = await asSupplier(page, profile);
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  const map = page.locator('[data-report-section="r-demand"]');
  await expect(map.getByRole('heading', { name: 'Who buys what you make' })).toBeVisible();
  await expect(map.locator('[data-demand-country]')).toHaveCount(5);
  expect(sent).toEqual([{ cpv: profile.supplier.cpv, countries: COUNTRIES }]);

  const es = DEMO.byCountry[0];
  const spain = map.locator('[data-demand-country="ES"]');
  await expect(spain.getByRole('heading', { name: 'Spain' })).toBeVisible();
  await expect(spain.locator('[data-demand-summary]')).toContainText(`${es.procurements} procurements by ${es.coreBuyers} core defence buyers and ${es.otherBuyers} other defence-scope buyers`);
  await expect(spain.locator('[data-demand-buyer]')).toHaveCount(es.topBuyers.length);
  await expect(spain.locator('[data-demand-buyer]').first().getByRole('link')).toHaveAttribute('href', `/buyers/${es.topBuyers[0].slug}`);
  // named winners only with at least kMin awards; every other winner as a count
  const named = DEMO.byCountry.flatMap((c: { topWinners: { awards: number }[] }) => c.topWinners);
  expect(named.length).toBeGreaterThan(0);
  expect(named.every((w: { awards: number }) => w.awards >= DEMO.kMin)).toBe(true);
  await expect(map.locator('[data-demand-winner]')).toHaveCount(named.length);
  await expect(spain.locator('[data-demand-others]')).toContainText(`${es.otherWinners.winners} other winners (${es.otherWinners.awards} awards) not named`);
  await expect(spain.locator('[data-demand-notice]').first().getByRole('link').first()).toHaveAttribute('href', /^\/tenders\//);
  await expect(map.locator('[data-demand-coverage]')).toHaveText(DEMO.coverage);
  await expect(map.locator('[data-demand-coverage]')).toContainText('not the sub-tier needs of prime contractors');
  await expect(page.locator('[data-report-section="r-about"]')).toContainText('with your CPV codes and nothing else');

  // print: the map starts a page, and an address at the source is printed after its link
  await page.emulateMedia({ media: 'print' });
  expect(await map.evaluate((e) => getComputedStyle(e).breakBefore)).toBe('page');
  const after = await map.locator('a[href^="http"]').first().evaluate((a) => getComputedStyle(a, '::after').content);
  expect(after).toMatch(/\(https?:\/\//);
  // WP-89: a notice's own "At the source" link is not printed (its number is); the printed report was 59 pages, these addresses a good part
  await expect(map.locator('[data-demand-notice] a[href^="http"]').first()).toBeHidden();
});

test('the results page shows one row per country and the way to the report', async ({ page }) => {
  await asSupplier(page, fixture('profile-es-sup-civil.json'));
  await visit(page, '/readiness/results', { title: /readiness results/i, h1: 'Your readiness results' });
  const section = page.locator('[data-demand-summary-section]');
  await expect(section.getByRole('heading', { name: 'Who buys what you make' })).toBeVisible();
  await expect(section.locator('[data-demand-row]')).toHaveCount(5);
  const es = DEMO.byCountry[0];
  await expect(section.locator('[data-demand-row="ES"]')).toContainText(`${es.coreBuyers} / ${es.otherBuyers}`);
  await expect(section.locator('[data-demand-coverage]')).toHaveText(DEMO.coverage);
  await section.getByRole('link', { name: 'Buyers and notices in your supplier report' }).click();
  await expect(page).toHaveURL(/\/readiness\/supplier\/report#r-demand$/);
});

test('a profile without CPV codes asks nothing and shows no map', async ({ page }) => {
  const profile = fixture('profile-es-sup-civil.json');
  const sent = await asSupplier(page, { ...profile, supplier: { ...profile.supplier, cpv: [] } });
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  await expect(page.locator('[data-report-section="r-roadmap"]')).toBeVisible();
  await expect(page.locator('[data-report-section="r-demand"]')).toHaveCount(0);
  await visit(page, '/readiness/results', { title: /readiness results/i, h1: 'Your readiness results' });
  await expect(page.getByRole('heading', { name: 'Where you stand, programme by programme' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Who buys what you make' })).toHaveCount(0);
  expect(sent).toEqual([]);
});

test('a demand map that fails is said, and the rest of the report stands', async ({ page }) => {
  await asSupplier(page, fixture('profile-es-sup-civil.json'));
  await page.route('**/api/readiness/demand', (route) => route.fulfill({ status: 502, contentType: 'application/json', body: '{"detail":"x"}' }));
  await page.goto('/readiness/supplier/report');
  const map = page.locator('[data-report-section="r-demand"]');
  await expect(map.getByText('The demand map could not be computed').first()).toBeVisible();
  await expect(map.getByRole('button', { name: 'Try again' })).toBeVisible();
  await expect(page.locator('[data-report-section="r-roadmap"] [data-item]').first()).toBeVisible();
});
