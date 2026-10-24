import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-109 (round 4 of 24 October 2026), on the demo build: one verdict per call page in every state (the first screen and the form share
 * one case and one verdict function), "Fits my profile" re-orders the list itself (not only on screen), the funding list's new status and
 * filter, the call CSV's new columns, and a call page printed on at most two A4 pages.
 */

const CPA = '/funding/21-edip-2027-shared-testing-facilities-manufacturers';
const USI = '/funding/6-edip-2026-supply-chain-security-raw-materials';
const CALL = '/funding/1-edf-2026-additive-manufacturing-spare-parts';
const PROFILE = {
  version: 5, step: 6, updatedAt: '2026-10-24T10:00:00.000Z', name: '', sizeClass: 'small', country: 'PL', legalForm: 'legal_person',
  applicantKind: 'company_or_research', offering: 'software_services', topics: '', orgKind: 'company', headcount: 'lt50', inGroup: 'no', groupHeadcount: '',
  management: 'same', managementCountry: '', control: 'no', controlCountry: '', investor: '', uaOccupied: '', uaPartner: '', seapPartner: '',
  regime: 'dual_use', componentPct: '', componentBand: 'le35', restricted: 'no', uaComponents: 'no', eeaComponents: 'no', safeRole: 'contractor',
  statuses: {}, classified: 'no', exportIntent: 'none',
};
const save = (page: Page, p: Record<string, unknown>) => page.addInitScript((value) => { window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, p);

async function quiet(page: Page) {
  // the call's facts for the saved profile's verdict, as /api/fit/facts serves them (the demo call's programme and topic)
  await page.route('**/api/fit/facts*', async (route) => {
    const ids = (new URL(route.request().url()).searchParams.get('ids') ?? '').split(',').filter(Boolean);
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: Object.fromEntries(ids.map((i) => [i, {
      state: 'read', basis: 'call_document', programme: 'EDIP', topic: i === '21' ? 'EDF-EDIP-P-2027-FNLC-CPA-TEST' : 'EDF-EDIP-USI-2026-SCS',
      facts: { eligible_countries: { value: 'EU Member States', note: null, quote: 'q', scope: 'call_document' } } }])) }) });
  });
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json',
    body: JSON.stringify({ generatedAt: '', rulesReviewed: '2026-10-20', assessments: [], general: [], roadmap: { steps: [], tracks: [] }, consultants: [], call: null, notice: '' }) }));
  await page.route('**/api/funding/*/partners*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    call: { id: '1', slug: '1-x', topic: null }, area: null, partners: [], countries: [], total: 0, country: null, prefer: null, note: 'No earlier projects can be compared with this call.' }) }));
}

test('without a saved profile, the first screen and the form give one verdict for the same answers', async ({ page }) => {
  await quiet(page);
  await visit(page, CPA, { title: /Common procurement/, h1: /Common procurement/ });
  const top = page.locator('[data-apply-summary]');
  await top.getByLabel('Your country').selectOption('BE');
  await top.getByLabel('Your kind of organisation').selectOption('sme');
  await expect(top.locator('[data-page-verdict]')).toHaveAttribute('data-verdict', 'no');
  await expect(top.locator('[data-line="who"]')).toHaveText(/^Companies cannot apply to this call/);
  // the same case further down (when the call has a form), and a public body is a check in both
  const form = page.getByRole('form', { name: 'Check your company against this call' });
  if (await form.count()) {
    await expect(form.getByLabel('What kind of organisation?')).toHaveValue('sme');
    await expect(page.locator('[data-form-verdict]')).toHaveAttribute('data-form-verdict', 'no');
    await form.getByLabel('What kind of organisation?').selectOption('public');
  } else {
    await top.getByLabel('Your kind of organisation').selectOption('public');
  }
  await expect(top.locator('[data-page-verdict]')).toHaveAttribute('data-verdict', 'check');
});

