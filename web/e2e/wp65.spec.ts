import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-65: the supplier profile (/readiness/supplier). What this proves: /readiness offers it without changing the funding wizard; the page
 * sends exactly the generated request of the civilian Spanish castings maker (`fixtures/request-es-sup-civil.json`, whose open questions the
 * backend counts: 19 before, 0 after) and the Spanish route card then asks nothing; errors are listed, announced and focused; a version 2
 * profile of the wizard is read with every answer and written back as version 3; the results link a question the page asks to its field;
 * the targets are at least 44 px high and nothing scrolls sideways at 375 px (`visit`).
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));

interface Posted { profile: Record<string, unknown>; statuses: Record<string, string> }

async function mockAssess(page: Page, answer: string): Promise<Posted[]> {
  const posted: Posted[] = [];
  await page.route('**/api/readiness/assess', async (route) => {
    posted.push(route.request().postDataJSON() as Posted);
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture(answer)) });
  });
  return posted;
}

const group = (page: Page, name: RegExp | string) => page.getByRole('group', { name });
const stored = (page: Page) => page.evaluate(() => JSON.parse(window.localStorage.getItem('dg.profile.v1') ?? 'null'));

const ES_V2 = {
  version: 2, step: 6, updatedAt: '2026-10-21T10:00:00.000Z', name: '', sizeClass: 'medium', country: 'ES', legalForm: 'legal_person', applicantKind: 'company_or_research',
  management: 'same', managementCountry: '', control: 'no', uaOccupied: '', uaPartner: '', seapPartner: '', regime: 'none', componentPct: '15', restricted: 'no',
  uaEeaComponents: 'no', safeRole: 'other_supplier', statuses: { 'REQ-ISO9001': 'held' }, classified: 'no', exportIntent: 'within_eu',
};

