import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * "Does this call fit me?" and partner suggestions (WP-32). The saved profile is put into localStorage before the page
 * loads, as the wizard would have left it. The two reads that need the API (the facts behind the badges, the partner
 * list) and the verdict of the rules engine are answered here, so the specs prove what the browser does with them:
 *
 *   - a visitor without a profile causes no request to /api/fit/facts and sees no badge;
 *   - with a profile each call of a list gets a badge, and "Fits my profile" hides what is not eligible or unknown;
 *   - the call page shows the readiness block with the profile (and the way to the check without one);
 *   - partner suggestions load on request, filter by country, and link to the organisation pages.
 *
 * Read-only. Runs at desktop width and at 375 px. Locators are roles and labels.
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));

const PROFILE_BASE = {
  version: 1, step: 6, updatedAt: '2026-10-17T10:00:00.000Z', name: '', managementSameCountry: true, managementCountry: '',
  uaOccupied: '', regime: 'dual_use', componentPct: '10', restricted: 'no', statuses: {}, classified: 'no', exportIntent: 'none',
};
const profile = (over: Record<string, unknown>) => ({ ...PROFILE_BASE, sizeClass: 'small', control: 'no', ...over });
const ES_SMALL = profile({ country: 'ES' });
const ES_LARGE = profile({ country: 'ES', sizeClass: 'large' });
const UA_SMALL = profile({ country: 'UA', uaOccupied: 'no', name: 'Secret Works Ltd' });

async function saveProfile(page: Page, p: Record<string, unknown> | null) {
  await page.addInitScript((value) => { if (value) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, p);
}

const fact = (value: unknown, scope = 'call_document') => ({ value, note: null, scope });
/** The facts of a call by its id: three kinds, so a list shows every verdict. */
function factsOf(id: number) {
  switch (id % 3) {
    case 0: return { state: 'read', basis: 'call_document', facts: { eligible_countries: fact('EU Member States'), consortium_required: fact(false), sme_only: fact(false), ownership_control_restriction: fact(false) } };
    case 1: return { state: 'read', basis: 'call_document', facts: { eligible_countries: fact('EU Member States'), consortium_required: fact(false), sme_only: fact(true) } };
    default: return { state: 'not_read', basis: 'call_document', facts: {} };
  }
}

/** Answer the facts route, and count the requests. */
async function mockFacts(page: Page): Promise<{ calls: number }> {
  const seen = { calls: 0 };
  await page.route('**/api/fit/facts*', async (route) => {
    seen.calls += 1;
    const ids = (new URL(route.request().url()).searchParams.get('ids') ?? '').split(',').filter(Boolean).map(Number);
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: Object.fromEntries(ids.map((i) => [String(i), factsOf(i)])) }) });
  });
  return seen;
}

const listItems = (page: Page) => page.locator('section[aria-labelledby="results-heading"] > ul > li');

test('a visitor without a profile gets no badge, no request and a way to the check', async ({ page }) => {
  const facts = await mockFacts(page);
  await saveProfile(page, null);
  await visit(page, '/funding?status=all', { title: /funding/i, h1: /funding/i });
  await expect(page.getByRole('link', { name: 'Answer the readiness check' })).toBeVisible();
  await expect(page.getByLabel('Fits my profile')).toHaveCount(0);
  await expect(page.getByText(/^(Eligible|Check|Not eligible|Unknown)$/)).toHaveCount(0);
  await page.waitForTimeout(400);
  expect(facts.calls, 'no request for the facts without a profile').toBe(0);
});

test('with a profile each call of the list gets a badge and the list can be narrowed to what fits', async ({ page }) => {
  const facts = await mockFacts(page);
  await saveProfile(page, ES_LARGE);
  await visit(page, '/funding?status=all', { title: /funding/i, h1: /funding/i });
  const switchBox = page.getByLabel('Fits my profile');
  await expect(switchBox).toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: /On this page: \d+ eligible/ })).toBeVisible();
  expect(facts.calls, 'one request for the page, not one per call').toBe(1);

  // A large company: the SME-only calls are "not eligible", the unread ones "unknown", the open ones eligible.
  const badges = page.locator('article').getByText(/^(Eligible|Check|Not eligible|Unknown)$/);
  await expect(badges.first()).toBeVisible();
  const words = await badges.allTextContents();
  expect(new Set(words).size, `several different verdicts in ${words.join(', ')}`).toBeGreaterThan(1);
  expect(words).toContain('Not eligible');

  const total = await listItems(page).count();
  await switchBox.check();
  const hidden = await page.locator('section[aria-labelledby="results-heading"] > ul > li[hidden]').count();
  expect(hidden).toBeGreaterThan(0);
  expect(hidden).toBeLessThan(total);
  await expect(page.getByRole('status').filter({ hasText: /hidden/ })).toBeVisible();
  await switchBox.uncheck();
  await expect(page.locator('section[aria-labelledby="results-heading"] > ul > li[hidden]')).toHaveCount(0);
});

