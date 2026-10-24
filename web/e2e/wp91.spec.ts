import { mkdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-91 (UX audit of 22 October 2026, section 6: the funding path), on the demo build (lib/mock, NEXT_PUBLIC_DG_NOW 12 October 2026).
 * Persona Piotr, the founder of a 15-person Polish drone-software start-up: an empty country list shows what opens next and what
 * closed; a call page says what it funds and whether a company from his country can apply, above the fold; EDIP USI calls are labelled
 * as such; "software", "autonomy" and "SME" find calls, EUDIS is said not to be collected; cards say who may apply and a filter keeps
 * them; partners rank by the call's topic and Ukraine is a choice for the instrument; organisations are found by project topic; the
 * readiness check has a software branch and "Fits my profile" orders by his topics; a call and a search have calendar files; the
 * requirements say plainly that Poland's NCAGE issuer is not verified. Screenshots go to WP91_SHOTS when it is set.
 */

const SHOTS = process.env.WP91_SHOTS;
const FUNDING = { title: /funding/i, h1: 'Funding' } as const;
const USI = '/funding/6-edip-2026-supply-chain-security-raw-materials';
const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));

const PROFILE = {
  version: 3, step: 6, updatedAt: '2026-10-22T10:00:00.000Z', name: '', sizeClass: 'small', country: 'PL', legalForm: 'legal_person',
  applicantKind: 'company_or_research', offering: 'software_services', topics: '', management: 'same', managementCountry: '', control: 'no',
  uaOccupied: '', uaPartner: '', seapPartner: '', regime: 'dual_use', componentPct: '', restricted: '', uaEeaComponents: '', safeRole: 'other_supplier',
  statuses: {}, classified: 'no', exportIntent: 'none',
};

async function openFilters(page: Page) {
  const button = page.getByRole('button', { name: /^(Show|Hide) filters/ });
  if (await button.isVisible() && (await button.getAttribute('aria-expanded')) !== 'true') await button.click();
}

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: `${SHOTS}/${name}-${page.viewportSize()!.width}.png`, fullPage: false });
}
const save = (page: Page, p: Record<string, unknown> | null) =>
  page.addInitScript((value) => { if (value) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, p);

async function quietApis(page: Page) {
  await page.route('**/api/fit/facts*', async (route) => {
    const ids = (new URL(route.request().url()).searchParams.get('ids') ?? '').split(',').filter(Boolean);
    const fact = (value: unknown) => ({ value, note: null, scope: 'call_document' });
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: Object.fromEntries(ids.map((i) => [i, {
      state: 'read', basis: 'call_document', programme: 'HORIZON', topic: 'HORIZON-CL3-2026-01-BM-01',
      facts: { eligible_countries: fact('EU Member States'), consortium_required: fact(false), sme_only: fact(false), ownership_control_restriction: fact(false) } }])) }) });
  });
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('assess-ua.json')) }));
  await page.route('**/api/funding/*/partners*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    call: { id: '6', slug: '6-x', topic: 'EDF-EDIP-USI-2026-SCS' },
    area: { kind: 'edf', label: 'all projects of the European Defence Fund', rule: 'All EDF projects read from the factsheets.', projects: 40, organisations: 120,
      firstYear: 2021, lastYear: 2025, broaderThanCall: false, generic: true, topicWords: ['supply', 'chain', 'security', 'critical', 'materials'], topicAlso: ['logistics'], topicalProjects: 3 },
    partners: [{ organisationId: '9', slug: '9-materials-sp-z-o-o', name: 'Materials Sp. z o.o.', country: 'PL', projects: 2, coordinated: 0, firstYear: 2023, lastYear: 2024, topical: 2, evidence: [] }],
    countries: [{ country: 'FR', organisations: 30 }, { country: 'PL', organisations: 4 }, { country: 'UA', organisations: 0 }], total: 120, country: null, prefer: null,
    note: 'This topic has no earlier counterpart by area. The organisations whose EDF projects share a word of its title are listed first; after them come those that took part most often in any EDF project.',
    source: { readAt: null, sources: ['CORDIS, European Commission'], licence: 'Commission Decision 2011/833/EU (reuse of Commission documents)' },
  }) }));
}

// ---------------------------------------------------------------- 1. an empty list is never a dead end

