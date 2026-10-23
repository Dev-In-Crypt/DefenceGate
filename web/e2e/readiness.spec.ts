import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { pace, visit } from './helpers';

/**
 * The readiness check (WP-29): the requirements catalogue, and the wizard with a Ukrainian and a Spanish company.
 *
 * The verdict is computed by the Python rules engine, which the CI run of this site does not have. The route
 * `/api/readiness/assess` is therefore answered here from `e2e/fixtures/assess-*.json`, which the backend generates from
 * the same seed (`python -m dgate.readiness.export`) and tests for drift. What these specs prove: the wizard sends exactly
 * the request in `fixtures/request-*.json` for the answers they give, the pages show the verdicts the fixtures carry,
 * the roadmap re-scores when a step is marked done, and the answers stay in the browser.
 *
 * Read-only against the site; the same file runs at desktop width and at 375 px. Locators are roles and labels.
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));

interface Posted { profile: { country: string }; statuses: Record<string, string> }

/** Answer the assessment route from the fixtures, and remember what the page sent. */
async function mockAssess(page: Page): Promise<Posted[]> {
  const posted: Posted[] = [];
  await page.route('**/api/readiness/assess', async (route) => {
    const body = route.request().postDataJSON() as Posted;
    posted.push(body);
    const answer = body.profile.country === 'ES' ? 'assess-es.json' : body.statuses['REQ-PIC'] === 'held' ? 'assess-ua-pic.json' : 'assess-ua.json';
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture(answer)) });
  });
  return posted;
}

const group = (page: Page, name: RegExp | string) => page.getByRole('group', { name });
const next = (page: Page) => page.getByRole('button', { name: 'Next', exact: true }).click();

async function answerUkraine(page: Page) {
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check' });
  await page.getByLabel('Company name (optional)').fill('Secret Works Ltd');
  await page.getByLabel('Country where your company is established').selectOption('UA');
  await group(page, /legal form of your organisation/).getByLabel(/^A legal person/).check();
  await group(page, /What kind of organisation are you/).getByLabel(/^A company or a research body/).check();
  await next(page);
  await group(page, /executive management structures/).getByLabel('In the country where the company is established').check();
  await group(page, /controlled by a country or an entity outside the EU/).getByLabel('No', { exact: true }).check();
  await group(page, /area of Ukraine that the Ukrainian government does not control/).getByLabel('No', { exact: true }).check();
  await next(page);
  await page.getByLabel('Dual-use (on the Annex I list)').check();
  await page.getByLabel(/Share of component cost from outside the EU/).fill('20');
  await group(page, /component come from a third country/).getByLabel('No', { exact: true }).check();
  await group(page, /originate in Ukraine or in an EEA EFTA state/).getByLabel('No', { exact: true }).check();
  await group(page, /what would your role be/).getByLabel('We would be the contractor').check();
  await next(page);
  await next(page);       // certifications: nothing held
  await group(page, /handle classified information/).getByLabel('No', { exact: true }).check();
  await group(page, /export, or plan to export/).getByLabel('Yes, outside the EU').check();
}

async function answerSpain(page: Page) {
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check' });
  await page.getByLabel('Country where your company is established').selectOption('ES');
  await group(page, /legal form of your organisation/).getByLabel(/^A legal person/).check();
  await group(page, /What kind of organisation are you/).getByLabel(/^A company or a research body/).check();
  await next(page);
  await group(page, /executive management structures/).getByLabel('In the country where the company is established').check();
  await group(page, /controlled by a country or an entity outside the EU/).getByLabel('No', { exact: true }).check();
  await next(page);
  await page.getByLabel('Military (on the Common Military List)').check();
  await page.getByLabel(/Share of component cost from outside the EU/).fill('10');
  await group(page, /component come from a third country/).getByLabel('No', { exact: true }).check();
  await group(page, /originate in Ukraine or in an EEA EFTA state/).getByLabel('No', { exact: true }).check();
  await group(page, /what would your role be/).getByLabel('We would be the contractor').check();
  await next(page);
  await page.getByLabel('ISO 9001 quality management certificate').selectOption({ label: 'We hold it' });
  await next(page);
  await group(page, /handle classified information/).getByLabel('Yes', { exact: true }).check();
  await group(page, /export, or plan to export/).getByLabel('Yes, outside the EU').check();
}