test('two profiles see different verdicts on the same calls', async ({ browser, baseURL }) => {
  const words: Record<string, string[]> = {};
  for (const [name, p] of [['es', ES_SMALL], ['ua', UA_SMALL]] as const) {
    const context = await browser.newContext({ baseURL });
    const page = await context.newPage();
    await mockFacts(page);
    await saveProfile(page, p);
    await visit(page, '/funding?status=all', { title: /funding/i, h1: /funding/i });
    await expect(page.locator('article').getByText(/^(Eligible|Check|Not eligible|Unknown)$/).first()).toBeVisible();
    words[name] = await page.locator('article').getByText(/^(Eligible|Check|Not eligible|Unknown)$/).allTextContents();
    await context.close();
  }
  expect(words.es.length).toBe(words.ua.length);
  expect(words.es, 'a Spanish company is eligible where a Ukrainian one must check').toContain('Eligible');
  expect(words.ua).not.toContain('Eligible');
  expect(words.ua).toContain('Check');
});

async function firstEdfCall(page: Page): Promise<string> {
  await page.goto('/funding?programme=EDF&status=all');
  const href = await page.locator('a[href^="/funding/"]:not([href*="export"])').first().getAttribute('href');
  expect(href, 'an EDF call on /funding').toMatch(/^\/funding\/\d+/);
  return href!;
}

test('a call page without a profile shows the way to the readiness check and no request goes out', async ({ page }) => {
  let assessed = 0;
  await page.route('**/api/readiness/assess', async (route) => { assessed += 1; await route.abort(); });
  await saveProfile(page, null);
  const href = await firstEdfCall(page);
  await visit(page, href, { title: /DefenceGate/, h1: /.+/ });
  await expect(page.getByRole('heading', { name: 'Your readiness for this call' })).toBeVisible();
  const start = page.getByRole('link', { name: 'Start the readiness check' });
  await expect(start).toHaveAttribute('href', '/readiness');
  await page.waitForTimeout(400);
  expect(assessed, 'nothing is computed without a profile').toBe(0);
});

test('a call page with a profile shows the document rules, the programme rules and the time left', async ({ page }) => {
  const posted: { call?: number; profile: { country: string } }[] = [];
  await page.route('**/api/readiness/assess', async (route) => {
    const body = route.request().postDataJSON() as { call?: number; profile: { country: string } };
    posted.push(body);
    const base = fixture('assess-ua.json');
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        ...base,
        call: {
          id: String(body.call), title: 'A call', programme: 'EDF', status: 'open', deadline: '2026-12-15T17:00:00+00:00', covered: true,
          timings: [{
            programme: 'EDF', name: 'European Defence Fund (EDF)', verdict: 'blocked', deadline: '2026-12-15T17:00:00+00:00', daysLeft: 59,
            steps: ['REQ-PIC'], fastestPathDays: { min: 0, max: 0 }, notFixable: [], realistic: 'yes',
            text: 'The missing steps take up to 0 days; the call closes in 59 days.',
          }],
        },
      }),
    });
  });
  await saveProfile(page, UA_SMALL);
  const href = await firstEdfCall(page);
  await visit(page, href, { title: /DefenceGate/, h1: /.+/ });
  const section = page.getByRole('region', { name: 'Your readiness for this call' });
  await expect(section.getByText(/The programme’s rules allow you once the missing steps are done/)).toBeVisible();
  await expect(section.getByRole('heading', { name: /The rules read from this call’s document/ })).toBeVisible();
  await expect(section.getByRole('heading', { name: /The programme’s rules, and the time left/ })).toBeVisible();
  await expect(section.getByText('European Defence Fund (EDF): Blocked')).toBeVisible();
  await expect(section.getByRole('link', { name: 'Your roadmap' })).toHaveAttribute('href', '/readiness/roadmap');
  await expect(section.getByText(/not legal advice/).first()).toBeVisible();
  expect(posted).toHaveLength(1);
  expect(posted[0].call).toBe(Number(href.match(/\/funding\/(\d+)/)![1]));
  expect(posted[0].profile.country).toBe('UA');
  // The company name never leaves the browser.
  expect(JSON.stringify(posted[0])).not.toContain('Secret');
});

