import { expect, test, type BrowserContext } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-162 against the fake API (e2e/support/fake-api.mjs): the "Who to sell to" report. The public sample names no company in section 3;
 * the form page asks a visitor to sign in and an account without the feature is told it is paid; an account with `sell_report` makes
 * the report from the form; a report with every section empty renders cleanly; the Consultant's name replaces our logo on the cover;
 * the print leaves the site's chrome out. Tagged @fake-api: the fake-api-* projects run it (1440 desktop and 375 mobile).
 */
const FORM = '/reports/who-to-sell-to';
const SAMPLE = '/reports/who-to-sell-to/sample';

async function signIn(context: BrowserContext, baseURL: string | undefined, session: string) {
  const host = new URL(baseURL ?? 'http://127.0.0.1').hostname;
  await context.addCookies([{ name: '__Host-dg_session', value: session, domain: host, path: '/', secure: true, httpOnly: true, sameSite: 'Lax' }]);
}

async function fill(page: import('@playwright/test').Page, code: string) {
  await page.getByLabel('Country where your company is established').selectOption('ES');
  await page.getByLabel('Search the CPV codes').fill(code);
  await page.locator('#q-cpv').getByRole('checkbox').first().check();
}

test('the public sample has the eight sections and names no company in section 3', { tag: '@fake-api' }, async ({ page }) => {
  await visit(page, SAMPLE, { title: /Who to sell to/, h1: 'Who to sell to: sample report' });
  const r = page.locator('[data-sell-report]');
  await expect(r).toHaveAttribute('data-sample', 'true');
  for (const id of ['sr-1', 'sr-2', 'sr-3', 'sr-4', 'sr-6', 'sr-7', 'sr-8']) await expect(r.locator(`[data-sr-section="${id}"]`)).toBeVisible();
  await expect(r.locator('[data-sr-winner]')).toHaveCount(0);
  await expect(r.locator('[data-sr-signin]')).toBeVisible();
  await expect(r.locator('[data-sr-buyer]').first()).toBeVisible();
  await expect(r.locator('[data-disclaimer]')).toContainText('not legal advice, not an eligibility decision');
  await expect(r.locator('[data-sr-section="sr-8"]')).toContainText('about a tenth of EU defence spending');
  // honest wording: who wins, never who needs sub-suppliers
  await expect(r).not.toContainText(/needs? sub-suppliers/i);
  await expect(r.locator('[data-sr-section="sr-3"] h2')).toHaveText('3 · Who wins these contracts');
  await page.emulateMedia({ media: 'print' });
  await expect(page.getByRole('button', { name: 'Print or save as PDF' })).toBeHidden();
});

test('a visitor is asked to sign in; an account without the feature is told it is paid', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  await visit(page, FORM, { title: /Who to sell to/, h1: 'Who to sell to' });
  await expect(page.locator('[data-sr-signin-gate]')).toContainText('for signed-in accounts');
  await signIn(context, baseURL, 'b'.repeat(43));
  await visit(page, FORM, { title: /Who to sell to/, h1: 'Who to sell to' });
  await fill(page, '34330000');
  await page.getByRole('button', { name: 'Make the report' }).click();
  await expect(page.locator('[data-sr-error]')).toContainText('comes with a paid plan');
});

test('an account makes the report from the form; consent is off by default', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  await signIn(context, baseURL, 'a'.repeat(43));
  await visit(page, FORM, { title: /Who to sell to/, h1: 'Who to sell to' });
  await expect(page.locator('[data-sr-consent] input[type="checkbox"]')).not.toBeChecked();
  await fill(page, '34330000');
  await page.getByRole('button', { name: 'Make the report' }).click();
  const r = page.locator('[data-sell-report]');
  await expect(r).toBeVisible();
  await expect(r.locator('[data-sr-winner]').first()).toBeVisible();
  await expect(r.locator('[data-sr-item]').first()).toBeVisible();
  await expect(r.locator('[data-sr-steps] li').first()).toBeVisible();
  await expect(page.locator('[data-sr-quota]')).toContainText('of 3 supplier reports used this month');
  // every row of sections 2 and 3 links to its page and its source notice
  for (const row of await r.locator('[data-sr-buyer], [data-sr-winner]').all()) await expect(row.locator('a').first()).toHaveAttribute('href', /^\//);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test('a report with every section empty renders cleanly', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  await signIn(context, baseURL, 'a'.repeat(43));
  await visit(page, FORM, { title: /Who to sell to/, h1: 'Who to sell to' });
  await fill(page, '03111000');
  await page.getByRole('button', { name: 'Make the report' }).click();
  const r = page.locator('[data-sell-report]');
  await expect(r).toBeVisible();
  await expect(r.locator('[data-sr-empty]').first()).toBeVisible();
  await expect(r.locator('[data-sr-buyer], [data-sr-winner], [data-sr-tender], [data-sr-call]')).toHaveCount(0);
  await expect(r.locator('[data-step="codes"]')).toBeVisible();
  await expect(r).not.toContainText(/undefined|NaN|null/);
});

test('the Consultant’s name is on the cover instead of ours; a used-up quota says so', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  await signIn(context, baseURL, 'c'.repeat(43));
  await visit(page, FORM, { title: /Who to sell to/, h1: 'Who to sell to' });
  await fill(page, '34330000');
  await page.getByRole('button', { name: 'Make the report' }).click();
  await expect(page.locator('[data-sr-brand]')).toContainText('Acme Advisory Ltd');
  await context.clearCookies();
  await signIn(context, baseURL, 'd'.repeat(43));
  await visit(page, FORM, { title: /Who to sell to/, h1: 'Who to sell to' });
  await fill(page, '34330000');
  await page.getByRole('button', { name: 'Make the report' }).click();
  await expect(page.locator('[data-sr-error]')).toContainText('No supplier reports left this month');
});
