import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-53, readiness correctness in the browser: the executive-management answer starts empty (T5), a share outside 0 to 100 stops "Next"
 * and is named wherever it is treated as missing (T6), "Not applicable to us" is not "Met" (T4), and the partner questions (T21).
 * The verdicts come from `e2e/fixtures/assess-*.json`, which the backend generates from the same seed (see readiness.spec.ts).
 * The focus after "Mark as done" is in readiness.spec.ts, on the roadmap of the Ukrainian company.
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));

interface Posted { profile: Record<string, unknown>; statuses: Record<string, string> }

async function mockAssess(page: Page): Promise<Posted[]> {
  const posted: Posted[] = [];
  await page.route('**/api/readiness/assess', async (route) => {
    const body = route.request().postDataJSON() as Posted;
    posted.push(body);
    const answer = body.statuses['REQ-PIC'] === 'not_applicable' ? 'assess-ua-pic-na.json' : body.profile.country === 'ES' ? 'assess-es.json' : 'assess-ua.json';
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture(answer)) });
  });
  return posted;
}

const ES = {
  version: 2, step: 6, updatedAt: '2026-10-19T10:00:00.000Z', name: '', sizeClass: 'small', country: 'ES', legalForm: 'legal_person', applicantKind: 'company_or_research',
  management: 'same', managementCountry: '', control: 'no', uaOccupied: '', uaPartner: '', seapPartner: '', regime: 'military', componentPct: '10', restricted: 'no',
  uaEeaComponents: 'no', safeRole: 'contractor', statuses: {}, classified: 'yes', exportIntent: 'outside_eu',
};
const UA = { ...ES, country: 'UA', uaOccupied: 'no', regime: 'dual_use', componentPct: '20', classified: 'no' };

const save = (page: Page, p: Record<string, unknown> | null) =>
  page.addInitScript((value) => { if (value) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, p);
const group = (page: Page, name: RegExp | string) => page.getByRole('group', { name });
const card = (page: Page, name: string) => page.getByRole('article', { name });
const stored = (page: Page) => page.evaluate(() => JSON.parse(window.localStorage.getItem('dg.profile.v1') ?? '{}'));

// ---------------------------------------------------------------- T5

test('T5: no executive-management answer is ticked for the visitor', async ({ page }) => {
  await save(page, null);
  await visit(page, '/readiness?step=2', { title: /readiness check/i, h1: 'Readiness check' });
  const management = group(page, /executive management structures/);
  await expect(management.getByRole('radio')).toHaveCount(2);
  await expect(management.getByRole('radio', { checked: true })).toHaveCount(0);
  await management.getByLabel('In the country where the company is established').check();
  expect((await stored(page)).management).toBe('same');
});

test('T5: an empty answer is sent as unknown, and a block written before this change cannot claim it', async ({ page }) => {
  const posted = await mockAssess(page);
  await save(page, { ...ES, management: '' });
  await visit(page, '/readiness/results', { title: /readiness results|your readiness/i, h1: 'Your readiness results' });
  await expect(card(page, 'European Defence Fund (EDF)')).toBeVisible();
  expect(posted[posted.length - 1].profile.executive_management_country).toBeNull();

  // version 1 had the radio ticked from the start: its "same country" is not an answer
  const legacy: Record<string, unknown> = { ...ES, version: 1, managementSameCountry: true };
  delete legacy.management;
  const other = await page.context().newPage();
  const posted2 = await mockAssess(other);
  await other.addInitScript((value) => window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)), legacy);
  await other.goto('/readiness/results');
  await expect(card(other, 'European Defence Fund (EDF)')).toBeVisible();
  expect(posted2[posted2.length - 1].profile.executive_management_country).toBeNull();
  expect(posted2[posted2.length - 1].profile.country).toBe('ES');
  // and it is asked for again: the results name the question that has no answer
  await expect(card(other, 'European Defence Fund (EDF)')).toBeVisible();
  await other.close();
});

// ---------------------------------------------------------------- T6

test('T6: a share outside 0 to 100 stops Next with its reason, and "-5" is shown as typed, not turned into 5', async ({ page }) => {
  await save(page, null);
  await visit(page, '/readiness?step=3', { title: /readiness check/i, h1: 'Readiness check' });
  const share = page.getByLabel(/Share of component cost from outside the EU/);
  await share.fill('150');
  await expect(page.getByText('Enter a number from 0 to 100.')).toBeVisible();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Step 3 of 5: Products and regime')).toBeVisible();
  await expect(share).toBeFocused();
  await share.fill('-5');
  await expect(share).toHaveValue('-5');
  await expect(page.getByText('Enter a number from 0 to 100.')).toBeVisible();
  await share.fill('abc');
  await expect(page.getByText('Enter a number from 0 to 100.')).toBeVisible();
  await share.fill('100.5');
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Step 3 of 5: Products and regime')).toBeVisible();
  await share.fill('20');
  await expect(page.getByText('Enter a number from 0 to 100.')).toHaveCount(0);
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Step 4 of 5: Certifications held')).toBeVisible();
});