const PARTNERS = {
  call: { id: '1', slug: '1-x', topic: 'EDF-2026-DA-SPACE-PRS-STEP' },
  area: { kind: 'edf-category', label: 'EDF capability category SPACE', rule: 'EDF projects whose factsheet file name names the category SPACE, as this call’s topic code does.', projects: 12, organisations: 40, firstYear: 2022, lastYear: 2025, broaderThanCall: false },
  partners: [
    { organisationId: '11', slug: '11-alpha-sa', name: 'Alpha SA', country: 'FR', projects: 5, coordinated: 2, firstYear: 2022, lastYear: 2025, evidence: [{ projectId: '1', acronym: 'ORBITX', title: 'Orbit', year: 2025, role: 'coordinator' }, { projectId: '2', acronym: 'SKYZ', title: 'Sky', year: 2024, role: 'participant' }] },
    { organisationId: '12', slug: '12-charlie-sl', name: 'Charlie SL', country: 'ES', projects: 2, coordinated: 0, firstYear: 2023, lastYear: 2024, evidence: [{ projectId: '3', acronym: 'MOON', title: 'Moon', year: 2024, role: 'participant' }] },
  ],
  countries: [{ country: 'FR', organisations: 30 }, { country: 'ES', organisations: 10 }],
  total: 40, country: null, note: null,
  source: { readAt: '2026-10-17T12:00:00Z', sources: ['CORDIS, European Commission', 'European Commission, DG DEFIS, EDF results factsheets'], licence: 'Commission Decision 2011/833/EU (reuse of Commission documents)' },
};

async function mockPartners(page: Page): Promise<string[]> {
  const asked: string[] = [];
  await page.route('**/api/funding/*/partners*', async (route) => {
    const url = new URL(route.request().url());
    asked.push(url.searchParams.get('country') ?? '');
    const country = url.searchParams.get('country');
    const partners = country ? PARTNERS.partners.filter((p) => p.country === country) : PARTNERS.partners;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...PARTNERS, partners, country }) });
  });
  return asked;
}

test('partner suggestions load on request, are ranked with their evidence, and filter by country', async ({ page }) => {
  const asked = await mockPartners(page);
  await saveProfile(page, null);
  const href = await firstEdfCall(page);
  await visit(page, href, { title: /DefenceGate/, h1: /.+/ });
  await expect(page.getByRole('heading', { name: 'Partners from earlier projects' })).toBeVisible();
  expect(asked, 'nothing is fetched until the visitor asks').toHaveLength(0);
  await page.getByRole('button', { name: 'Show organisations from earlier projects' }).click();
  await expect(page.getByText('EDF capability category SPACE').first()).toBeVisible();
  const items = page.getByRole('list').filter({ has: page.getByRole('link', { name: 'Alpha SA' }) }).getByRole('listitem');
  await expect(items).toHaveCount(2);
  await expect(items.first()).toContainText('5 projects in this area, 2 as coordinator, latest 2025');
  await expect(items.first()).toContainText('ORBITX (2025, coordinator); SKYZ (2024)');
  await expect(page.getByRole('link', { name: 'Alpha SA' })).toHaveAttribute('href', '/organisations/11-alpha-sa');
  await expect(page.getByText(/not a recommendation/)).toBeVisible();
  await page.getByLabel('Show organisations from').selectOption('ES');
  await expect(page.getByRole('link', { name: 'Alpha SA' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Charlie SL' })).toBeVisible();
  expect(asked).toEqual(['', 'ES']);
});

test('with a profile the partner list loads by itself and puts the profile’s country first', async ({ page }) => {
  const asked = await mockPartners(page);
  await saveProfile(page, ES_SMALL);
  const href = await firstEdfCall(page);
  await visit(page, href, { title: /DefenceGate/, h1: /.+/ });
  const links = page.getByRole('link', { name: /^(Alpha SA|Charlie SL)$/ });
  await expect(links).toHaveCount(2);
  expect(await links.allTextContents()).toEqual(['Charlie SL', 'Alpha SA']);
  await expect(page.getByText(/come first/)).toBeVisible();
  expect(asked).toEqual(['']);
});

test('the home page names the three parts', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: /tenders and funding/i });
  await expect(page.getByRole('heading', { name: 'Three questions, three parts' })).toBeVisible();
  for (const name of [/1\. What is open to me\?/, /2\. Who is already inside\?/, /3\. What do I need to qualify\?/]) {
    await expect(page.getByRole('heading', { name })).toBeVisible();
  }
  await expect(page.getByRole('link', { name: 'Readiness check' })).toHaveAttribute('href', '/readiness');
});
