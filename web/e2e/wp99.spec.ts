import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-99 (persona round of 23 October 2026, D: funding and eligibility), on the demo build (lib/mock, NEXT_PUBLIC_DG_NOW 12 October 2026):
 * a French cyber start-up, a Ukrainian drone maker and a Belgian consultant. The readiness results lead to the Digital Europe, EIC and
 * national calls; the control and component questions keep Ukraine and the EEA EFTA states apart; a funding search can be subscribed to
 * (webcal and Atom) and its calendar keeps the search; the Ukraine partners table says what each coordinator's projects are, takes a
 * keyword and has pages; the organisation name box says it is the name and leads to the topic search.
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
const group = (page: Page, name: RegExp) => page.getByRole('group', { name });
const save = (page: Page, p: Record<string, unknown>) =>
  page.addInitScript((value) => { if (!sessionStorage.getItem('wp99')) { window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); sessionStorage.setItem('wp99', '1'); } }, p);
const stored = (page: Page) => page.evaluate(() => JSON.parse(window.localStorage.getItem('dg.profile.v1') ?? 'null'));

const UA = {
  version: 4, step: 1, updatedAt: '2026-10-23T10:00:00.000Z', name: '', sizeClass: 'small', country: 'UA', legalForm: 'legal_person',
  applicantKind: 'company_or_research', offering: 'products', topics: '', orgKind: 'company', headcount: 'lt50', inGroup: 'no', groupHeadcount: '',
  management: 'same', managementCountry: '', control: 'ua_eea_only', controlCountry: '', investor: '', uaOccupied: 'no', uaPartner: '', seapPartner: '',
  regime: 'military', componentPct: '20', componentBand: '', restricted: 'no', uaEeaComponents: 'yes', safeRole: 'contractor', statuses: {},
  classified: 'no', exportIntent: 'none',
};

test('the control and component questions keep Ukraine and the EEA EFTA states apart, and an old answer is asked again', async ({ page }) => {
  await save(page, UA);
  await visit(page, '/readiness?step=2', { title: /readiness check/i, h1: 'Readiness check' });
  const control = group(page, /controlled by a country or an entity outside the EU/);
  // a version 4 "only by Ukraine or an EEA EFTA state" without the country says neither: it is unanswered again
  await expect(control.getByRole('radio', { checked: true })).toHaveCount(0);
  await expect(control).toContainText('choose “Yes, but only by Ukraine”');
  await control.getByLabel('Yes, but only by Ukraine (for example Ukrainian owners)').check();
  await expect(group(page, /Which country controls your company/)).toHaveCount(0);
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(group(page, /originate in Ukraine\?/)).toBeVisible();
  await group(page, /originate in Ukraine\?/).getByLabel('Yes', { exact: true }).check();
  await group(page, /originate in an EEA EFTA state/).getByLabel('No', { exact: true }).check();
  const p = await stored(page);
  expect(p).toMatchObject({ version: 5, control: 'ua_eea_only', controlCountry: 'ua', uaComponents: 'yes', eeaComponents: 'no' });
  expect(p.uaEeaComponents).toBeUndefined();
});

test('the readiness results lead to the Digital Europe, EIC and national calls with the profile filter on', async ({ page }) => {
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('assess-ua.json')) }));
  await save(page, { ...UA, version: 5, country: 'FR', step: 6, control: 'no', uaComponents: 'no', eeaComponents: 'no' });
  await visit(page, '/readiness/results', { title: /readiness results|your readiness/i, h1: 'Your readiness results' });
  const other = page.locator('[data-other-funding]');
  await expect(other.getByRole('heading', { name: 'Digital Europe, the EIC and national calls' })).toBeVisible();
  await expect(other.locator('[data-other-funding-card]')).toHaveCount(3);
  await expect(other.locator('[data-other-funding-card="NATIONAL"]')).toContainText('National calls of France');
  await expect(other.locator('[data-other-funding-card="NATIONAL"]').getByRole('link')).toHaveAttribute('href', '/funding?programme=NATIONAL&country=FR&fit=1#results');
  await expect(other.getByRole('link', { name: 'See matching calls' })).toHaveAttribute('href', '/funding?fit=1#results');
});

test('a funding search can be subscribed to, and its calendar keeps the search', async ({ page, request }) => {
  await visit(page, '/funding?q=space&status=all', { title: /funding/i, h1: 'Funding' });
  const box = page.locator('[data-subscribe-funding]').first();
  await box.locator('summary').click();
  await expect(box.locator('[data-subscribe-webcal]')).toHaveAttribute('href', /^webcal:\/\/.+\/funding\.ics\?q=space&status=all$/);
  await expect(box.locator('[data-subscribe-atom]')).toHaveAttribute('href', '/funding.atom?q=space&status=all');
  await expect(page.getByRole('link', { name: 'Deadline calendar of this search' }).first()).toHaveAttribute('href', '/funding?q=space&status=all&view=calendar');
  const feed = await request.get('/funding.atom?q=space&status=all');
  expect(feed.status()).toBe(200);
  expect(feed.headers()['content-type']).toContain('application/atom+xml');
  const xml = await feed.text();
  expect(xml).toContain('<feed xmlns="http://www.w3.org/2005/Atom"');
  expect(xml).toContain('the search “space”');
  expect((await request.get('/funding.atom?nope=1')).status()).toBe(422);
  const ics = (await (await request.get('/funding.ics?status=all')).text()).replace(/\r\n /g, '');
  expect(ics).not.toContain('17:00');
});

test('the Ukraine partners table labels each coordinator, takes a keyword and keeps it in its links', async ({ page }) => {
  await visit(page, '/networks/ukraine-partners?programme=all', { title: /Ukrainian/, h1: 'Ukraine partners' });
  await expect(page.getByRole('columnheader', { name: 'Projects are' })).toBeVisible();
  await expect(page.locator('[data-group]').first()).toHaveText(/^(Defence|Dual-use|Civil)$/);
  await page.getByLabel('Project keyword').fill('alpha');
  await page.getByRole('button', { name: 'Apply' }).click();
  await expect(page).toHaveURL(/q=alpha/);
  await expect(page.locator('[data-keyword]')).toContainText('Only projects whose acronym or title has “alpha”');
  await expect(page.locator('[data-group]')).toHaveCount(1);
  await visit(page, '/networks/ukraine-partners?programme=all&q=nothingmatches', { title: /Ukrainian/, h1: 'Ukraine partners' });
  await expect(page.getByText(/No project started in or after \d+ matches/)).toBeVisible();
});

test('the organisation name box says it is the name and leads to the search by project topic', async ({ page }) => {
  await visit(page, '/organisations?q=a', { title: /Organisations|Companies/, h1: 'Companies' });
  await expect(page.getByLabel('Name of the organisation')).toHaveValue('a');
  const note = page.locator('[data-name-search]');
  await expect(note).toContainText('These are the organisations whose name has “a”');
  await expect(note.getByRole('link')).toHaveAttribute('href', /\/organisations\?topic=a/);
});