const card = (page: Page, name: string) => page.getByRole('article', { name });

// ---------------------------------------------------------------- the catalogue

test('/requirements lists the requirements with their cost, time and source date', async ({ page }) => {
  await visit(page, '/requirements', { title: /requirements/i, h1: 'Requirements', text: ['About the costs', 'Eligibility rules of the programmes'] });
  await expect(page.getByRole('link', { name: 'NCAGE code' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'AQAP 2110 quality assurance certification' })).toBeVisible();
  await expect(page.getByText('vendor range, not a benchmark').first()).toBeVisible();
  await expect(page.getByText(/Last reviewed \d{1,2} [A-Z][a-z]{2} 2026/).first()).toBeVisible();
});

test('a requirement page says what it is, who issues it, the cost and time, the programmes and the source', async ({ page }) => {
  await visit(page, '/requirements/aqap2110', { title: /AQAP 2110/, h1: 'AQAP 2110 quality assurance certification', text: ['At a glance', 'Who issues it', 'Which programmes ask for it'] });
  await expect(page.getByText('vendor range, not a benchmark').first()).toBeVisible();
  await expect(page.getByText('USD 17,000 to 48,000 for a full cycle').first()).toBeVisible();
  await expect(page.getByText('3-8 months').first()).toBeVisible();
  await expect(page.getByText('PECAL, audited through DGAM structures').first()).toBeVisible();
  await expect(page.getByText(/AQAP 2120 no longer exists/)).toBeVisible();
  // AQAP is shown as a contract matter, not as a condition of the programmes
  await expect(page.getByText(/not a condition for applying to the EDF/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Source', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open the source' })).toHaveAttribute('href', /^https:\/\//);
  await expect(page.getByText(/Last reviewed 7 Sep 2026/).first()).toBeVisible();
});

test('a requirement page carries structured data that repeats what the page says', async ({ page }) => {
  await visit(page, '/requirements/ncage', { title: /NCAGE code/, h1: 'NCAGE code' });
  await expect(page.getByText('In accordance with NATO policy, the assignment and update to the NCAGE are free of charge.')).toBeVisible();
  await expect(page.getByText(/Unidad de Catalogación/).first()).toBeVisible();
  const blocks = await page.locator('script[type="application/ld+json"]').evaluateAll((s) => s.map((n) => JSON.parse(n.textContent ?? '{}')));
  const types = blocks.map((b) => b['@type']);
  expect(types).toEqual(expect.arrayContaining(['BreadcrumbList', 'Article', 'FAQPage']));
  const faq = blocks.find((b) => b['@type'] === 'FAQPage');
  for (const q of faq.mainEntity) {
    // every answer in the data is on the page
    const answer: string = q.acceptedAnswer.text;
    await expect(page.getByText(answer, { exact: false }).first()).toBeVisible();
  }
});

test('an old-style code redirects to the page address and an unknown requirement is a 404', async ({ page }) => {
  await page.goto('/requirements/req-ncage');
  await expect(page).toHaveURL(/\/requirements\/ncage$/);
  await visit(page, '/requirements/nothing-like-it', { status: 404, title: /page not found/i, h1: 'This page is not in the directory' });
});

// ---------------------------------------------------------------- the wizard

