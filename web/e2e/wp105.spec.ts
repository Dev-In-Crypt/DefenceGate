import { mkdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-105 (persona round of 24 October 2026): the supplier report (the results page's answers reused, so the report after the results page
 * asks the API nothing; the company's own country sent; the primes that win other contracts from the same buyers; the Spanish portal's
 * credit under Spain only; the national export authority of the Netherlands and Italy, "Not covered yet" for Portugal), the profile's
 * code buttons (textiles, naval, aviation), the buyer page (top suppliers first, with contract values, under its CPV filter; the planned
 * tenders folded) and the market's contract values. The demo demand answer (lib/mock/demand.json) and the WP-97 assess fixtures.
 * Screenshots go to WP105_SHOTS when it is set (the self-check).
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
const DEMO = JSON.parse(readFileSync(path.join(__dirname, '..', 'lib', 'mock', 'demand.json'), 'utf8'));
const SHOTS = process.env.WP105_SHOTS;

const base = (country: string, cpv: string[]) => ({
  version: 4, step: 1, updatedAt: '2026-10-24T15:05:57.221Z', name: '', sizeClass: 'medium', country, legalForm: '', applicantKind: '', offering: '',
  topics: '', orgKind: 'company', headcount: '50_249', inGroup: 'no', groupHeadcount: '', management: '', managementCountry: '', control: 'no',
  controlCountry: '', investor: '', uaOccupied: '', uaPartner: '', seapPartner: '', regime: '', componentPct: '', componentBand: '', restricted: '',
  uaEeaComponents: '', safeRole: '', statuses: { 'REQ-ISO9001': 'held' }, classified: 'no', exportIntent: 'within_eu',
  supplier: { region: '', foreignOwner: 'no', foreignCountry: '', nace: '', cpv, processes: ['machining'], held: [], expiry: {}, usComponents: 'no', answers: {}, euFunding: 'no' },
});
const MACHINING = ['35421000', '35521000', '35641000', '34320000', '34330000', '34913000', '35340000', '44530000'];

interface Calls { assess: number; demand: number; bodies: Record<string, unknown>[] }

/** The stored profile; the assess and demand calls answered from fixtures and counted. */
async function as(page: Page, profile: object, assess: string): Promise<Calls> {
  const calls: Calls = { assess: 0, demand: 0, bodies: [] };
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, profile);
  await page.route('**/api/readiness/assess', async (route) => {
    calls.assess += 1;
    const body = route.request().postDataJSON() as { programmes?: string[] };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture(`assess-${assess}${body.programmes ? '-routes' : ''}.json`)) });
  });
  await page.route('**/api/readiness/demand', async (route) => {
    calls.demand += 1;
    calls.bodies.push(route.request().postDataJSON() as Record<string, unknown>);
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DEMO) });
  });
  return calls;
}

const shot = async (page: Page, name: string) => {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
};

test('the report right after the results page asks the API nothing again (p02: "Too many requests" in all three sections)', async ({ page }) => {
  const calls = await as(page, base('DE', MACHINING), 'de-mach97');
  await visit(page, '/readiness/results?from=supplier', { title: /Your supplier report/, h1: 'Your supplier report' });
  await expect(page.locator('[data-approach-summary-section]')).toBeVisible();
  await expect.poll(() => calls.demand).toBe(1);
  const asked = { assess: calls.assess, demand: calls.demand };
  // the company's own country goes with the codes, so its own winners are named past the first 30 (p03)
  expect(calls.bodies[0]).toEqual({ cpv: MACHINING, countries: ['ES', 'DE', 'FR', 'PL', 'NL', 'PT', 'IT'], home: 'DE' });
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  await expect(page.locator('[data-approach]')).toBeVisible();
  await expect(page.locator('[data-report-section="r-roadmap"]')).toBeVisible();
  await expect(page.getByText('Too many requests')).toHaveCount(0);
  // the demand map of the results page is reused; the report asks only its own readiness question (the supply routes)
  expect(calls.demand, 'the demand map is not asked again').toBe(asked.demand);
  expect(calls.assess).toBeLessThanOrEqual(asked.assess + 1);
  const again = calls.assess;
  await page.reload();
  await expect(page.locator('[data-report-section="r-roadmap"]')).toBeVisible();
  expect({ assess: calls.assess, demand: calls.demand }, 'a second look at the report asks nothing').toEqual({ assess: again, demand: asked.demand });
});

