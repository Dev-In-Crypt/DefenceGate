import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-107 (round 3, 24 October 2026: readiness wizard and roadmap), on the demo build. A Horizon Cluster 3 card in the results; the component
 * questions of a software firm collapsed, not counted as missing (p05); the EEA-recipient question asked in step 5 (p09); the ANSSI
 * qualifications in step 4 (p05); the clearer 35 % Ukraine wording (p08); the roadmap follows the result: rules to settle, steps left out,
 * the size of a vendor range, the step that sets the total time, no unverified issuer named (p09, p03); "what you sell" for services (p06).
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
const group = (page: Page, name: RegExp) => page.getByRole('group', { name });
const save = (page: Page, p: Record<string, unknown>) =>
  page.addInitScript((value) => { if (!sessionStorage.getItem('wp107')) { window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); sessionStorage.setItem('wp107', '1'); } }, p);
const stored = (page: Page) => page.evaluate(() => JSON.parse(window.localStorage.getItem('dg.profile.v1') ?? 'null'));
const answer = (page: Page, body: unknown) =>
  page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }));

const BE = {
  version: 5, step: 6, updatedAt: '2026-10-24T10:00:00.000Z', name: '', sizeClass: 'large', country: 'BE', legalForm: 'legal_person',
  applicantKind: 'company_or_research', offering: 'software_services', topics: '', orgKind: 'company', headcount: '2000plus', inGroup: 'no', groupHeadcount: '',
  management: 'same', managementCountry: '', control: 'other', controlCountry: 'other_non_eu', investor: '', uaOccupied: '', uaPartner: 'no', seapPartner: '',
  regime: 'none', componentPct: '', componentBand: '', restricted: '', uaComponents: '', eeaComponents: '', safeRole: 'contractor', statuses: {},
  classified: 'no', exportIntent: 'none',
};

test('the results have a Horizon Cluster 3 card, and a software firm’s component questions are one collapsed note, not missing answers', async ({ page }) => {
  const body = fixture('assess-ua.json');
  const edip = body.assessments.find((a: { programme: string }) => a.programme === 'EDIP');
  edip.missing = [
    { field: 'legal_form', question: 'What is the legal form of your organisation?' },
    { field: 'restricted_third_country_component', question: 'Does any component of your end product come from a restricted third country?' },
    { field: 'non_eu_component_cost_pct', question: 'What share of the component cost originates outside?' },
  ];
  await answer(page, body);
  await save(page, BE);
  await visit(page, '/readiness/results', { title: /readiness results|your readiness/i, h1: 'Your readiness results' });
  const cl3 = page.locator('[data-horizon-cl3]');
  await expect(cl3.getByRole('heading', { name: /Horizon Europe, Cluster 3/ })).toBeVisible();
  await expect(cl3).toContainText('at least three independent legal entities');
  await expect(cl3.getByRole('link', { name: /Cluster 3 calls that fit your profile/ })).toHaveAttribute('href', '/funding?programme=HORIZON&q=CL3&fit=1#results');
  const card = page.locator('[data-programme="EDIP"]');
  await expect(card.locator('[data-missing] > p')).toHaveText('1 answer is missing:');
  const note = card.locator('[data-not-asked-components]');
  await expect(note.locator('summary')).toHaveText(/Not applicable to software or services: 2 rules on components stay open/);
  await expect(note.locator('[data-skipped]')).toHaveCount(2);
});

test('the wizard asks the EEA-recipient question in step 5, lists the ANSSI qualifications in step 4, and words the Ukraine 35 % rule plainly', async ({ page }) => {
  await answer(page, fixture('assess-ua.json'));
  await save(page, { ...BE, offering: 'products', step: 3 });
  await visit(page, '/readiness?step=3', { title: /readiness check/i, h1: 'Readiness check' });
  await expect(group(page, /originate in Ukraine\?/)).toContainText('they do not count toward its 35 % limit');
  await page.goto('/readiness?step=4');
  const other = group(page, /Other certificates you hold/);
  await other.getByLabel(/ANSSI PASSI/).check();
  await expect(other.getByLabel(/ISO\/IEC 27001/)).toBeVisible();
  await page.goto('/readiness?step=5');
  await group(page, /defence-related products from other EEA states/).getByLabel('No', { exact: true }).check();
  const p = await stored(page);
  expect(p.supplier.held).toContain('PASSI');
  expect(p.supplier.answers.receives_eea_defence_products).toBe('no');
  // a wizard answer does not turn the company into a supplier: the results do not lead with the supply routes
  await page.goto('/readiness/results');
  await expect(page.locator('[data-supplier-routes]')).toHaveCount(0);
});

test('the roadmap follows the result: rules to settle, AQAP left out, the size of a range, the slowest step, no unverified issuer named', async ({ page }) => {
  const body = fixture('assess-ua.json');
  const plan = body.roadmap;
  const aqap = plan.steps.find((s: { code: string }) => s.code === 'REQ-AQAP2110');
  expect(aqap).toBeTruthy();
  aqap.sizeNote = 'The source quotes this range for a firm of 30 to 80 employees; you said 2,000 or more, so it may not fit your size, and the source gives no figure for yours.';
  aqap.issuers = [{ country: 'DE', name: 'Bundeswehr', url: null, notes: null, status: 'U' }];   // the seed's German row since WP-107
  plan.longest = 'REQ-NCAGE';
  plan.leftOut = [{ code: 'REQ-AQAP2310', name: 'AQAP 2310', text: 'AQAP 2310 is left out because you make software or services, not a physical product: it is a quality standard for the design, development and production of products, and only a supply contract that names it asks for it.' }];
  plan.settle = [{ programme: 'EDF', programmeName: 'European Defence Fund (EDF)', rule: 'EDF-CONTROL', title: 'Not controlled by a non-associated third country', outcome: 'conditional', reason: 'Guarantees approved by the Member State are needed.', sourceUrl: 'http://data.europa.eu/eli/reg/2021/697/oj' }];
  await answer(page, body);
  await save(page, { ...BE, offering: 'products' });
  await page.goto('/readiness/roadmap');
  await expect(page.locator('[data-roadmap-settle]')).toContainText('To settle first');
  await expect(page.locator('[data-settle="EDF-CONTROL"]')).toContainText('Guarantees approved by the Member State');
  await expect(page.locator('[data-roadmap-left-out]')).toContainText('AQAP 2310 is left out');
  await expect(page.locator('[data-totals="required"] [data-totals-longest]')).toContainText('NCAGE');
  const step = page.locator('[data-step="REQ-AQAP2110"]');
  await expect(step.locator('[data-step-size-note="REQ-AQAP2110"]')).toContainText('30 to 80 employees');
  await expect(step).not.toContainText('Bundeswehr');
  await expect(step).toContainText('Not verified in our sources');
});

test('a services company is asked for the CPV codes of what it sells', async ({ page }) => {
  await save(page, { ...BE, offering: 'software_services' });
  await visit(page, '/readiness/supplier', { title: /supplier profile/i, h1: /supplier profile/i });
  await expect(page.getByRole('group', { name: /CPV codes of what you sell/ })).toBeVisible();
  await expect(page.getByRole('group', { name: /CPV codes of what you make/ })).toHaveCount(0);
});
