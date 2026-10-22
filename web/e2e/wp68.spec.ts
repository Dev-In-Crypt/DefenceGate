import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-68: the entry page /readiness/spain-automotive and the supplier page's German and dual-use questions. What this proves: the entry page
 * says who it is for, what it gives and what it is not, leads to the supplier profile, carries its metadata and is linked from /readiness,
 * the Readiness menu and the sitemap; on this demo build (no API) it shows no demand figure, since only a live answer may be shown. A German
 * supplier with classified work sees the German questions only after its "yes", and the page then sends exactly the generated request
 * (`fixtures/request-de-sup.json`); its results show the German and dual-use rules decided, with the specialist flag for "not sure".
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
const isMobile = (w: number | undefined) => (w ?? 1280) < 700;
const group = (page: Page, name: RegExp | string) => page.getByRole('group', { name });

test('the entry page: audience, what you get, what it is not, the button to start, metadata', async ({ page }) => {
  await visit(page, '/readiness/spain-automotive', { title: /Spain automotive suppliers/, h1: 'Supplier readiness: Spain automotive' });
  const main = page.locator('#main');
  await expect(main.getByText(/civilian manufacturers in Spain, such as automotive component suppliers/).first()).toBeVisible();
  for (const h of ['Who it is for', 'What you get', 'What it is not']) await expect(main.getByRole('heading', { name: h })).toBeVisible();
  await expect(main.getByRole('complementary', { name: 'Indicative, sources linked, not legal advice' })).toBeVisible();
  for (const t of ['A readiness check.', 'A roadmap.', 'A demand map.', 'A printable report']) await expect(main.getByText(t, { exact: false }).first()).toBeVisible();
  await expect(main.getByText('It does not show what prime contractors need from their suppliers', { exact: false })).toBeVisible();
  await expect(main.getByText('Meeting these requirements does not win a contract.', { exact: false })).toBeVisible();
  // a demo build has no API: no figure of the demand map is shown, none is taken from the demo data
  await expect(page.locator('[data-demand-sample]')).toHaveCount(0);
  await expect(main.getByRole('heading', { name: 'Live from the demand map' })).toHaveCount(0);
  // the short Spanish summary is marked as Spanish
  await expect(page.locator('[data-summary-es]')).toHaveAttribute('lang', 'es');
  await expect(page.locator('[data-summary-es]')).toContainText('no es asesoramiento jurídico');
  // metadata: title and description within the limits, canonical and Open Graph
  expect((await page.title()).length).toBeLessThanOrEqual(60);
  const description = await page.locator('meta[name="description"]').getAttribute('content');
  expect((description ?? '').length).toBeGreaterThan(50);
  expect((description ?? '').length).toBeLessThanOrEqual(160);
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', /\/readiness\/spain-automotive$/);
  await expect(page.locator('meta[property="og:url"]')).toHaveAttribute('content', /\/readiness\/spain-automotive$/);
  await expect(page.locator('meta[property="og:title"]')).toHaveAttribute('content', /Spain automotive/);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /index/);
  // the button starts the supplier profile
  await main.getByRole('link', { name: 'Start the supplier profile' }).first().click();
  await expect(page).toHaveURL(/\/readiness\/supplier$/);
});

test('the entry page is linked from /readiness, the Readiness menu and the sitemap', async ({ page, request }) => {
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check' });
  await expect(page.locator('#main').getByRole('link', { name: /civilian manufacturer in Spain/ })).toHaveAttribute('href', '/readiness/spain-automotive');
  await expect(page.locator('footer nav[aria-label="Readiness"] a[href="/readiness/spain-automotive"]')).toHaveText('Spain automotive');
  if (!isMobile(page.viewportSize()?.width)) {
    await expect(page.locator('header nav[aria-label="Main"] #sub-Readiness a[href="/readiness/spain-automotive"]')).toHaveText('Spain automotive');
  }
  const xml = await (await request.get('/sitemap.xml')).text();
  expect(xml).toContain('/readiness/spain-automotive</loc>');
});

