import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-80: the supplier report and the supplier results lead with "who to approach". What this proves: the report's first section lists the
 * winners of the demo answer (lib/mock/demand.json, production's answer of 22 October 2026 for the vehicle-parts codes), the primes first and
 * marked with their source, every named winner with at least kMin contracts and the rest as a count, links to the supplier pages that exist;
 * then the demand map, then the rules as appendices, the roadmap steps carrying the free guide and the regional grants (the company's region
 * first, "check the current call"); the results page shows the short list first; still exactly one demand request per page; the entry page
 * and the supplier page say the new order.
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
const DEMO = JSON.parse(readFileSync(path.join(__dirname, '..', 'lib', 'mock', 'demand.json'), 'utf8'));
type W = { name: string; country: string | null; contracts: number; slug: string | null; prime: { group: string } | null; distributor?: boolean };
const WINNERS: W[] = DEMO.approach.winners;
// WP-89: the primes of the company's own country (Spain, the fixture profiles) first, then the others, each most contracts first
const PRIMES = [...WINNERS.filter((w) => w.prime && w.country === 'ES'), ...WINNERS.filter((w) => w.prime && w.country !== 'ES')];
// WP-97: the dealers of parts and tyres (Ferretería, Recambios ...) are listed apart, not among the direct suppliers
const HOME = WINNERS.filter((w) => !w.prime && !w.distributor && w.country === 'ES');

/** `visit` measures before the demand answer arrives: measured again once the lists are on the page. */
async function noSideScroll(page: Page) {
  const o = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  expect(o.scroll, `horizontal scroll (${o.scroll} px in ${o.client} px)`).toBeLessThanOrEqual(o.client);
}

async function asSupplier(page: Page, profile: unknown): Promise<unknown[]> {
  const sent: unknown[] = [];
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, profile);
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('assess-es-sup-civil.json')) }));
  page.on('request', (r) => { if (r.url().endsWith('/api/readiness/demand')) sent.push(r.postDataJSON()); });
  return sent;
}

