import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-112 (persona round 4 of 24 October 2026): the results page says what it is computing, and the report opened while the results page's
 * demand request is still on its way waits for that request instead of asking again (p02: "Too many requests"); a services company reads
 * "what you sell"; "who to approach" lists a winner matched by an additional code apart and names a prime's source once per group (p06); the
 * company list credits PLACSP only for a page with its wins (p03, p04, p06); the market's scope switch (p06); the requirements of
 * another country's route (p03). The demo demand answer (lib/mock/demand.json) and the WP-97 assess fixtures.
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
const DEMO = JSON.parse(readFileSync(path.join(__dirname, '..', 'lib', 'mock', 'demand.json'), 'utf8'));
const MACHINING = ['35421000', '35521000', '35641000', '34320000', '34330000', '34913000', '35340000', '44530000'];

const profile = (offering = '') => ({
  version: 4, step: 1, updatedAt: '2026-10-24T15:05:57.221Z', name: '', sizeClass: 'medium', country: 'ES', legalForm: '', applicantKind: '', offering,
  topics: '', orgKind: 'company', headcount: '50_249', inGroup: 'no', groupHeadcount: '', management: '', managementCountry: '', control: 'no',
  controlCountry: '', investor: '', uaOccupied: '', uaPartner: '', seapPartner: '', regime: '', componentPct: '', componentBand: '', restricted: '',
  uaEeaComponents: '', safeRole: '', statuses: { 'REQ-ISO9001': 'held' }, classified: 'no', exportIntent: 'within_eu',
  supplier: { region: '', foreignOwner: 'no', foreignCountry: '', nace: '', cpv: MACHINING, processes: ['machining'], held: [], expiry: {}, usComponents: 'no', answers: {}, euFunding: 'no' },
});

/** The stored profile; assess from the fixtures; demand answered after `delay` ms with `answer`, counted. */
async function as(page: Page, p: object, answer: object = DEMO, delay = 0): Promise<{ demand: number }> {
  const calls = { demand: 0 };
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, p);
  await page.route('**/api/readiness/assess', async (route) => {
    const body = route.request().postDataJSON() as { programmes?: string[] };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture(`assess-de-mach97${body.programmes ? '-routes' : ''}.json`)) });
  });
  await page.route('**/api/readiness/demand', async (route) => {
    calls.demand += 1;
    if (delay) await new Promise((r) => { setTimeout(r, delay); });
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(answer) }).catch(() => { /* page gone */ });
  });
  return calls;
}

test('the results page says what it computes, and the report opened before the answer asks no second time (p02)', async ({ page }) => {
  const calls = await as(page, profile(), DEMO, 2500);
  await page.goto('/readiness/results?from=supplier');
  const status = page.locator('[data-approach-summary-section] [data-computing]');
  await expect(status).toContainText('Finding who wins these contracts: counting three years of defence notices under your codes');
  await expect(page.locator('[data-demand-summary-section] [data-computing]')).toContainText('Computing the demand map');
  // the visitor clicks through before the demand answer has come
  await page.getByRole('link', { name: 'My supplier report' }).first().click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Supplier readiness report');
  await expect(page.locator('[data-approach]')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Too many requests')).toHaveCount(0);
  expect(calls.demand, 'the report waited for the results page\'s request').toBe(1);
});

test('a services company reads "Who buys what you sell" on its results (p06)', async ({ page }) => {
  await as(page, profile('software_services'));
  await visit(page, '/readiness/results?from=supplier', { title: /Your supplier report/, h1: 'Your supplier report' });
  await expect(page.getByRole('heading', { name: 'Who buys what you sell' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Who buys what you make' })).toHaveCount(0);
});

test('who to approach: a winner matched by an additional code apart, a prime\'s source once per group (p01, p02, p06)', async ({ page }) => {
  const answer = structuredClone(DEMO);
  const indra = answer.approach.winners.find((w: { name: string }) => w.name.startsWith('Indra'));
  answer.approach.winners.push({ ...indra, name: 'Indra Soluciones TI SL', slug: '9-indra-soluciones' });
  const uro = answer.approach.winners.find((w: { name: string }) => w.name.startsWith('URO'));
  uro.byOtherCodeOnly = true;
  await as(page, profile(), answer);
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  const side = page.locator('[data-approach-side]');
  await expect(side.getByRole('heading', { name: 'Matched by an additional code only' })).toBeAttached();
  await expect(side.locator('[data-approach-other-code]')).toHaveCount(1);
  await expect(side).toContainText('URO VEHICULOS ESPECIALES');
  await expect(page.locator('[data-approach-home]')).not.toContainText('URO VEHICULOS ESPECIALES');
  const primes = page.locator('[data-approach-primes] [data-approach-winner="prime"]');
  await expect(primes).toHaveCount(3);
  await expect(page.locator('[data-approach-primes] [data-prime-source]')).toHaveCount(2);      // Saab, Indra: once each
  // the buyer links carry the codes, so the buyer's top suppliers are those of the trade
  const link = page.locator('[data-approach-winner] a[href^="/buyers/"]').first();
  await expect(link).toHaveAttribute('href', /\?cpv=35421%2C35521%2C35641%2C3432%2C3433%2C34913%2C3534%2C4453$/);
});

test('the company list credits PLACSP only for a page with its wins (p03, p04, p06)', async ({ page }) => {
  // the demo map holds no PLACSP source, so this shows the Polish page's credit; the per-page rule itself is the API's
  // (tests/integration/test_wp112.py::test_the_supplier_list_credits_placsp_only_for_a_page_with_its_wins)
  await visit(page, '/suppliers?country=PL', { title: /supplier/i, h1: 'Companies' });
  await expect(page.locator('[data-attribution]')).toHaveText('Source: TED, © European Union.');
});

test('the market counts all defence on request, and a German reader is not sent to the Spanish rules (p03, p06)', async ({ page }) => {
  await visit(page, '/market?country=NL&cpv=60', { title: /Market overview/, h1: 'Market overview' });
  await expect(page.getByLabel('What is counted')).toBeAttached();
  await expect(page.locator('[data-market-scope]')).toContainText('to count the services too');
  await visit(page, '/requirements?country=DE', { title: /requirements/i, h1: /requirements/i });
  await expect(page.getByText('Appears in the rules of Spanish defence supplier (MoD).')).toHaveCount(0);
  await expect(page.getByText('No rule we hold for Germany names it').first()).toBeVisible();
});