test('a German supplier: the German questions follow its "yes", the page sends the generated request, the rules are decided', async ({ page }) => {
  const posted: unknown[] = [];
  await page.route('**/api/readiness/assess', async (route) => {
    posted.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('assess-de-sup.json')) });
  });
  await visit(page, '/readiness/supplier', { title: /supplier profile/i, h1: 'Supplier profile' });
  const germany = page.getByRole('region', { name: 'Questions of the German rules on classified contracts (optional)' });
  await expect(germany).toHaveCount(0);                                   // a company elsewhere is not asked
  await page.getByLabel('Country where your company is established').selectOption('DE');
  await expect(page.getByRole('region', { name: 'Questions of the Spanish defence supplier route (optional)' })).toHaveCount(0);
  await expect(germany.locator('[data-germany-waiting]')).toBeVisible();    // nothing to answer before classified access
  await expect(germany).toContainText('Ü1 to Ü3');
  await group(page, /foreign investor own or control/).getByLabel('No', { exact: true }).check();
  await group(page, 'Certificates you hold').getByLabel('ISO 9001', { exact: true }).check();
  await group(page, /US origin/).getByLabel('No', { exact: true }).check();
  await group(page, /defence-related products from other EEA states/).getByLabel('No', { exact: true }).check();
  await group(page, /access to classified information/).getByLabel('Yes', { exact: true }).check();

  // the follow-ups appear only after their "yes"
  await expect(group(page, /Geheimschutzbetreuung/)).toHaveCount(0);
  await group(page, /VS-VERTRAULICH or higher/).getByLabel('Yes', { exact: true }).check();
  await group(page, /Geheimschutzbetreuung/).getByLabel('No', { exact: true }).check();
  await group(page, /security officer/).getByLabel('Yes', { exact: true }).check();
  await group(page, /VS-NUR FÜR DEN DIENSTGEBRAUCH/).getByLabel('Yes', { exact: true }).check();
  await group(page, /commitment declaration/).getByLabel('Yes', { exact: true }).check();
  await group(page, /VS-NfD-Merkblatt/).getByLabel('No', { exact: true }).check();

  // exports: the dual-use question and the German export list, then the export authorisation once the item may be listed
  const exports = page.getByRole('region', { name: 'Exports and export control' });
  await expect(group(page, /Annex I of Regulation \(EU\) 2021\/821/)).toBeVisible();
  await group(page, /export, or plan to export, your product/).getByLabel('Yes, to other EU countries').check();
  await expect(group(page, /Annex I of Regulation \(EU\) 2021\/821/)).toHaveCount(0);       // only for exports outside the EU
  await expect(exports.locator('[data-dual-use-hidden]')).toBeVisible();
  await group(page, /export, or plan to export, your product/).getByLabel('Yes, outside the EU').check();
  await expect(group(page, /export authorisation for this item/)).toHaveCount(0);
  await group(page, /Annex I of Regulation \(EU\) 2021\/821/).getByLabel('I am not sure').check();
  await group(page, /Ausfuhrliste/).getByLabel('I am not sure').check();
  await group(page, /export authorisation for this item/).getByLabel('No', { exact: true }).check();

  await page.getByRole('button', { name: 'Save and see my results' }).click();
  await expect(page).toHaveURL(/\/readiness\/results$/);
  await expect.poll(() => posted.length).toBeGreaterThan(0);
  expect(posted[posted.length - 1]).toEqual(fixture('request-de-sup.json'));

  const general = page.locator('[data-programme="GENERAL"]');
  for (const [rule, outcome] of [['DE-SIBE', 'met'], ['DE-VSNFD', 'not_met'], ['DE-GHB-ADMISSION', 'conditional'], ['DE-EXPORT-BAFA', 'conditional'], ['EU-DUALUSE-EXPERT', 'conditional']]) {
    await expect(general.locator(`[data-rule="${rule}"]`)).toHaveAttribute('data-outcome', outcome);
  }
  await expect(page.locator('[data-consultant-flag="EU-DUALUSE-EXPERT"]')).toBeVisible();
  await expect(page.locator('[data-not-asked]')).toHaveCount(0);
});

test('a German question left open links back to its block on the supplier page', async ({ page }) => {
  // the same company before it answered: the generated answer of the engine without the page's German answers is not a fixture, so
  // the link is checked on the profile page itself: every block a link names exists for a German company with classified work
  await page.addInitScript(() => {
    if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify({ version: 3, step: 1, country: 'DE', classified: 'yes', statuses: {}, supplier: {} }));
  });
  await visit(page, '/readiness/supplier', { title: /supplier profile/i, h1: 'Supplier profile' });
  // the question ids are on their fieldsets (before WP-68 the radio questions had none, so `#q-foreign_capital` led nowhere)
  for (const id of ['sp-germany', 'sp-export', 'q-de_vs_vertraulich', 'q-de_vs_nfd', 'q-dualuse_annex_i', 'q-de_ausfuhrliste', 'q-foreign_capital']) {
    await expect(page.locator(`#${id}`)).toHaveCount(1);
  }
});