test('the report starts with who to approach, then who buys, then the rules as appendices', async ({ page }) => {
  const profile = fixture('profile-es-sup-civil.json');
  const sent = await asSupplier(page, { ...profile, supplier: { ...profile.supplier, region: 'ES-GA' } });
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  await expect(page.locator('[data-item]').first()).toBeVisible();
  const order = await page.locator('[data-report-section]').evaluateAll((els) => els.map((e) => e.getAttribute('data-report-section')));
  expect(order).toEqual(['r-open', 'r-approach', 'r-demand', 'r-results', 'r-roadmap', 'r-profile', 'r-about']);   // WP-97: open now first
  expect(sent).toHaveLength(1);                                   // one request feeds both sections
  await expect(page.locator('[data-approach-winner]').first()).toBeVisible();
  await noSideScroll(page);

  const s = page.locator('[data-report-section="r-approach"]');
  await expect(s.getByRole('heading', { name: 'Who to approach', level: 2 })).toBeVisible();
  await expect(s.locator('[data-approach-explainer]')).toContainText('usually enter defence as subcontractors');
  await expect(s.locator('[data-approach-explainer]')).toContainText('Public notices miss most of that work');
  await expect(s.locator('[data-approach-summary]')).toContainText(`${DEMO.total.winners} companies won defence-scope procurements under your codes`);
  // the primes first, each marked with its group and the source of the list; then every other named winner, once
  const primes = s.locator('[data-approach-primes] [data-approach-winner]');
  await expect(primes).toHaveCount(PRIMES.length);
  for (const [i, w] of PRIMES.entries()) {
    await expect(primes.nth(i)).toContainText(w.name);
    await expect(primes.nth(i)).toContainText(`Prime or large defence group: ${w.prime!.group}`);
    await expect(primes.nth(i).getByRole('link', { name: /SIPRI|elDiario/ })).toHaveAttribute('href', /^https:\/\//);
  }
  await expect(s.locator('[data-approach-winner]')).toHaveCount(WINNERS.length);
  // WP-89: the direct suppliers of the company's own country lead the section, before the primes
  await expect(s.locator('[data-approach-home] h3')).toHaveText('Direct suppliers in Spain');
  await expect(s.locator('[data-approach-home] [data-approach-winner]')).toHaveCount(HOME.length);
  await expect(s.locator('[data-approach-winner]').first()).toContainText(HOME[0].name);
  expect(WINNERS.every((w) => w.contracts >= DEMO.kMin)).toBe(true);
  await expect(s.locator('[data-approach-others]')).toContainText(`${DEMO.approach.below.winners} other winners with fewer than ${DEMO.kMin} awards each`);
  // a supplier page is linked where one exists, and only then
  const linked = WINNERS.find((w) => w.slug)!;
  // WP-89: with the profile's codes and the report's countries, so that the page says how many of its contracts are under them
  await expect(s.getByRole('link', { name: linked.name, exact: true }).first()).toHaveAttribute('href', new RegExp(`^/suppliers/${linked.slug}\\?cpv=`));
  const plain = WINNERS.find((w) => !w.slug)!;
  await expect(s.getByRole('link', { name: plain.name, exact: true })).toHaveCount(0);
  await expect(s.locator('[data-approach-facts]').first()).toContainText(/contracts? won in .+; latest notice published/);

  // the roadmap: the RID step with its free guide and the grants, Galicia (the company's region) first
  const rid = page.locator('[data-item="REQ-RID"]');
  await expect(rid.locator('[data-item-guide]').getByRole('link', { name: /Guide to registration in the RID/ })).toHaveAttribute('href', /1_Guia_CAETRA_RegistroDGAM\.pdf$/);
  const grants = rid.locator('[data-item-grants] li');
  await expect(grants.first()).toHaveAttribute('data-grant-region', 'ES-GA');
  await expect(grants.first()).toContainText('Galicia (your region)');
  await expect(rid.locator('[data-item-grants]')).toContainText('Check the current call');
  await expect(page.locator('[data-report-support]')).toContainText('ACCIÓ');
  // a step no research line covers carries neither
  await expect(page.locator('[data-item="REQ-NCAGE"] [data-item-support]')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Appendix B: supplier roadmap, with the free guides and grants' })).toBeVisible();
});

test('the results page leads with who to approach, then who buys, then the programmes', async ({ page }) => {
  const sent = await asSupplier(page, fixture('profile-es-sup-civil.json'));
  await visit(page, '/readiness/results', { title: /readiness results/i, h1: 'Your readiness results' });
  const approach = page.locator('[data-approach-summary-section]');
  await expect(approach.getByRole('heading', { name: 'Who to approach' })).toBeVisible();
  // WP-89: two columns, the direct suppliers of Spain (the company's country) first, the large primes beside them
  await expect(approach.locator('[data-approach-home] h3')).toHaveText('Direct suppliers in Spain');
  await expect(approach.locator('[data-approach-winner]').first()).toContainText(HOME[0].name);
  await expect(approach.locator('[data-approach-home] [data-approach-winner]')).toHaveCount(Math.min(5, HOME.length));
  await expect(approach.locator('[data-approach-primes] h3')).toHaveText('Large primes');
  await expect(approach.locator('[data-approach-primes] [data-approach-winner]').first()).toContainText(PRIMES[0].name);
  await expect(approach.locator('[data-approach-winner]')).toHaveCount(Math.min(5, HOME.length) + Math.min(5, PRIMES.length));
  await expect(page.getByRole('heading', { name: 'Where you stand, programme by programme' })).toBeVisible();
  const headings = await page.locator('#main h2').allInnerTexts();
  expect(headings.indexOf('Who to approach')).toBeLessThan(headings.indexOf('Who buys what you make'));
  expect(headings.indexOf('Who buys what you make')).toBeLessThan(headings.indexOf('Where you stand, programme by programme'));
  expect(sent).toHaveLength(1);
  await expect(page.locator('[data-demand-row]').first()).toBeVisible();
  await noSideScroll(page);
  await approach.getByRole('link', { name: 'Who to approach in your supplier report' }).click();
  await expect(page).toHaveURL(/\/readiness\/supplier\/report#r-approach$/);
});

test('codes too broad for one map: the report says to choose more specific codes, and the rest stands', async ({ page }) => {
  await asSupplier(page, fixture('profile-es-sup-civil.json'));
  const message = 'These CPV codes cover too many defence-scope notices for one map (more than 30,000 in three years). Choose more specific codes.';
  await page.route('**/api/readiness/demand', (route) => route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'too_broad', message } }) }));
  await page.goto('/readiness/supplier/report');
  await expect(page.locator('[data-report-section="r-approach"]').getByText(message)).toBeVisible();
  await expect(page.locator('[data-item="REQ-RID"]')).toBeVisible();
});

test('without CPV codes the report says how to get the list, and asks nothing', async ({ page }) => {
  const profile = fixture('profile-es-sup-civil.json');
  const sent = await asSupplier(page, { ...profile, supplier: { ...profile.supplier, cpv: [] } });
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  const s = page.locator('[data-report-section="r-approach"]');
  await expect(s.getByRole('link', { name: 'Add CPV codes to my supplier profile' })).toHaveAttribute('href', '/readiness/supplier');
  await expect(s.locator('[data-approach-winner]')).toHaveCount(0);
  await expect(page.locator('[data-report-section="r-roadmap"]')).toBeVisible();
  expect(sent).toEqual([]);
});

test('the entry page and the supplier page say the new order', async ({ page }) => {
  await visit(page, '/readiness/spain-automotive', { title: /Spain automotive: who to approach/, h1: 'Supplier readiness: Spain automotive' });
  const main = page.locator('#main');
  // WP-88: the lead is one sentence (owner-approved copy change); the order is the same
  await expect(main.getByText('the report shows who wins and who buys it in five countries, then the rules', { exact: false })).toBeVisible();
  await expect(main.getByText('Why this order:', { exact: false })).toBeVisible();
  await expect(page.locator('[data-summary-es]')).toContainText('El informe empieza por las empresas que ganan contratos');
  await visit(page, '/readiness/supplier', { title: /Supplier profile: who to approach/, h1: 'Supplier profile' });
  await expect(page.locator('[data-supplier-audience]')).toContainText('it lists first who to approach');
});