test('an empty open list shows what closed and what opens next, with one sentence', async ({ page }) => {
  await visit(page, '/funding?country=FR&q=logistique', FUNDING);
  const empty = page.locator('[data-empty-fallback]');
  await expect(empty.locator('h2')).toHaveText('No open calls in France now, and none is announced; the latest that closed is “Numérisation de la logistique”, on 30 Sep 2026.');
  await expect(empty.getByRole('heading', { name: 'Closed recently' })).toBeVisible();
  await expect(empty.locator('article')).toHaveCount(1);
  await shot(page, 'funding-empty-country');
  await visit(page, '/funding?programme=EDIP&q=equipment', FUNDING);
  await expect(page.locator('[data-empty-fallback] h2')).toHaveText('No open calls for this search now; next expected: “Common procurement of shared testing equipment”, opens 13 Oct 2026.');
  await expect(page.locator('[data-empty-fallback]').getByRole('heading', { name: 'Opening next' })).toBeVisible();
});

test('every entry chip of the funding list lands on calls or on that sentence', async ({ page }) => {
  await visit(page, '/funding', FUNDING);
  const hrefs = await page.getByRole('navigation', { name: 'Browse funding' }).getByRole('link').evaluateAll((as) => as.map((a) => (a as HTMLAnchorElement).getAttribute('href')!));
  expect(hrefs).toContain('/funding?programme=EDIP-USI');
  for (const href of hrefs) {
    await page.goto(href);
    const cards = await page.locator('#results article').count();
    expect(cards, href).toBeGreaterThan(0);
  }
});

// ---------------------------------------------------------------- 3, 4, 5: labels, search, who may apply

test('a Ukraine Support Instrument call is labelled EDIP USI, and has a filter of its own', async ({ page }) => {
  await visit(page, '/funding?programme=EDIP-USI', FUNDING);
  const cards = page.locator('#results article');
  await expect(cards).toHaveCount(1);
  await expect(cards.first().getByText('EDIP USI', { exact: true })).toBeVisible();
  await expect(cards.first().getByText('Open to Ukraine', { exact: true })).toBeVisible();
  await expect(cards.first().getByText('EDF', { exact: true })).toHaveCount(0);
  await openFilters(page);
  await expect(page.getByRole('checkbox', { name: 'EDIP USI (Ukraine Support Instrument)' })).toBeAttached();
  await shot(page, 'funding-usi-label');
});

test('software, autonomy and SME find calls by their topic words; EUDIS is said not to be collected', async ({ page }) => {
  await visit(page, '/funding?q=software', FUNDING);
  await expect(page.locator('#results article').filter({ hasText: 'Space situational awareness data fusion' })).toHaveCount(1);
  await expect(page.getByText(/^Also searched: algorithms, computing/)).toBeVisible();
  await visit(page, '/funding?q=SME&status=all', FUNDING);
  await expect(page.locator('#results article').filter({ hasText: 'Cybersecurity uptake for manufacturing SMEs' })).toHaveCount(1);
  await visit(page, '/funding?q=EUDIS', FUNDING);
  await expect(page.locator('[data-not-collected]')).toContainText('EUDIS, the EU Defence Innovation Scheme, is not a programme we collect');
  await expect(page.locator('[data-not-collected] a')).toHaveCount(0);
});

test('cards say who may apply, and the filter keeps one kind', async ({ page }) => {
  await visit(page, '/funding?who=public&status=all', FUNDING);
  const cards = page.locator('#results article');
  await expect(cards).toHaveCount(1);
  await expect(cards.first().locator('[data-who="public"]')).toHaveText('Public buyers only');
  await visit(page, '/funding?who=companies', FUNDING);
  const n = await page.locator('#results article').count();
  expect(n).toBeGreaterThan(0);
  await expect(page.locator('#results article [data-who="companies"]')).toHaveCount(n);
  await expect(page.locator('#results article [data-who="companies"]').first()).toHaveText('Companies can take part');
  await shot(page, 'funding-who');
});

// ---------------------------------------------------------------- 2. the call page's first screen