test('the Ukrainian-partner rule is asked and decides the word, on the first screen as in the list', async ({ page }) => {
  await quiet(page);
  await visit(page, USI, { title: /Supply chain security/, h1: /Supply chain security/ });
  const top = page.locator('[data-apply-summary]');
  await top.getByLabel('Your country').selectOption('PL');
  await top.getByLabel('Your kind of organisation').selectOption('sme');
  await expect(top.locator('[data-page-verdict]')).toHaveAttribute('data-verdict', 'check');
  await top.getByLabel('Does a legal entity established in Ukraine take part with you?').selectOption('no');
  await expect(top.locator('[data-page-verdict]')).toHaveText('Not without a Ukrainian partner (you said none takes part)');
  await top.getByLabel('Your country').selectOption('US');
  await expect(top.locator('[data-page-verdict]')).toHaveAttribute('data-verdict', 'no');
});

test('with a saved profile the page says its verdict, and a changed answer is one case for the whole page', async ({ page }) => {
  await quiet(page);
  await save(page, PROFILE);
  await visit(page, CPA, { title: /Common procurement/, h1: /Common procurement/ });
  const top = page.locator('[data-apply-summary]');
  await expect(top.locator('[data-profile-verdict]')).toHaveAttribute('data-profile-verdict', 'no');
  await expect(top.getByLabel('Your country')).toHaveValue('PL');
  await top.getByLabel('Your kind of organisation').selectOption('public');
  await expect(top.locator('[data-profile-verdict]')).toHaveCount(0);
  await expect(top.locator('[data-page-verdict]')).toHaveAttribute('data-verdict', 'check');
});

test('"Fits my profile" puts the calls with the visitor’s topics first in the list itself', async ({ page }) => {
  await quiet(page);           // first: a route added later answers first
  await page.route('**/api/fit/facts*', async (route) => {
    const ids = (new URL(route.request().url()).searchParams.get('ids') ?? '').split(',').filter(Boolean);
    const fact = (value: unknown) => ({ value, note: null, quote: 'q', scope: 'call_document' });
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: Object.fromEntries(ids.map((i) => [i, {
      state: 'read', basis: 'call_document', programme: 'HORIZON', topic: 'HORIZON-CL3-2026-01-BM-01',
      facts: { eligible_countries: fact('EU Member States'), consortium_required: fact(false), sme_only: fact(false), ownership_control_restriction: fact(false) } }])) }) });
  });
  await save(page, { ...PROFILE, topics: 'cyber' });
  await visit(page, '/funding', { title: /funding/i, h1: 'Funding' });
  await page.getByLabel('Fits my profile').check();
  const list = page.locator('ul[data-fit-sorted]');
  await expect(list).toBeVisible();
  // the first item of the list, in the order a screen reader and a copy of the text read it, is a call that names the topic
  const first = list.locator(':scope > li:not([hidden])').first();
  await expect(first).toHaveAttribute('data-topics-matched', /\d/);
  await expect(first).toContainText(/cyber/i);
  const text = await list.innerText();
  expect(text.toLowerCase().indexOf('cyber')).toBeLessThan(200);
});

test('the funding list has "Open and forthcoming" and "Universities and research organisations"', async ({ page }) => {
  await visit(page, '/funding?status=open-forthcoming&who=research', { title: /funding/i, h1: 'Funding' });
  await expect(page.locator('#results')).not.toContainText('No calls match');
  await expect(page.locator('#results article').first()).toBeVisible();
});

test('the call CSV has who may apply, the regime, Ukraine and the minimum consortium, and EDIP calls under their instrument', async ({ request }) => {
  const r = await request.get('/funding/export.csv?status=all');
  expect(r.status()).toBe(200);
  const text = await r.text();
  const header = text.split(/\r?\n/).find((l) => l.includes('title,funder'))!;
  expect(header, text.slice(0, 300)).toBeTruthy();
  for (const col of ['who_may_apply', 'research_may_apply', 'regime', 'open_to_ukraine', 'min_consortium']) expect(header).toContain(col);
  const usi = text.split('\n').find((l) => l.includes('EDF-EDIP-USI-2026-SCS'))!;
  expect(usi).toContain('EDIP Ukraine Support Instrument');
});

test('a call page with its rules prints on at most two A4 pages', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'one print run');
  await quiet(page);
  await visit(page, CALL, { title: /DefenceGate/, h1: /additive manufacturing/i });
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('[data-print-note]')).toBeVisible();
  const pdf = await page.pdf({ format: 'A4', printBackground: false });
  const pages = (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) ?? []).length;
  info.annotations.push({ type: 'call print pages', description: String(pages) });
  expect(pages).toBeLessThanOrEqual(2);
});