test('a "Too many requests" with a short Retry-After is waited out, not shown', async ({ page }) => {
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, base('ES', MACHINING));
  let n = 0;
  await page.route('**/api/readiness/assess', async (route) => {
    const body = route.request().postDataJSON() as { programmes?: string[] };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture(`assess-de-mach97${body.programmes ? '-routes' : ''}.json`)) });
  });
  await page.route('**/api/readiness/demand', async (route) => {
    n += 1;
    if (n === 1) await route.fulfill({ status: 429, headers: { 'retry-after': '1' }, contentType: 'application/json', body: '{"detail":"rate limit exceeded"}' });
    else await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DEMO) });
  });
  // not `visit`: the browser logs the refused first request on the console, which `visit` counts as a page error
  await page.goto('/readiness/supplier/report');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Supplier readiness report');
  await expect(page.locator('[data-approach]')).toBeVisible({ timeout: 15_000 });
  expect(n).toBe(2);
  await expect(page.getByText('Too many requests')).toHaveCount(0);
});

test('the report: primes that win from the same buyers, the PLACSP credit under Spain only, the export authority of the own country', async ({ page }) => {
  await as(page, base('NL', MACHINING), 'de-mach97');
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  const at = page.locator('[data-approach-primes-at-buyers]');
  await expect(at.getByRole('heading', { name: 'Primes that win other contracts from the same buyers' })).toBeVisible();
  await expect(at.locator('[data-prime-at-buyers="Indra"]')).toContainText('147 contracts from these buyers under other codes');
  await expect(at.locator('[data-prime-at-buyers="Indra"] a').first()).toHaveAttribute('href', '/suppliers/406963-indra-sistemas-sa');
  // p06: "Origen de los datos" under Spain's figures, not under the map of every country
  await expect(page.locator('[data-demand-country="ES"] [data-country-attribution]')).toContainText('Origen de los datos');
  await expect(page.locator('[data-country-attribution]')).toHaveCount(1);
  await expect(page.locator('[data-demand] > [data-attribution]')).not.toContainText('Origen de los datos');
  // p06: the Dutch export authority from the official page, and no Spanish or German one named to a Dutch company
  const route = page.locator('[data-country-route="NL"]');
  await expect(route.locator('[data-route-line="nl-export"]')).toContainText('Central Import and Export Service (CDIU) of Dutch Customs');
  await expect(route.locator('[data-route-line="nl-export"] a')).toHaveAttribute('href', /^https:\/\/www\.rijksoverheid\.nl\//);
  await expect(route).not.toContainText('BAFA');
  await shot(page, 'report-nl');
});

test('a Portuguese company: Portugal in the map request, its route says what is not covered (p02, p07)', async ({ page }) => {
  const calls = await as(page, base('PT', ['35810000', '18100000']), 'de-mach97');
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  await expect(page.locator('[data-approach]')).toBeVisible();
  expect(calls.bodies[0]).toMatchObject({ home: 'PT', countries: ['ES', 'DE', 'FR', 'PL', 'NL', 'PT', 'IT'] });
  const route = page.locator('[data-country-route="PT"]');
  await expect(route.locator('[data-route-line="export"]')).toContainText('Not covered yet for Portugal: which authority licenses exports');
  await expect(route).not.toContainText(/BAFA|CDIU|UAMA|Secretaría/);
});

test('the supplier profile offers textiles, naval and aviation codes, and the machining codes of the tender list', async ({ page }) => {
  await as(page, base('IT', []), 'de-mach97');
  await visit(page, '/readiness/supplier', { title: /supplier/i, h1: /.+/ });
  for (const [key, label] of [['uniforms', 'Uniforms, textiles and protective gear'], ['naval', 'Ships and naval'], ['aviation', 'Aircraft and aviation'], ['machining', 'Machined parts and spare parts']]) {
    await expect(page.locator(`[data-cpv-set="${key}"]`).getByRole('button', { name: `${label}: suggested codes` })).toBeVisible();
  }
  await page.getByRole('button', { name: 'Ships and naval: suggested codes' }).click();
  await expect(page.getByRole('list', { name: 'Your CPV codes' }).locator('li')).toHaveCount(4);
  await visit(page, '/tenders', { title: /tenders/i, h1: /.+/ });
  const filters = page.getByRole('button', { name: /^(Show|Hide) filters/ });
  if (await filters.isVisible() && (await filters.getAttribute('aria-expanded')) !== 'true') await filters.click();
  // WP-121: the eighth goods group is folded under "Show all" (the column was ~3,500 px); it is still the same link
  await expect(page.locator('[data-cpv-presets]').getByRole('link', { name: 'Ships and naval', includeHidden: true })).toHaveAttribute('href', `/tenders?cpv=${encodeURIComponent('345,355,5064,50241')}`);
});

test('a buyer page: top suppliers first, with contract values and their sum, under the CPV filter (p01, p03, p06)', async ({ page }) => {
  await visit(page, '/buyers/1-demo-armaments-agency', { title: /Demo Armaments Agency/i, h1: 'Demo Armaments Agency' });
  const top = page.locator('[data-top-suppliers]');
  const before = await top.boundingBox();
  const open = await page.locator('#open-tenders').boundingBox();
  expect(before!.y, 'top suppliers before the open tenders').toBeLessThan(open!.y);
  await expect(top.locator('[data-top-suppliers-total]')).toContainText(/Contract values awarded: EUR [\d,]+ over \d+ contracts/);
  await expect(top.locator('[data-top-supplier-value]').first()).toContainText(/EUR [\d,]+ over \d+ contract/);
  await expect(top.locator('[data-top-suppliers-summary]')).toContainText(/contracts? of Demo Armaments Agency .+ names? \d+ compan/);
  await shot(page, 'buyer-top-suppliers');
  await visit(page, '/buyers/1-demo-armaments-agency?cpv=18', { title: /Demo Armaments Agency/i, h1: 'Demo Armaments Agency' });
  await expect(page.locator('[data-top-suppliers]').getByRole('heading')).toHaveText('Top suppliers of this buyer under 18');
  await expect(page.locator('[data-top-suppliers] tbody tr')).toHaveCount(1);
  await expect(page.locator('[data-top-suppliers] tbody tr')).toContainText('Demo Protective Textiles');
});

test('the market overview sums contract values by country, CPV group and buyer (p07)', async ({ page }) => {
  await visit(page, '/market', { title: /market overview/i, h1: 'Market overview' });
  const money = page.locator('[data-market-money]');
  await expect(money.locator('[data-market-money-total]')).toContainText(/EUR [\d,]+ over [\d,]+ contracts/);
  await expect(money.locator('[data-money-country]')).toHaveCount(3);
  await expect(money.locator('[data-money-country="PL"]')).toContainText('PLN 96,000,000 over 120 contracts');
  await expect(money.locator('[data-money-group="354"]')).toContainText('EUR 60,000,000 over 200 contracts');
  await expect(money.locator('[data-money-buyer] a').first()).toHaveAttribute('href', '/buyers/1-demo-armaments-agency');
  await expect(money.locator('[data-money-basis]')).toContainText('Framework ceilings, estimates and unit prices are never added');
  await expect(page.getByText('never of money')).toHaveCount(0);
  await shot(page, 'market-money');
});