test('the call page says what it funds and whether a company from Poland can apply, above the fold', async ({ page }) => {
  await quietApis(page);
  await save(page, PROFILE);
  await visit(page, USI, { title: /Supply chain security/, h1: /Supply chain security/ });
  const funds = page.locator('[data-what-it-funds]');
  await expect(funds).toContainText('What it funds: Supply chain security for critical raw materials. The source’s keywords for this topic: Critical raw materials');
  await expect(funds.getByRole('link', { name: /Read the topic description at/ })).toBeVisible();
  const box = page.locator('[data-apply-summary]');
  await expect(box.locator('[data-line="country"]')).toHaveText(/^From Poland: only together with a partner established in Ukraine/);
  await expect(box.locator('[data-verdict]')).toHaveAttribute('data-verdict', 'check');
  await expect(box.locator('[data-line="territory"]')).toHaveCount(0);
  // above the fold, on a phone too
  const top = (await box.boundingBox())!.y;
  expect(top).toBeLessThan(page.viewportSize()!.height);
  await shot(page, 'call-can-i-apply');
  // the territory note is not shown to a company of Poland
  await expect(page.getByText('Entities established in the non-government controlled areas of Ukraine are not eligible.')).toHaveCount(0);
  // another country, chosen here: Ukraine gets the note, a third country a plain no
  await box.getByLabel('Your country').selectOption('UA');
  await expect(box.locator('[data-line="territory"]')).toContainText('government does not control');
  await box.getByLabel('Your country').selectOption('US');
  await expect(box.locator('[data-verdict]')).toHaveAttribute('data-verdict', 'no');
});

test('a Ukrainian company sees the territory note in the Ukrainian participants panel', async ({ page }) => {
  await quietApis(page);
  await save(page, { ...PROFILE, country: 'UA', uaOccupied: 'no' });
  await visit(page, USI, { title: /Supply chain security/, h1: /Supply chain security/ });
  await expect(page.getByText(/Entities established in the non-government controlled areas of Ukraine are not eligible\./)).toBeVisible();
  await expect(page.locator('[data-apply-summary] [data-line="country"]')).toHaveText(/^From Ukraine: your country is eligible/);
});

test('a common-procurement call tells a company plainly that it cannot apply', async ({ page }) => {
  await quietApis(page);
  await save(page, PROFILE);
  await visit(page, '/funding/21-edip-2027-shared-testing-facilities-manufacturers', { title: /Common procurement/, h1: /Common procurement/ });
  await expect(page.locator('[data-apply-summary] [data-line="who"]')).toHaveText(/^Companies cannot apply to this call\. Who may apply: contracting authorities/);
  await expect(page.locator('[data-apply-summary] [data-verdict]')).toHaveAttribute('data-verdict', 'no');
});

// ---------------------------------------------------------------- 6. partners

test('partners of the instrument rank by the call’s topic and offer Ukraine', async ({ page }) => {
  await quietApis(page);
  await visit(page, USI, { title: /Supply chain security/, h1: /Supply chain security/ });
  await page.getByRole('button', { name: 'Show organisations from earlier projects' }).click();
  await expect(page.locator('[data-topic-words]')).toHaveText('3 projects of this area share a word of the call’s title: supply, chain, security, critical, materials (also searched: logistics).');
  await expect(page.getByText(/2 projects in this area, latest 2024; 2 on this call’s topic\./)).toBeVisible();
  await expect(page.getByLabel('Show organisations from').locator('option', { hasText: 'Ukraine (0)' })).toBeAttached();
});

// ---------------------------------------------------------------- 8. calendar files

test('a call and a funding search have calendar files with exactly their dates', async ({ page, request }) => {
  await quietApis(page);
  await visit(page, USI, { title: /Supply chain security/, h1: /Supply chain security/ });
  const slug = USI.replace('/funding/', '');
  await expect(page.locator('[data-call-ics]').first()).toHaveAttribute('href', `/funding.ics?call=${slug}`);
  const one = await request.get(`/funding.ics?call=${slug}`);
  expect(one.status()).toBe(200);
  expect(one.headers()['content-type']).toContain('text/calendar');
  const file = (await one.text()).replace(/\r\n /g, '');
  expect([...file.matchAll(/^BEGIN:VEVENT/gm)].length).toBe(1);
  expect(file).toMatch(/SUMMARY:Deadline: Supply chain security for critical raw materials/);
  expect((await request.get('/funding.ics?call=19-x')).status()).toBe(404);       // a closed call has no date to come
  expect((await request.get(`/funding.ics?call=${slug}&country=PL`)).status()).toBe(422);

  await visit(page, '/funding?country=PL', FUNDING);
  const link = page.locator('[data-search-ics]').first();
  await expect(link).toHaveAttribute('href', '/funding.ics?country=PL');
  const titles = await page.locator('#results article h2').allInnerTexts();
  const feed = (await (await request.get('/funding.ics?country=PL')).text()).replace(/\r\n /g, '');
  const summaries = [...feed.matchAll(/^SUMMARY:Deadline: (.*)$/gm)].map((m) => m[1].replace(/\\,/g, ',').replace(/\r$/, ''));
  expect(summaries.length).toBe(titles.length);
  for (const s of summaries) expect(titles.some((t) => t.startsWith(s.replace(/…$/, ''))), s).toBe(true);
  expect((await request.get('/funding.ics?status=closed')).status()).toBe(422);
  expect((await request.get('/funding.ics?cpv=35')).status()).toBe(422);
});