test('the readiness check offers the supplier profile and keeps the funding wizard', async ({ page }) => {
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check' });
  await expect(page.getByText('Step 1 of 5: Your company')).toBeVisible();
  await page.getByRole('link', { name: 'I make parts or materials and want to supply defence buyers' }).click();
  await expect(page).toHaveURL(/\/readiness\/supplier$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Supplier profile');
});

test('a civilian castings maker: errors first, then exactly the request of the fixture, and the Spanish route asks nothing', async ({ page }) => {
  const posted = await mockAssess(page, 'assess-es-sup-civil.json');
  await visit(page, '/readiness/supplier', { title: /supplier profile/i, h1: 'Supplier profile' });

  // saving an empty page: the problems are listed in an alert that takes focus, and each links to its field
  await page.getByRole('button', { name: 'Save and see my results' }).click();
  const alert = page.getByRole('alert').filter({ hasText: /needs? a change before saving/ });
  await expect(alert).toContainText('Choose the country where your company is established.');
  // WP-73 (QA MJ-2): no CPV code is required, since no rule reads them
  await expect(alert).not.toContainText('CPV');
  await expect(alert).toBeFocused();
  await alert.getByRole('link', { name: /Choose the country/ }).click();
  await expect(page.getByLabel('Country where your company is established')).toBeFocused();
  expect(posted).toEqual([]);

  await page.getByLabel('Country where your company is established').selectOption('ES');
  await page.getByLabel('Region (optional)').selectOption('ES-PV');
  await page.getByLabel('Size of the company (optional)').selectOption('medium');
  await page.getByLabel('NACE code of your main activity (optional)').fill('24-53');
  await group(page, /foreign investor own or control/).getByLabel('No', { exact: true }).check();

  // CPV codes: by code, by a word of the titles; the count is announced
  const search = page.getByLabel('Search the CPV codes');
  await search.fill('vehicles');
  await expect(page.getByRole('status').filter({ hasText: /codes match/ })).toBeVisible();
  await page.getByRole('checkbox', { name: /^34300000 Parts and accessories for vehicles/ }).check();
  for (const code of ['34100000', '35421000', '42600000']) {
    await search.fill(code);
    await page.getByRole('checkbox', { name: new RegExp(`^${code}`) }).check();
  }
  await search.fill('gun');
  await expect(page.getByRole('checkbox', { name: /Gunmetal/ })).toHaveCount(0);
  await expect(page.getByRole('list', { name: 'Your CPV codes' }).getByRole('listitem')).toHaveCount(4);

  await page.getByLabel('Casting').check();
  await page.getByLabel('Machining').check();
  await group(page, 'Certificates you hold').getByLabel('ISO 9001', { exact: true }).check();
  await page.getByLabel('ISO 9001: expiry month (optional)').fill('2027-05');
  await group(page, 'Certificates you hold').getByLabel('IATF 16949').check();
  await group(page, /US origin/).getByLabel('No', { exact: true }).check();
  await group(page, /access to classified information/).getByLabel('No', { exact: true }).check();

  // a bad NACE code: refused, with its reason (four CPV codes are fine since WP-73)
  await page.getByRole('button', { name: 'Save and see my results' }).click();
  await expect(alert).toContainText('Enter a NACE code such as 25.50 or C25.50, or leave it empty.');
  await expect(alert).not.toContainText('CPV');
  await expect(page.getByLabel('NACE code of your main activity (optional)')).toHaveAttribute('aria-invalid', 'true');
  await page.getByLabel('NACE code of your main activity (optional)').fill('24.53');
  await search.fill('44300000');
  await page.getByRole('checkbox', { name: /^44300000/ }).check();

  // the questions of the Spanish route: the follow-ups appear only after their "yes"
  const spain = page.getByRole('region', { name: 'Questions of the Spanish defence supplier route (optional)' });
  await expect(spain.getByRole('group', { name: /nine months/ })).toHaveCount(0);
  for (const q of [/PECAL certificate of your quality management system/, /target PECAL 2310/, /NCAGE code to register/, /specific defence use/,
    /NATO CONFIDENTIAL/, /NATO international competitive bidding/, /defence-related products from other EEA states/]) {
    await spain.getByRole('group', { name: q }).getByLabel('No', { exact: true }).check();
  }
  await page.getByRole('button', { name: 'Save and see my results' }).click();
  await expect(page).toHaveURL(/\/readiness\/results$/);
  await expect.poll(() => posted.length).toBeGreaterThan(0);
  expect(posted[posted.length - 1]).toEqual(fixture('request-es-sup-civil.json'));

  const card = page.getByRole('article', { name: 'Spanish defence supplier (MoD)' });
  // WP-73 (QA MJ-4): Spain's NCAGE without a justified need is a condition of the route, so the route is conditional, not "obtain"
  await expect(card).toHaveAttribute('data-verdict', 'conditional');
  // the list of missing answers ("1 answer is missing:"), not the verdict's words "an answer is missing"
  await expect(card.getByText(/\d+ answers? (is|are) missing/)).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Change my supplier profile' })).toBeVisible();
  const block = await stored(page);
  expect(block.version).toBe(3);
  expect(block.supplier.cpv).toHaveLength(5);
  expect(block.supplier.expiry).toEqual({ ISO9001: '2027-05' });
  expect(block.control).toBe('no');      // "no foreign investor" answered the wizard's empty control question
});

test('a version 2 profile of the wizard: every answer is read, the results link to the supplier page, the block becomes version 3', async ({ page }) => {
  await mockAssess(page, 'assess-es-auto.json');
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, ES_V2);
  await visit(page, '/readiness/results', { title: /readiness results/i, h1: 'Your readiness results' });
  const card = page.getByRole('article', { name: 'Spanish defence supplier (MoD)' });
  await expect(card.getByRole('link', { name: /current RID certificate/ })).toHaveAttribute('href', '/readiness/supplier#q-REQ-RID');
  await expect(card.getByRole('link', { name: /foreign investor hold shares/ })).toHaveAttribute('href', '/readiness/supplier#q-foreign_capital');
  await expect(card.locator('[data-not-asked]')).toHaveCount(0);

  await visit(page, '/readiness/supplier', { title: /supplier profile/i, h1: 'Supplier profile' });
  await expect(page.getByLabel('Country where your company is established')).toHaveValue('ES');
  await expect(page.getByLabel('Size of the company (optional)')).toHaveValue('medium');
  await expect(group(page, 'Certificates you hold').getByLabel('ISO 9001', { exact: true })).toBeChecked();
  await expect(group(page, /access to classified information/).getByLabel('No', { exact: true })).toBeChecked();
  expect((await stored(page)).version).toBe(2);           // reading does not write
  await group(page, 'Registrations you hold').getByLabel(/^RID/).check();
  const block = await stored(page);
  expect(block.version).toBe(3);
  expect(block.statuses).toEqual({ 'REQ-ISO9001': 'held', 'REQ-RID': 'held' });
  for (const [k, v] of Object.entries(ES_V2)) if (!['version', 'updatedAt', 'statuses'].includes(k)) expect(block[k], k).toEqual(v);
});

test('targets are at least 44 px high', async ({ page }) => {
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, ES_V2);
  await visit(page, '/readiness/supplier', { title: /supplier profile/i, h1: 'Supplier profile' });
  await page.getByLabel('Search the CPV codes').fill('35421');
  await page.getByRole('checkbox', { name: /^35421000/ }).check();
  const sizes = await page.locator('form[aria-label="Supplier profile"]').evaluate((form) =>
    [...form.querySelectorAll('label:has(input[type=checkbox]), label:has(input[type=radio]), button, select, input:not([type=checkbox]):not([type=radio])')]
      // a text field or select is the 44 px box around it (the control inside is the box less its border)
      .map((n) => ({ text: (n.textContent || n.getAttribute('aria-label') || n.id).trim().slice(0, 40), h: (n.matches('input, select') ? n.parentElement! : n).getBoundingClientRect().height }))
      .filter((x) => x.h > 0));
  expect(sizes.length).toBeGreaterThan(50);           // the radios of the Spanish questions, the checkboxes, the CPV list and its remove button
  expect(sizes.filter((x) => x.h < 44)).toEqual([]);
});
