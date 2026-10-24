import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-97 (persona round of 23 October 2026, section B: the supplier report for every country and for services). Four persona profiles as
 * the audit stored them (p01 Aragonese foundry, p03 Bavarian machining, p04 Polish ammunition, p06 Dutch logistics), with assess answers
 * computed by the API's own function over the requirements seed (fixtures assess-*97*.json) and the demo demand answer with the WP-97
 * fields added (open counts and buyer amounts here are test values). What this proves: own country first; the intro by codes and country,
 * the Spanish automotive material only for the Spanish automotive profile; "Open now" first with the list link; buyer amounts; dealers
 * apart; the national route of Germany and Poland and "Not covered yet" elsewhere; Spain's requirements hidden for others; the services
 * path; "I am not sure" not counted as missing and every missing link landing on a question; the supplier path's title and "Change my
 * answers"; the short print. Screenshots and PDFs go to WP97_SHOTS when it is set (the self-check).
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
const DEMO = JSON.parse(readFileSync(path.join(__dirname, '..', 'lib', 'mock', 'demand.json'), 'utf8'));
const SHOTS = process.env.WP97_SHOTS;

const PREFIXES = [...new Set((DEMO.codes as { prefix: string }[]).map((c) => c.prefix))].join(',');
const OPEN: Record<string, number> = { ES: 12, DE: 4, FR: 0, PL: 7, NL: 2 };
/** The demo answer with the WP-97 fields: an open count per country and the first buyer's amount (test values). */
const DEMAND = {
  ...DEMO,
  byCountry: DEMO.byCountry.map((c: { country: string; topBuyers: object[] }) => ({
    ...c,
    openNow: { count: OPEN[c.country], atLeast: false, href: `/tenders?country=${c.country}&cpv=${PREFIXES}` },
    topBuyers: c.topBuyers.map((b, i) => ({ ...b, awardedValue: i === 0 ? [{ currency: 'EUR', amount: 2450000, count: 14, lotEstimates: 0 }] : [] })),
  })),
};

const base = (country: string, extra: object, supplier: object) => ({
  version: 4, step: 1, updatedAt: '2026-10-23T15:05:57.221Z', name: '', sizeClass: 'medium', country, legalForm: '', applicantKind: '', offering: '',
  topics: '', orgKind: 'company', headcount: '50_249', inGroup: 'no', groupHeadcount: '', management: '', managementCountry: '', control: 'no',
  controlCountry: '', investor: '', uaOccupied: '', uaPartner: '', seapPartner: '', regime: '', componentPct: '', componentBand: '', restricted: '',
  uaEeaComponents: '', safeRole: '', statuses: {}, classified: 'no', exportIntent: 'within_eu', ...extra,
  supplier: { region: '', foreignOwner: 'no', foreignCountry: '', nace: '', cpv: [], processes: [], held: [], expiry: {}, usComponents: 'no', answers: {}, euFunding: 'no', ...supplier },
});
const ES_AUTO = base('ES', {
  statuses: { 'REQ-ISO9001': 'held', 'REQ-EN9100': 'not_held', 'REQ-AQAP2110': 'not_held', 'REQ-AQAP2310': 'not_held', 'REQ-PECAL': 'not_held', 'REQ-RID': 'not_held', 'REQ-NCAGE': 'not_held' },
  classified: 'unsure',
}, {
  region: 'ES-AR', nace: '24.51', cpv: ['34300000', '34320000', '34330000', '35420000', '35421000', '34322000', '34312000', '44470000', '44530000', '31611000'],
  processes: ['casting', 'machining'], held: ['IATF16949'],
  answers: { pecal_certificate_wanted: 'unsure', pecal_2310_target: 'no', ncage_need_justified: 'unsure', specific_defence_use: 'no', nato_classified_contract: 'no', nato_icb_bid: 'no', receives_eea_defence_products: 'no' },
});
const DE_MACH = base('DE', { statuses: { 'REQ-ISO9001': 'held', 'REQ-EN9100': 'held', 'REQ-AQAP2110': 'not_held', 'REQ-AQAP2310': 'not_held', 'REQ-NCAGE': 'not_held' } }, {
  region: 'Bayern', nace: '25.62', cpv: ['35421000', '35641000', '34320000', '34913000', '35420000', '34731000', '42141000', '35340000'], processes: ['machining'],
});
const PL_AMMO = base('PL', { headcount: '250_499', classified: 'yes', statuses: { 'REQ-ISO9001': 'held', 'REQ-AQAP2110': 'held' } }, {
  region: 'Podkarpackie', cpv: ['35330000', '35340000', '24610000', '24615000'],
});
const NL_SVC = base('NL', { headcount: '250_499', offering: 'software_services', exportIntent: 'none', statuses: { 'REQ-ISO9001': 'held' } }, {
  cpv: ['60000000', '63100000', '09100000', '79993000', '90900000', '55500000', '50100000', '80600000', '72000000'],
  processes: ['logistics', 'transport', 'fuel'], held: ['VCA', 'ISO14001', 'ISO45001'],
});