// ---------------------------------------------------------------- 6. organisations by project topic; Ukraine partners order

test('organisations are found by the topic of their projects', async ({ page }) => {
  await visit(page, '/organisations?topic=cyber', { title: /organisations/i, h1: 'Companies' });
  const names = await page.locator('main article h2, main article h3').allInnerTexts();
  expect(names.map((n) => n.trim()).sort()).toEqual(['Alpha Systems GmbH', 'Bravo Ingénierie SAS', 'Echo Iberica SL']);
  await expect(page.getByLabel('Project topic')).toHaveValue('cyber');
  await shot(page, 'organisations-topic');
  await visit(page, '/networks/ukraine-partners', { title: /Ukrainian/, h1: 'Ukraine partners' });
  await expect(page.locator('[data-order]')).toContainText('defence programmes come first, then those with projects of the calls we label dual-use');
});

// ---------------------------------------------------------------- 7. the software branch; "Fits my profile" by topics

test('the readiness check skips the component questions for software, and the results say why they stay open', async ({ page }) => {
  await save(page, { ...PROFILE, step: 3 });
  await visit(page, '/readiness?step=3', { title: /readiness check/i, h1: 'Readiness check' });
  await expect(page.locator('[data-skipped-components]')).toContainText('You said you make software or services');
  await expect(page.getByLabel(/Share of component cost/)).toHaveCount(0);
  await expect(page.getByRole('group', { name: /Does any component come from a third country/ })).toHaveCount(0);
  await shot(page, 'readiness-software');

  const answer = fixture('assess-ua.json');
  const usi = answer.assessments.find((a: { programme: string }) => a.programme === 'EDIP-USI');
  usi.missing = [{ field: 'restricted_third_country_component', question: 'Does any component of your end product come from a third country that contravenes the Union’s security and defence interests?' }];
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(answer) }));
  await save(page, PROFILE);
  await visit(page, '/readiness/results', { title: /readiness results|your readiness/i, h1: 'Your readiness results' });
  await expect(page.locator('[data-skipped="restricted_third_country_component"]')).toContainText('left open: you make software or services');
});

test('"Fits my profile" lists the calls with the visitor’s topics first', async ({ page }) => {
  await quietApis(page);
  await save(page, { ...PROFILE, topics: 'software' });
  await visit(page, '/funding', FUNDING);
  await page.getByLabel('Fits my profile').check();
  const first = page.locator('[data-topics-matched]').first();
  await expect(first).toContainText('Matches your topic');      // WP-102: was "Matches 1 of your topic"
  await expect(first).toContainText('Space situational awareness data fusion');
  const order = await first.evaluate((li) => getComputedStyle(li).order);
  expect(Number(order)).toBeLessThan(0);
  await expect(page.getByLabel('Your topics (optional)')).toHaveValue('software');
});

// ---------------------------------------------------------------- 9. requirements in Poland

test('the requirements say plainly that Poland’s NCAGE issuer is not verified, and link NSPA', async ({ page }) => {
  await visit(page, '/requirements?country=PL', { title: /Requirements/, h1: 'Requirements' });
  const ncage = page.locator('li', { has: page.getByRole('heading', { name: 'NCAGE code' }) });
  await expect(ncage.locator('[data-issuer="unverified"]')).toContainText('Not covered yet for Poland: which office issues NCAGE codes');   // WP-97: one NCAGE sentence everywhere
  await expect(ncage.getByRole('link', { name: /NSPA: request an NCAGE code/ })).toHaveAttribute('href', 'https://eportal.nspa.nato.int/Codification/CageTool/request-new-cage');
  await shot(page, 'requirements-poland');
  await visit(page, '/requirements?country=ES', { title: /Requirements/, h1: 'Requirements' });
  await expect(page.locator('li', { has: page.getByRole('heading', { name: 'NCAGE code' }) }).locator('[data-issuer="verified"]')).toContainText('Issued in Spain by');
});
