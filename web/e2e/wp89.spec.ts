import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-89 (UX audit of 22 October 2026, section 4: the supplier path). Persona Marta: a Valencian automotive parts maker, her profile as the
 * audit stored it (state.json of the audit: seven CPV codes, machining and casting, ISO 9001 and IATF 16949, region ES-VC). What this proves:
 * the results lead with the Spanish winners and the supply routes, the EU programmes collapsed, a missing answer linked to the supplier page;
 * the roadmap asks the supply routes only and has no PIC; the supplier page's CPV search finds products before machines and offers the
 * automotive set; /buyers and /market take a CPV code; the report says plainly that her region has no programme, marks closed calls, states
 * each cost once in the roadmap's words, the contract values' rules once, links a winner's page with her codes, and prints in fewer pages.
 * Screenshots and the PDF go to WP89_SHOTS when it is set (the self-check), else to the test's output folder.
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
const DEMO = JSON.parse(readFileSync(path.join(__dirname, '..', 'lib', 'mock', 'demand.json'), 'utf8'));
const SHOTS = process.env.WP89_SHOTS;

const MARTA = {
  version: 3, step: 1, updatedAt: '2026-10-22T19:00:31.202Z', name: '', sizeClass: 'medium', country: 'ES', legalForm: '', applicantKind: '',
  management: '', managementCountry: '', control: 'no', uaOccupied: '', uaPartner: '', seapPartner: '', regime: '', componentPct: '',
  restricted: '', uaEeaComponents: '', safeRole: '',
  statuses: { 'REQ-ISO9001': 'held', 'REQ-EN9100': 'not_held', 'REQ-AQAP2110': 'not_held', 'REQ-AQAP2310': 'not_held', 'REQ-PECAL': 'not_held', 'REQ-RID': 'not_held', 'REQ-NCAGE': 'not_held' },
  classified: 'unsure', exportIntent: 'within_eu',
  supplier: {
    region: 'ES-VC', foreignOwner: 'no', foreignCountry: '', nace: '',
    cpv: ['34300000', '34320000', '34330000', '35420000', '44470000', '34322000', '44500000'],
    processes: ['machining', 'casting'], held: ['IATF16949'], expiry: {}, usComponents: 'no', answers: {},
  },
};

/** The stored profile, and the assess answers by what is asked: the supply routes only (the roadmap) or every programme. */
async function asMarta(page: Page, profile: unknown = MARTA): Promise<{ programmes: (string[] | undefined)[] }> {
  const asked: { programmes: (string[] | undefined)[] } = { programmes: [] };
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, profile);
  await page.route('**/api/readiness/assess', async (route) => {
    const body = route.request().postDataJSON() as { programmes?: string[] };
    asked.programmes.push(body.programmes);
    const answer = fixture(body.programmes ? 'assess-es-sup-civil-routes.json' : 'assess-es-sup-civil.json');
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(answer) });
  });
  return asked;
}

const shot = async (page: Page, name: string, full = false) => {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: full });
};

test('results: Spanish winners first, the supply routes first, EU funding collapsed, missing answers asked on the supplier page', async ({ page }, info) => {
  await asMarta(page);
  await visit(page, '/readiness/results', { title: /readiness results/i, h1: 'Your readiness results' });
  const approach = page.locator('[data-approach-summary-section]');
  await expect(approach.locator('[data-approach-home] h3')).toHaveText('Direct suppliers in Spain');
  const home = approach.locator('[data-approach-home] [data-approach-winner]');
  await expect(home).toHaveCount(5);
  await expect(home.first()).toContainText('(Spain)');
  await expect(approach.locator('[data-approach-primes] h3')).toHaveText('Large primes');
  await expect(approach.getByRole('link', { name: `All ${DEMO.total.winners} winners for these codes` })).toBeVisible();
  // a winner's supplier page is linked with her codes and the report's countries
  await expect(home.first().getByRole('link').first()).toHaveAttribute('href', /^\/suppliers\/[^?]+\?cpv=34300000%2C34320000.*&buyerCountry=ES%2CDE%2CFR%2CPL%2CNL$/);

  const cards = page.locator('[data-supplier-routes] > div [data-programme]');
  await expect(cards.first()).toHaveAttribute('data-programme', 'ES-MOD');
  await expect(cards.nth(1)).toHaveAttribute('data-programme', 'NATO-SUPPLY');
  const eu = page.locator('[data-eu-funding="collapsed"]');
  await expect(eu.locator(':scope > summary')).toHaveText(/If you also want EU funding \(4 programmes\)/);
  expect(await eu.evaluate((d) => (d as HTMLDetailsElement).open)).toBe(false);
  await expect(eu.locator('[data-programme="EDF"]')).toBeHidden();
  // every missing answer of a card links to the supplier page, none to a step of the readiness check
  expect(await page.locator('[data-programme] a[data-supplier-asks]').count()).toBeGreaterThan(0);
  await expect(page.locator('[data-programme] a[href^="/readiness?step"]')).toHaveCount(0);
  if (info.project.name === 'desktop') await shot(page, 'after-results-fold');
});