/** The stored profile, the demand answer and the assess answers (the supply routes only when they are asked for). */
async function as(page: Page, profile: object, name: string): Promise<void> {
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, profile);
  await page.route('**/api/readiness/assess', async (route) => {
    const body = route.request().postDataJSON() as { programmes?: string[] };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture(`assess-${name}${body.programmes ? '-routes' : ''}.json`)) });
  });
  await page.route('**/api/readiness/demand', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DEMAND) }));
}

const shot = async (page: Page, name: string, full = false) => {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: full });
};

/** The report printed short or in full, as a PDF: its page count (written to WP97_SHOTS with the PDF). */
async function printed(page: Page, version: 'short' | 'full', name: string): Promise<number> {
  await page.evaluate((v) => document.querySelector('.report')!.setAttribute('data-print', v), version);
  await page.emulateMedia({ media: 'print' });
  const pdf = await page.pdf({ format: 'A4', printBackground: false });
  const pages = (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) ?? []).length;
  if (SHOTS) {
    mkdirSync(SHOTS, { recursive: true });
    writeFileSync(path.join(SHOTS, `${name}-${version}.pdf`), pdf);
    writeFileSync(path.join(SHOTS, `${name}-${version}-pages.txt`), `${pages}\n`);
  }
  await page.emulateMedia({ media: 'screen' });
  return pages;
}

test('ES automotive: the supplier report title, open now first, Spain first, Indra only here, not sure is an answer, links land on questions', async ({ page }, info) => {
  await as(page, ES_AUTO, 'es-auto97');
  await visit(page, '/readiness/results?from=supplier', { title: /Your supplier report/, h1: 'Your supplier report' });
  await expect(page.getByRole('navigation', { name: /breadcrumb/i }).getByRole('link', { name: 'Supplier profile' })).toHaveAttribute('href', '/readiness/supplier');
  await expect(page.getByRole('link', { name: 'Change my answers' })).toHaveAttribute('href', '/readiness/supplier');
  // open now, first, with the tender list's link
  const open = page.locator('[data-open-now="ES"]');
  await expect(open.getByRole('heading')).toHaveText('Open now in Spain under your codes (12)');
  await expect(open.locator('[data-open-now-link]')).toHaveAttribute('href', `/tenders?country=ES&cpv=${PREFIXES}`);
  const order = await page.locator('main section[aria-labelledby]').evaluateAll((els) => els.map((e) => e.getAttribute('aria-labelledby')));
  expect(order.slice(0, 3)).toEqual(['open-now', 'approach', 'demand']);
  await expect(page.locator('[data-approach-explainer="automotive"]')).toBeVisible();
  await expect(page.locator('[data-approach-indra]')).toHaveCount(1);
  await expect(page.locator('[data-demand-row]').first()).toHaveAttribute('data-demand-row', 'ES');
  // "I am not sure" is an answer: listed apart, not counted as missing; each missing answer is a question the profile shows
  const mod = page.locator('[data-programme="ES-MOD"]');
  await expect(mod.locator('[data-not-sure-field]')).toHaveCount(3);
  await expect(mod.locator('[data-missing] > p')).toHaveText('5 answers are missing:');
  const hrefs = await mod.locator('[data-missing] a').evaluateAll((as) => as.map((a) => a.getAttribute('href')!));
  expect(hrefs).toHaveLength(5);
  if (info.project.name === 'desktop') await shot(page, 'es-auto-results', true);
  await page.goto('/readiness/supplier');
  for (const h of hrefs) await expect(page.locator(`#${h.split('#')[1]}`), h).toBeVisible();
});