test('T6: another country chosen for the executive management but not named stops Next', async ({ page }) => {
  await save(page, null);
  await visit(page, '/readiness?step=2', { title: /readiness check/i, h1: 'Readiness check' });
  await group(page, /executive management structures/).getByLabel('In another country').check();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Choose the country of the executive management to go on.')).toBeVisible();
  await expect(page.getByText('Step 2 of 5: Ownership and control')).toBeVisible();
  await expect(page.getByLabel('Country of the executive management')).toBeFocused();
});

test('T6: an answer that is treated as missing says so on the results and on the roadmap, with the way to change it', async ({ page }) => {
  await mockAssess(page);
  await save(page, { ...ES, componentPct: '150' });
  await visit(page, '/readiness/results', { title: /readiness results|your readiness/i, h1: 'Your readiness results' });
  const note = page.getByRole('complementary').filter({ hasText: 'One of your answers is not used' });
  await expect(note).toContainText('The share of component cost you entered (“150”) is not a number from 0 to 100, so it is treated as not given.');
  await expect(note.getByRole('link', { name: 'Change it' })).toHaveAttribute('href', '/readiness?step=3');
  await visit(page, '/readiness/roadmap', { title: /roadmap/i, h1: 'Your roadmap' });
  await expect(page.getByRole('complementary').filter({ hasText: 'One of your answers is not used' })).toBeVisible();
  // a valid share is not mentioned
  await save(page, ES);
  await visit(page, '/readiness/results', { title: /readiness results|your readiness/i, h1: 'Your readiness results' });
  await expect(page.getByText('One of your answers is not used')).toHaveCount(0);
});

// ---------------------------------------------------------------- T4

test('T4: "Not applicable to us" for the PIC is not "Met": the rule is set apart and the roadmap has no PIC step', async ({ page }) => {
  const posted = await mockAssess(page);
  await save(page, { ...UA, statuses: { 'REQ-PIC': 'not_applicable' } });
  await visit(page, '/readiness?step=4', { title: /readiness check/i, h1: 'Readiness check' });
  await expect(page.getByText(/“Not applicable to us” leaves that rule out of your result; it does not count as holding it\./)).toBeVisible();
  await expect(page.getByLabel('PIC (Participant Identification Code)')).toHaveValue('not_applicable');

  await visit(page, '/readiness/results', { title: /readiness results|your readiness/i, h1: 'Your readiness results' });
  expect(posted[posted.length - 1]).toEqual(fixture('request-ua-pic-na.json'));
  const edf = card(page, 'European Defence Fund (EDF)');
  await edf.getByText(/\d+ rules? that do(es)? not apply to you/).click();
  const rule = edf.locator('li[data-rule="EDF-PIC"]');
  await expect(rule).toHaveAttribute('data-outcome', 'not_applicable');
  await expect(rule).toContainText('Does not apply');
  await expect(rule).toContainText('You answered “Not applicable to us” for this requirement');
  await expect(rule).not.toContainText('You have a PIC');
  for (const name of ['EDIP: Ukraine Support Instrument', 'European Defence Industry Programme (EDIP): the Programme']) {
    await expect(card(page, name).getByText('You have a PIC.')).toHaveCount(0);
  }
  await visit(page, '/readiness/roadmap', { title: /roadmap/i, h1: 'Your roadmap' });
  await expect(page.locator('li[data-step="REQ-PIC"]')).toHaveCount(0);
});

// ---------------------------------------------------------------- T21

test('T21: the partner questions are asked in step 2, kept in the browser, and the Ukrainian one is sent to the rules', async ({ page }) => {
  const posted = await mockAssess(page);
  await save(page, ES);
  await visit(page, '/readiness?step=2', { title: /readiness check/i, h1: 'Readiness check' });
  const ukraine = group(page, /legal entity established in Ukraine, with its executive management structure there/);
  const seap = group(page, /Does a SEAP \(structure for European armament programmes\) take part/);
  await expect(ukraine.getByRole('radio', { checked: true })).toHaveCount(0);
  await expect(seap.getByRole('radio', { checked: true })).toHaveCount(0);
  await ukraine.getByLabel('Yes', { exact: true }).check();
  await seap.getByLabel('No', { exact: true }).check();
  const p = await stored(page);
  expect([p.uaPartner, p.seapPartner]).toEqual(['yes', 'no']);

  // client-side navigation, so that the stored answers are not written again by the init script of the test
  await page.getByRole('button', { name: /^Go to step 5/ }).click();
  await page.getByRole('button', { name: 'See my results' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your readiness results');
  await expect(card(page, 'European Defence Fund (EDF)')).toBeVisible();
  const body = posted[posted.length - 1];
  expect(body.profile.ua_partner).toBe(true);
  expect(JSON.stringify(body)).not.toMatch(/seap/i);
});

test('T21: a Ukrainian company is not asked for a Ukrainian partner and a leftover answer is not sent', async ({ page }) => {
  const posted = await mockAssess(page);
  await save(page, { ...UA, uaPartner: 'yes' });
  await visit(page, '/readiness?step=2', { title: /readiness check/i, h1: 'Readiness check' });
  await expect(group(page, /legal entity established in Ukraine, with its executive management structure there/)).toHaveCount(0);
  await expect(group(page, /Does a SEAP/)).toBeVisible();
  await visit(page, '/readiness/results', { title: /readiness results|your readiness/i, h1: 'Your readiness results' });
  expect(posted[posted.length - 1].profile.ua_partner).toBeNull();
});
