import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-93 (the eligibility check of 23 October 2026), on the demo build: the readiness check asks what the size, control and EIC rules
 * read and keeps it in the same browser block (version 4); the call page's first screen gives the one verdict the list badge gives.
 */

const USI = '/funding/6-edip-2026-supply-chain-security-raw-materials';
const save = (page: Page, p: Record<string, unknown>) =>
  page.addInitScript((value) => { if (!sessionStorage.getItem('wp93')) { window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); sessionStorage.setItem('wp93', '1'); } }, p);
const stored = (page: Page) => page.evaluate(() => JSON.parse(window.localStorage.getItem('dg.profile.v1') ?? 'null'));
const group = (page: Page, name: RegExp) => page.getByRole('group', { name });

const UA = {
  version: 3, step: 6, updatedAt: '2026-10-22T10:00:00.000Z', name: '', sizeClass: 'medium', country: 'UA', legalForm: 'legal_person',
  applicantKind: 'company_or_research', offering: 'products', topics: '', management: 'same', managementCountry: '', control: 'ua_eea_only',
  uaOccupied: 'no', uaPartner: '', seapPartner: '', regime: 'military', componentPct: '', restricted: 'no', uaEeaComponents: 'no', safeRole: 'contractor',
  statuses: {}, classified: 'no', exportIntent: 'none',
};

test('the readiness check asks the size, group and controlling-country questions and keeps them in version 5', async ({ page }) => {
  await save(page, { ...UA, step: 1, control: 'other' });
  await visit(page, '/readiness?step=1', { title: /readiness check/i, h1: 'Readiness check' });
  await group(page, /Which of these is your organisation/).getByLabel('A company', { exact: true }).check();
  await group(page, /How many people does your organisation employ/).getByLabel('250 to 499', { exact: true }).check();
  await expect(group(page, /How many people does the whole group employ/)).toHaveCount(0);
  await group(page, /Is your company part of a group/).getByLabel('Yes', { exact: true }).check();
  await group(page, /How many people does the whole group employ/).getByLabel('2,000 or more', { exact: true }).check();
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(page.getByText('Step 2 of 5: Ownership and control')).toBeVisible();
  await group(page, /Which country controls your company/).getByLabel('China', { exact: true }).check();
  await group(page, /pre-commitment from a single qualified investor/).getByLabel('No', { exact: true }).check();
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(group(page, /share of the estimated cost of the components/)).toBeVisible();
  await group(page, /share of the estimated cost of the components/).getByLabel('35 % or less', { exact: true }).check();
  const p = await stored(page);
  expect(p).toMatchObject({ version: 5, orgKind: 'company', headcount: '250_499', inGroup: 'yes', groupHeadcount: '2000plus', controlCountry: 'cn', investor: 'no', componentBand: 'le35' });
  expect(p.country).toBe('UA');                                                 // the old answers are kept
});

test('the call page and the list badge give the same verdict for the saved profile', async ({ page }) => {
  // every call answers with the facts of a Digital Europe call limited to the EU and the EEA (call 146 of 23 October)
  await page.route('**/api/fit/facts*', async (route) => {
    const ids = (new URL(route.request().url()).searchParams.get('ids') ?? '').split(',').filter(Boolean);
    const fact = (value: unknown, quote: string) => ({ value, note: null, quote, scope: 'call_document' });
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: Object.fromEntries(ids.map((i) => [i, {
      state: 'read', basis: 'call_document', programme: 'DIGITAL', topic: 'DIGITAL-ECCC-2027-DEPLOY-CYBER-11-DUALUSE',
      facts: { eligible_countries: fact('EU Member States (including OCTs); EEA countries (Norway, Iceland, Liechtenstein)', 'Eligible countries: EU and EEA.') } }])) }) });
  });
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json',
    body: JSON.stringify({ generatedAt: '', rulesReviewed: '2026-10-20', assessments: [], general: [], roadmap: { steps: [], tracks: [] }, consultants: [], call: null, notice: '' }) }));
  // the partner suggestions of the call page (WP-91), as in wp91.spec: an answer, so that no request fails
  await page.route('**/api/funding/*/partners*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    call: { id: '6', slug: '6-x', topic: 'EDF-EDIP-USI-2026-SCS' },
    area: { kind: 'edf', label: 'all projects of the European Defence Fund', rule: 'All EDF projects read from the factsheets.', projects: 40, organisations: 120,
      firstYear: 2021, lastYear: 2025, broaderThanCall: false, generic: true, topicWords: ['supply'], topicAlso: [], topicalProjects: 0 },
    partners: [], countries: [], total: 0, country: null, prefer: null, note: null,
    source: { readAt: null, sources: ['CORDIS, European Commission'], licence: 'Commission Decision 2011/833/EU (reuse of Commission documents)' },
  }) }));
  await save(page, { ...UA, orgKind: 'company', headcount: '50_249', inGroup: 'no', controlCountry: 'ua' });
  await visit(page, USI, { title: /Supply chain security/, h1: /Supply chain security/ });
  const verdict = page.locator('[data-apply-summary] [data-profile-verdict]');
  await expect(verdict).toHaveAttribute('data-profile-verdict', 'no');
  await expect(verdict).toContainText('Blocked by: Country');
  await expect(verdict.locator('[data-profile-line="country"]')).toContainText('not among them');
  await visit(page, '/funding', { title: /funding/i, h1: 'Funding' });
  await expect(page.getByText('Blocked by: Country').first()).toBeVisible();
});