test('a Ukrainian company: the wizard sends the answers the rules read and the page shows the verdicts', async ({ page }) => {
  const posted = await mockAssess(page);
  await answerUkraine(page);
  await page.getByRole('button', { name: 'See my results' }).click();
  await expect(page).toHaveURL(/\/readiness\/results$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your readiness results');
  // only the free PIC (Ukraine Support Instrument) or the NCAGE code (NATO) is missing: "Obtain first", not "Blocked".
  // The EDF is "Conditional": Ukraine's association agreement to the EDF is pending signature and not confirmed (V2-B2).
  await expect(card(page, 'European Defence Fund (EDF)')).toContainText('Conditional');
  // EDIP the Programme: Ukraine is not an associated country there, so the company is blocked whatever it obtains
  await expect(card(page, 'European Defence Industry Programme (EDIP): the Programme')).toContainText('Blocked');
  await expect(card(page, 'EDIP: Ukraine Support Instrument')).toContainText('Obtain first');
  await expect(card(page, 'Security Action for Europe (SAFE)')).toContainText('Eligible');
  await expect(card(page, 'NATO and NSPA supply')).toContainText('Obtain first');

  // exactly the request the backend's fixture was made from, and nothing that identifies the company
  expect(posted.length).toBeGreaterThan(0);
  expect(posted[posted.length - 1]).toEqual(fixture('request-ua.json'));
  expect(JSON.stringify(posted)).not.toContain('Secret');

  // every rule: its outcome, its reason, the verbatim source and the link
  const edf = card(page, 'European Defence Fund (EDF)');
  await edf.getByText(/Show the \d+ rules behind this/).click();
  const rule = edf.locator('li[data-rule="EDF-ESTABLISH"]');
  await expect(rule).toContainText('Established in the Union or an associated country');
  await expect(rule).toContainText('Conditional');
  await expect(rule).toContainText('pending the signature of the association agreement to EDF');
  await expect(rule).toContainText('Last reviewed 2026-10-18');
  await expect(rule.getByRole('link', { name: 'Open the source' })).toHaveAttribute('href', 'http://data.europa.eu/eli/reg/2021/697/oj');
  await rule.getByText('Show the text of the source').click();
  await expect(rule).toContainText('Recipients and subcontractors involved in an action shall be established in the Union or in an associated country.');
  await expect(edf.locator('li[data-rule="EDF-PIC"]')).toContainText('To obtain');
  await expect(edf.locator('li[data-rule="EDF-LEGAL-ENTITY"]')).toContainText('Met');
  await expect(edf.locator('li[data-rule="EDF-AQAP"]')).toContainText('For information');
  await pace(page);
});

test('the SAFE card shows the two rules of Article 16(10) and says what the 35 % is measured against', async ({ page }) => {
  await mockAssess(page);
  await answerUkraine(page);
  await page.getByRole('button', { name: 'See my results' }).click();
  const safe = card(page, 'Security Action for Europe (SAFE)');
  await safe.getByText(/Show the \d+ rules behind this/).click();
  await expect(safe.locator('li[data-rule="SAFE-ORIGIN-35"]')).toContainText('estimated cost of the components of the end product');
  await expect(safe.locator('li[data-rule="SAFE-ORIGIN-35"]')).toContainText('not against the contract value');
  await expect(safe.locator('li[data-rule="SAFE-NO-RESTRICTED"]')).toContainText('No component from a third country that contravenes');
});

test('WP-46: the programme cards fill their rows and the cards of a row are equally tall', async ({ page }) => {
  await mockAssess(page);
  await answerUkraine(page);
  await page.getByRole('button', { name: 'See my results' }).click();
  await expect(card(page, 'European Defence Fund (EDF)')).toBeVisible();
  const rows = await page.locator('section[aria-labelledby="programmes"]').evaluate((section) => {
    const outer = section.getBoundingClientRect();
    const by = new Map<number, DOMRect[]>();
    for (const a of section.querySelectorAll('article')) { const r = a.getBoundingClientRect(); const k = Math.round(r.top); by.set(k, [...(by.get(k) ?? []), r]); }
    return { width: outer.width, rows: [...by.values()].map((row) => ({ n: row.length, heights: row.map((r) => Math.round(r.height)), span: Math.max(...row.map((r) => r.right)) - Math.min(...row.map((r) => r.left)) })) };
  });
  expect(rows.rows.reduce((n, r) => n + r.n, 0)).toBe(5);
  for (const r of rows.rows) {
    expect(Math.max(...r.heights) - Math.min(...r.heights), 'cards of one row have one height').toBeLessThanOrEqual(1);
    expect(Math.abs(r.span - rows.width), 'a row spans the section: no empty cell').toBeLessThanOrEqual(2);
  }
});

test('a Ukrainian company: the roadmap in order, with issuers and ranges, and marking a step done re-scores', async ({ page }) => {
  const posted = await mockAssess(page);
  await answerUkraine(page);
  await page.getByRole('button', { name: 'See my results' }).click();
  await page.getByRole('link', { name: 'See my roadmap' }).click();
  await expect(page).toHaveURL(/\/readiness\/roadmap$/);
  const steps = page.locator('li[data-step]');
  await expect(steps).toHaveCount(5);
  expect(await steps.evaluateAll((els) => els.map((e) => e.getAttribute('data-step')))).toEqual(
    ['REQ-PIC', 'REQ-NCAGE', 'REQ-EXPORT', 'REQ-ISO9001', 'REQ-AQAP2110']);
  const aqap = page.locator('li[data-step="REQ-AQAP2110"]');
  await expect(aqap).toContainText('USD 17,000 to 48,000');
  await expect(aqap).toContainText('vendor range, not a benchmark');
  await expect(aqap).toContainText('Only when a contract names it');
  await expect(aqap).toContainText('Commercial and partner certification bodies');
  await expect(aqap).toContainText('Comes after');
  await expect(page.locator('li[data-step="REQ-NCAGE"]')).toContainText('National Codification Bureau of Ukraine');
  await expect(page.locator('li[data-step="REQ-EXPORT"]')).toContainText('has not been collected');
  await expect(page.getByText(/different tracks do not depend on each other/)).toBeVisible();
  await expect(page.locator('[data-totals="required"]')).toContainText('5 to 20 days');
  await expect(page.locator('[data-totals="with-optional"]')).toContainText('USD 17,000 to 48,000');
  // WP-53 (T7): two of the three steps are free and one states no cost: the headline says so and never reads "Free"
  await expect(page.locator('[data-totals="required"] dd').first()).toHaveText('2 steps free, 1 with no stated cost');
  await expect(page.locator('[data-totals="required"] dd').nth(1)).toHaveText('5 to 20 days, 1 with no stated time');
  await expect(page.locator('[data-totals="with-optional"] dd').first()).toHaveText('USD 17,000 to 48,000, 2 steps free, 2 with no stated cost');

  await page.getByRole('button', { name: 'Mark as done: PIC (Participant Identification Code)' }).click();
  await expect(page.locator('li[data-step="REQ-PIC"]')).toHaveCount(0);
  // WP-53: the card that held the focus is gone; focus moves to the heading of the step that follows it, and the change is announced
  await expect(page.locator('[data-step-heading="REQ-NCAGE"]')).toBeFocused();
  await expect(page.getByRole('status').filter({ hasText: 'is marked as done' })).toHaveText('PIC (Participant Identification Code) is marked as done. 4 steps are left. Your results are re-scored.');
  expect(posted[posted.length - 1].statuses['REQ-PIC']).toBe('held');
  expect(await page.evaluate(() => JSON.parse(window.localStorage.getItem('dg.profile.v1') ?? '{}').statuses['REQ-PIC'])).toBe('held');

  await page.getByRole('link', { name: 'My results' }).click();
  await expect(card(page, 'European Defence Fund (EDF)')).toContainText('Conditional');
  await expect(card(page, 'EDIP: Ukraine Support Instrument')).toContainText('Eligible');
  await expect(card(page, 'European Defence Industry Programme (EDIP): the Programme')).toContainText('Blocked');
});

test('a Spanish company with ISO 9001: no vendor price for the state AQAP route, the Spanish issuers and the verdicts', async ({ page }) => {
  const posted = await mockAssess(page);
  await answerSpain(page);
  await page.getByRole('button', { name: 'See my results' }).click();
  await expect(card(page, 'Security Action for Europe (SAFE)')).toContainText('Eligible');
  await expect(card(page, 'European Defence Fund (EDF)')).toContainText('Obtain first');
  await expect(card(page, 'European Defence Industry Programme (EDIP): the Programme')).toContainText('Obtain first');
  expect(posted[posted.length - 1]).toEqual(fixture('request-es.json'));
  await expect(page.getByRole('heading', { name: 'Other requirements that may apply to you' })).toBeVisible();
  await page.getByRole('link', { name: 'See my roadmap' }).click();
  const aqap = page.locator('li[data-step="REQ-AQAP2110"]');
  // Spain's AQAP route is the state's own (PECAL): the vendor ranges of the sources do not describe it, so none is shown
  await expect(aqap).toContainText('the state issues this itself');
  await expect(aqap).not.toContainText('USD');
  await expect(page.locator('li[data-step="REQ-ISO9001"]')).toHaveCount(0);
  await expect(page.locator('li[data-step="REQ-REOCE"]')).toContainText('Secretaría de Estado de Comercio');
  await expect(page.locator('li[data-step="REQ-FSC-ES"]')).toContainText('Oficina Nacional de Seguridad');
  await expect(page.locator('li[data-step="REQ-EXPORT"]')).toContainText('Before or together with');
});

// ---------------------------------------------------------------- the browser keeps the answers

test('the answers stay in this browser: a reload keeps them, nothing is sent but the verdict call, and they can be cleared', async ({ page, context }) => {
  const origin = new URL(test.info().project.use.baseURL ?? 'http://127.0.0.1:3000').host;
  const hosts = new Set<string>();
  page.on('request', (r) => hosts.add(new URL(r.url()).host));
  await mockAssess(page);
  await answerUkraine(page);
  await page.getByRole('button', { name: 'See my results' }).click();
  await expect(card(page, 'European Defence Fund (EDF)')).toBeVisible();

  const stored = await page.evaluate(() => window.localStorage.getItem('dg.profile.v1'));
  expect(stored).toContain('"country":"UA"');
  await page.reload();
  await expect(card(page, 'European Defence Fund (EDF)')).toContainText('Conditional');
  await page.goto('/readiness');
  // U7: a finished profile with nothing unanswered is changed from the first step; any step is one click away.
  await expect(page.getByText('Step 1 of 5: Your company')).toBeVisible();
  await page.getByRole('button', { name: /^Go to step 5/ }).click();
  await expect(page.getByLabel('Yes, outside the EU')).toBeChecked();
  expect(await context.cookies()).toEqual([]);
  expect([...hosts].filter((h) => h !== origin && h !== new URL(page.url()).host)).toEqual([]);

  // U7: clearing asks first, and "Keep my answers" leaves everything as it was.
  await page.getByRole('button', { name: 'Clear my answers' }).click();
  await expect(page.getByRole('alertdialog', { name: 'Clear my answers' })).toBeVisible();
  await page.getByRole('button', { name: 'Keep my answers' }).click();
  expect(await page.evaluate(() => window.localStorage.getItem('dg.profile.v1'))).toContain('"country":"UA"');
  await page.getByRole('button', { name: 'Clear my answers' }).click();
  await page.getByRole('button', { name: 'Yes, clear them' }).click();
  expect(await page.evaluate(() => window.localStorage.getItem('dg.profile.v1'))).toBeNull();
  await page.goto('/readiness/results');
  await expect(page.getByText('No answers in this browser yet')).toBeVisible();
});

test('the first step needs a country, and a page of results without answers says so', async ({ page }) => {
  await visit(page, '/readiness/roadmap', { title: /roadmap/i, h1: 'Your roadmap', text: ['No answers in this browser yet'] });
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check' });
  await next(page);
  await expect(page.getByText('Choose a country to go on.')).toBeVisible();
  await expect(page.getByText('Choose the legal form to go on.')).toBeVisible();
  await expect(page.getByText('Step 1 of 5: Your company')).toBeVisible();
});

test('the wizard page says where the answers go and what the check does not do', async ({ page }) => {
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check', text: ['Your answers are not stored on our server', 'What it does not do'] });
  await expect(page.getByText(/not legal advice/).first()).toBeVisible();
  await expect(page.getByText(/AQAP quality certification is not an eligibility condition/)).toBeVisible();
});