test('roadmap: the supply routes only, no PIC, and the way to add EU funding', async ({ page }) => {
  const asked = await asMarta(page);
  await visit(page, '/readiness/roadmap', { title: /roadmap/i, h1: 'Your roadmap' });
  await expect(page.locator('[data-step]').first()).toBeVisible();
  expect(asked.programmes).toContainEqual(['ES-MOD', 'NATO-SUPPLY']);
  await expect(page.locator('[data-step="REQ-PIC"]')).toHaveCount(0);
  await expect(page.locator('[data-roadmap-routes]')).toContainText('What only the EU funding programmes ask (the PIC) is left out');
  await expect(page.locator('[data-roadmap-routes] a')).toHaveAttribute('href', '/readiness/supplier#sp-eu');
  // one cost statement: the roadmap's words are the report's (below) and the requirement page's
  await expect(page.locator('[data-step="REQ-NCAGE"] [data-step-cost]')).toHaveText('Free of charge (NSPA)');
  await expect(page.locator('[data-step="REQ-RID"] [data-step-cost]')).toHaveText('Not stated by the source');
  await expect(page.locator('[data-step="REQ-RID"] [data-step-time]')).toHaveText('Not stated by the source');
});

test('a supplier that wants EU funding answers the EU questions on its own page, and its roadmap asks every programme', async ({ page }) => {
  const asked = await asMarta(page);
  await visit(page, '/readiness/supplier', { title: /supplier profile/i, h1: /supplier profile/i });
  const eu = page.locator('#sp-eu').locator('xpath=ancestor::section[1]');
  await expect(eu.locator('[data-eu-questions]')).toHaveCount(0);
  await eu.getByRole('radio', { name: 'Yes' }).first().check();
  await expect(eu.locator('[data-eu-questions]')).toBeVisible();
  await eu.getByRole('radio', { name: /A legal person/ }).check();
  await eu.locator('#q-REQ-PIC').getByRole('radio', { name: 'No', exact: true }).check();
  const stored = await page.evaluate(() => JSON.parse(window.localStorage.getItem('dg.profile.v1') ?? '{}'));
  expect(stored.supplier.euFunding).toBe('yes');
  expect(stored.legalForm).toBe('legal_person');
  expect(stored.statuses['REQ-PIC']).toBe('not_held');
  await page.goto('/readiness/roadmap');
  await expect(page.locator('[data-step]').first()).toBeVisible();
  expect(asked.programmes.at(-1)).toBeUndefined();
  await expect(page.locator('[data-roadmap-routes]')).toHaveCount(0);
  await page.goto('/readiness/results');
  await expect(page.locator('[data-eu-funding="open"] [data-programme="EDF"]')).toBeVisible();
});

test('CPV search: castings finds the products before the machines, machined parts find part codes, a suggested set', async ({ page }, info) => {
  await asMarta(page, { ...MARTA, supplier: { ...MARTA.supplier, cpv: [] } });
  await visit(page, '/readiness/supplier', { title: /supplier profile/i, h1: /supplier profile/i });
  const search = page.getByLabel('Search the CPV codes');
  await search.fill('castings');
  await expect(page.locator('#q-cpv label').filter({ hasText: '44470000' }).first()).toBeVisible();
  const texts = await page.locator('#q-cpv label').filter({ hasText: /^\d{8}/ }).allInnerTexts();
  expect(texts[0]).toMatch(/^44470000 Cast-iron products/);
  const machines = texts.findIndex((t) => t.startsWith('43720000'));
  if (machines >= 0) expect(machines).toBeGreaterThan(texts.findIndex((t) => t.startsWith('34320000')));
  await expect(page.locator('[data-cpv-note]')).toContainText('no code for castings as such');
  if (info.project.name === 'desktop') await page.locator('#q-cpv').screenshot({ path: SHOTS ? path.join(SHOTS, 'after-cpv-castings.png') : info.outputPath('cpv.png') });
  await search.fill('machined parts');
  await expect(page.locator('#q-cpv label').filter({ hasText: '34320000' }).first()).toBeVisible();
  await search.fill('');
  await page.getByRole('button', { name: 'Automotive supplier: suggested codes' }).click();
  await expect(page.locator('[data-cpv-suggested] [role="status"]')).toHaveText('9 codes of “Automotive supplier” added. Remove below the ones that do not fit what you do.');   // WP-105: 35400000 in place of 35420000 and 35421000
  const chosen = page.getByRole('list', { name: 'Your CPV codes' }).locator('li');
  await expect(chosen).toHaveCount(9);
  await page.getByRole('button', { name: 'Remove 31611000' }).click();
  await expect(chosen).toHaveCount(8);
});