test('ES automotive report: open now, dealers apart, buyer amounts, grants once, a short print of 5 to 10 pages', async ({ page }, info) => {
  await as(page, ES_AUTO, 'es-auto97');
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  await expect(page.locator('[data-item]').first()).toBeVisible();
  const order = await page.locator('[data-report-section]').evaluateAll((els) => els.map((e) => e.getAttribute('data-report-section')));
  expect(order).toEqual(['r-open', 'r-approach', 'r-demand', 'r-results', 'r-roadmap', 'r-profile', 'r-about']);
  await expect(page.locator('[data-approach-dealers] h3')).toHaveText('Competitors and distributors');
  await expect(page.locator('[data-approach-dealers] [data-approach-winner="dealer"]').first()).toContainText('Distributor or dealer, by its name');
  await expect(page.locator('[data-approach-home] [data-approach-winner="dealer"]')).toHaveCount(0);
  await expect(page.locator('[data-demand-country]').first()).toHaveAttribute('data-demand-country', 'ES');
  await expect(page.locator('[data-demand-country="ES"] [data-demand-buyer-value]').first()).toHaveText('Awarded: EUR 2,450,000 over 14 contracts');
  // Aragón's call is printed in full once, the other steps it covers point to it
  const aragon = page.locator('[data-grant-region="ES-AR"]');
  expect(await aragon.count()).toBeGreaterThan(1);
  await expect(page.locator('[data-grant-region="ES-AR"]:not([data-grant-repeat])')).toHaveCount(1);
  await expect(page.locator('[data-item-support]').getByText('Check the current call before you count on it')).toHaveCount(1);
  if (info.project.name !== 'desktop') return;
  await shot(page, 'es-auto-report');
  const short = await printed(page, 'short', 'es-auto-report');
  const full = await printed(page, 'full', 'es-auto-report');
  await page.evaluate(() => document.querySelector('.report')!.setAttribute('data-print', 'short'));
  await page.emulateMedia({ media: 'print' });
  await shot(page, 'es-auto-report-print-short', true);
  expect(short).toBeGreaterThanOrEqual(3);
  expect(short).toBeLessThanOrEqual(10);
  expect(full).toBeGreaterThan(short);
});

test('DE machining: German context first, the national route from primary sources, NCAGE in one sentence, no Spanish material', async ({ page }, info) => {
  await as(page, DE_MACH, 'de-mach97');
  await visit(page, '/readiness/results?from=supplier', { title: /Your supplier report/, h1: 'Your supplier report' });
  await expect(page.locator('[data-open-now="DE"]').getByRole('heading')).toHaveText('Open now in Germany under your codes (4)');
  await expect(page.locator('[data-approach-explainer="machining"]')).toBeVisible();
  await expect(page.locator('[data-approach-indra]')).toHaveCount(0);
  await expect(page.locator('main')).not.toContainText('Automotive suppliers usually');
  await expect(page.locator('[data-demand-row]').first()).toHaveAttribute('data-demand-row', 'DE');
  if (info.project.name === 'desktop') await shot(page, 'de-mach-results', true);

  await visit(page, '/readiness/roadmap', { title: /roadmap/i, h1: 'Your roadmap' });
  const route = page.locator('[data-country-route="DE"]');
  await expect(route.getByRole('heading')).toHaveText('Your national route: Germany');
  await expect(route.locator('[data-route-line="de-export"]')).toContainText('BAFA (AWV § 8 and § 11, AWG § 13)');
  await expect(route.locator('[data-route-line="de-buyer"]')).toContainText('BAAINBw');
  await expect(route.locator('[data-route-line="de-quality"]')).toContainText(/^AQAP quality assuranceNot covered yet for Germany: who requires and who audits AQAP quality assurance\. Check with/);
  const ncage = 'Not covered yet for Germany: which office issues NCAGE codes (for a NATO member, its national codification bureau). Check with NSPA, whose NCAGE request tool is where a request starts.';
  await expect(route.locator('[data-route-line="ncage"]')).toContainText(ncage);
  await expect(page.locator('li[data-step="REQ-NCAGE"] [data-issuer-unverified]')).toContainText(ncage);
  if (info.project.name === 'desktop') await shot(page, 'de-mach-roadmap', true);

  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  await expect(page.locator('[data-item="REQ-NCAGE"]')).toContainText(`Issued by: ${ncage}`);
  await expect(page.locator('[data-item="REQ-NCAGE"]')).not.toContainText('National codification bureau (NCB) of the country');
  await expect(page.locator('[data-item-guide]')).toHaveCount(0);          // Murcia's guides are for Spanish companies
  await expect(page.locator('[data-item="REQ-PIC"]')).toHaveCount(0);       // no EU funding wanted: no PIC
  await expect(page.locator('[data-country-route="DE"]')).toBeVisible();
  if (info.project.name !== 'desktop') return;
  const short = await printed(page, 'short', 'de-mach-report');
  expect(short).toBeLessThanOrEqual(10);
});

test('PL ammunition: Spain\'s requirements hidden, the Polish route says plainly what is not covered and whom to ask', async ({ page }, info) => {
  await visit(page, '/requirements?country=PL', { title: /Requirements/, h1: 'Requirements' });
  await expect(page.getByRole('heading', { name: /RID registration/ })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: /PECAL certification/ })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'NCAGE code' })).toBeVisible();
  await expect(page.locator('[data-requirements-elsewhere]')).toContainText('requirements of the Spanish route are left out');
  const route = page.locator('[data-country-route="PL"]');
  await expect(route.locator('[data-route-line="pl-licence"]')).toContainText('Not covered yet for Poland: the licences to make or trade in weapons, ammunition and explosives');
  await expect(route.locator('[data-route-line="pl-licence"]')).toContainText('Check with the buyer, for example the Armament Agency (Agencja Uzbrojenia)');
  if (info.project.name === 'desktop') await shot(page, 'pl-requirements', true);
  await visit(page, '/requirements?country=ES', { title: /Requirements/, h1: 'Requirements' });
  await expect(page.getByRole('heading', { name: /RID registration/ })).toBeVisible();

  await as(page, PL_AMMO, 'pl-ammo97');
  await visit(page, '/readiness/results?from=supplier', { title: /Your supplier report/, h1: 'Your supplier report' });
  await expect(page.locator('[data-approach-explainer="ammunition"]')).toBeVisible();
  await expect(page.locator('[data-demand-row]').first()).toHaveAttribute('data-demand-row', 'PL');
  if (info.project.name === 'desktop') await shot(page, 'pl-ammo-results', true);
});

test('NL services: the services branch from /check, its processes, certificates and codes, and its report', async ({ page, browser }, info) => {
  await visit(page, '/check', { title: /Check my company/, h1: 'Check my company' });
  await expect(page.getByRole('link', { name: 'Start with services' })).toHaveAttribute('href', '/readiness/supplier?offer=services');
  await page.getByRole('link', { name: 'Start with services' }).click();
  await expect(page.getByLabel('We provide services')).toBeChecked();
  await expect(page.getByRole('heading', { name: 'What you provide' })).toBeVisible();
  for (const label of ['Logistics and warehousing', 'Fuel supply', 'Catering', 'Maintenance and repair', 'Training', 'IT services']) await expect(page.getByLabel(label, { exact: true })).toBeVisible();
  for (const label of ['VCA (safety checklist for contractors)', 'ISO 14001 (environmental management)', 'ISO 45001 (occupational health and safety)', 'ISO 50001 (energy management)', 'ISO/IEC 27001']) {
    await expect(page.getByLabel(label)).toBeVisible();
  }
  const sets = await page.locator('[data-cpv-set]').evaluateAll((els) => els.map((e) => e.getAttribute('data-cpv-set')));
  expect(sets).toEqual(['services', 'automotive', 'machining', 'uniforms', 'naval', 'aviation', 'ammunition']);   // WP-105: textiles, naval, aviation
  await page.getByRole('button', { name: 'Services to the armed forces: suggested codes' }).click();
  await expect(page.getByRole('list', { name: 'Your CPV codes' }).locator('li')).toHaveCount(9);
  if (info.project.name === 'desktop') await shot(page, 'nl-services-profile', true);

  const fresh = await (await browser.newContext({ viewport: page.viewportSize() ?? undefined })).newPage();
  await as(fresh, NL_SVC, 'nl-svc97');
  await visit(fresh, '/readiness/results?from=supplier', { title: /Your supplier report/, h1: 'Your supplier report' });
  await expect(fresh.locator('[data-open-now="NL"]').getByRole('heading')).toHaveText('Open now in the Netherlands under your codes (2)');
  await expect(fresh.locator('[data-approach-explainer="services"]')).toBeVisible();
  await expect(fresh.locator('main')).not.toContainText('Automotive suppliers usually');
  await expect(fresh.locator('[data-demand-row]').first()).toHaveAttribute('data-demand-row', 'NL');
  if (info.project.name === 'desktop') await shot(fresh, 'nl-services-results', true);
  await visit(fresh, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  await expect(fresh.locator('[data-report-section="r-profile"]')).toContainText('Logistics and warehousing, Transport, Fuel supply');
  await expect(fresh.locator('[data-report-section="r-profile"]')).toContainText('VCA (safety checklist for contractors)');
  await expect(fresh.locator('[data-country-route="NL"] [data-route-line="route"]')).toContainText('Not covered yet for the Netherlands: a national supplier route');
  await expect(fresh.getByRole('heading', { name: 'Who buys what you provide' })).toBeVisible();
  if (info.project.name !== 'desktop') return;
  await shot(fresh, 'nl-services-report');
  const short = await printed(fresh, 'short', 'nl-services-report');
  expect(short).toBeLessThanOrEqual(10);
});