test('/buyers and /market take a CPV code', async ({ page }, info) => {
  await visit(page, '/buyers?cpv=343', { title: /buyers/i, h1: 'Buyers' });
  await expect(page.getByLabel('CPV code')).toHaveValue('343');
  await expect(page.getByText('Buyers with at least one tender under CPV 343; the counts are of all their tenders')).toBeVisible();
  if (info.project.name === 'desktop') await shot(page, 'after-buyers-cpv');
  await visit(page, '/buyers?cpv=99', { title: /buyers/i, h1: 'Buyers' });
  await expect(page.getByText('No buyers match these filters')).toBeVisible();
  await visit(page, '/buyers?cpv=abc', { title: /buyers/i, h1: 'Buyers' });
  await expect(page.getByText('Ignored filter: cpv=abc (CPV codes are 2 to 8 digits)')).toBeVisible();
  await visit(page, '/market?cpv=343', { title: /market/i, h1: 'Market overview' });
  await expect(page.getByLabel('CPV code (optional)')).toHaveValue('343');
  await expect(page.getByRole('heading', { name: /Notices published per month/ }).first()).toBeVisible();
  // WP-96: the headline names the set it counts ("Notices of military goods and works, ...")
  await expect(page.locator('main').getByText(/^Notices of military goods and works, .*, CPV 343$/).first()).toBeVisible();
  await expect(page.locator('a[href*="/tenders?country="]').first()).toHaveAttribute('href', /&cpv=343$/);
});

test('a supplier page reached from the report says how many of its contracts are under the codes', async ({ page }) => {
  await visit(page, '/suppliers/1-demo-airframes-gmbh?cpv=34300000&buyerCountry=ES,DE', { title: /Demo Airframes/i, h1: 'Demo Airframes GmbH' });
  await expect(page.locator('[data-under-codes]')).toHaveText('7 of them under your CPV codes, in Spain, Germany, as in your supplier report');
  await visit(page, '/suppliers/1-demo-airframes-gmbh', { title: /Demo Airframes/i, h1: 'Demo Airframes GmbH' });
  await expect(page.locator('[data-under-codes]')).toHaveCount(0);
});

test('the report: no programme of her region said plainly, closed calls marked, one cost statement, the rules once, fewer pages', async ({ page }, info) => {
  await asMarta(page);
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  await expect(page.locator('[data-item]').first()).toBeVisible();
  await expect(page.locator('[data-approach-winner]').first()).toBeVisible();
  const rid = page.locator('[data-item="REQ-RID"]');
  await expect(rid.locator('[data-item-no-grant]')).toContainText('No programme of Comunitat Valenciana in our sources pays for this step. Ask your regional development agency');
  await expect(page.locator('[data-item-grants]')).toHaveCount(0);           // Murcia's, Aragón's and Galicia's are not hers
  await expect(page.locator('[data-item="REQ-NCAGE"] [data-item-cost]')).toHaveText('Free of charge (NSPA)');
  await expect(rid.locator('[data-item-cost]')).toHaveText('Not stated by the source');
  await expect(page.locator('[data-report-section="r-approach"] [data-value-rules]')).toHaveCount(1);
  await expect(page.locator('[data-approach-home] h3')).toHaveText('Direct suppliers in Spain');
  // the appendix lists her supply routes first
  const programmes = await page.locator('[data-report-programme]').evaluateAll((els) => els.map((e) => e.getAttribute('data-report-programme')));
  expect(programmes.slice(0, 2)).toEqual(['ES-MOD', 'NATO-SUPPLY']);
  // the same steps for a Galician company: its own region's calls only, a closed one marked
  if (info.project.name !== 'desktop') return;
  await shot(page, 'after-report-fold');
  await page.emulateMedia({ media: 'print' });
  await shot(page, 'after-report-print', true);
  const pdf = await page.pdf({ format: 'A4', printBackground: false });
  const pages = (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) ?? []).length;
  if (SHOTS) {
    writeFileSync(path.join(SHOTS, 'after-report.pdf'), pdf);
    writeFileSync(path.join(SHOTS, 'after-report-pages.txt'), `${pages}\n`);
  }
  expect(pages).toBeGreaterThan(3);
  expect(pages).toBeLessThanOrEqual(32);                 // 46 on this demo profile before WP-89 (59 on production for the audit's)
});

test('a Galician company sees its own region\'s grants, the closed calls marked', async ({ page }) => {
  await asMarta(page, { ...MARTA, supplier: { ...MARTA.supplier, region: 'ES-GA' } });
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  const grants = page.locator('[data-item="REQ-RID"] [data-item-grants] li');
  await expect(grants).toHaveCount(1);
  await expect(grants.first()).toHaveAttribute('data-grant-region', 'ES-GA');
  await expect(grants.first()).toHaveAttribute('data-grant-closed', 'true');
  await expect(grants.first()).toContainText('Closed');
  await expect(page.locator('[data-grant-region="ES-MC"], [data-grant-region="ES-AR"]')).toHaveCount(0);
});

test('one cost statement: the requirement page says what the report and the roadmap say', async ({ page }) => {
  await visit(page, '/requirements/ncage', { title: /NCAGE/i, h1: /NCAGE/ });
  await expect(page.getByText('Free of charge (NSPA)').first()).toBeVisible();
  await visit(page, '/requirements/rid', { title: /RID/i, h1: /RID/ });
  await expect(page.getByText('Not stated by the source').first()).toBeVisible();
});
