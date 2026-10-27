import { expect, test, type BrowserContext } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-152 against the fake API (e2e/support/fake-api.mjs, company 152001, report switch on): the supplier page links its company report;
 * the report asks a visitor to sign in, tells an account without the feature that it comes with a paid plan, and gives an account with
 * `company_report` the report: competitors, where it wins, its share and its EU project partners, ready to print (the site's header and
 * the print button are left out of the print). Tagged @fake-api: the fake-api-* projects run it.
 */
const SLUG = '152001-fake-defence-gmbh';
const REPORT = `/suppliers/${SLUG}/report`;
const TITLE = { title: /Company report/i, h1: 'Company report: Fake Defence GmbH' } as const;

/** The session cookie as the site sets it at sign-in (lib/account.ts): host-only, Secure, path /. */
async function signIn(context: BrowserContext, baseURL: string | undefined, session: string) {
  const host = new URL(baseURL ?? 'http://127.0.0.1').hostname;
  await context.addCookies([{ name: '__Host-dg_session', value: session, domain: host, path: '/', secure: true, httpOnly: true, sameSite: 'Lax' }]);
}

test('the supplier page links the company report when it is open', { tag: '@fake-api' }, async ({ page }) => {
  await visit(page, `/suppliers/${SLUG}`, { title: /Fake Defence GmbH/, h1: 'Fake Defence GmbH' });
  await expect(page.locator('[data-company-report-link]')).toHaveAttribute('href', REPORT);
});

test('a visitor is asked to sign in, an account without the feature is told it is paid', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  await visit(page, REPORT, TITLE);
  await expect(page.locator('[data-report-gate]')).toContainText('for signed-in accounts');
  await expect(page.locator('[data-company-report]')).toHaveCount(0);
  await signIn(context, baseURL, 'b'.repeat(43));
  await visit(page, REPORT, TITLE);
  await expect(page.locator('[data-report-plan]')).toContainText('comes with a paid plan');
  await expect(page.locator('[data-company-report]')).toHaveCount(0);
});

test('an account with the feature gets the report, ready to print', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  await signIn(context, baseURL, 'a'.repeat(43));
  await visit(page, REPORT, TITLE);
  await expect(page.locator('[data-company-report]')).toBeVisible();
  await expect(page.locator('section[aria-labelledby="competitors"] [data-competitor]')).toHaveCount(2);
  await expect(page.locator('[data-same-name]')).toHaveCount(1);
  await expect(page.locator('section[aria-labelledby="share"] [data-share]')).toHaveCount(2);
  await expect(page.locator('section[aria-labelledby="partners"] [data-partner]')).toContainText('Fake Research Institute');
  await expect(page.getByRole('button', { name: 'Print or save as PDF' })).toBeVisible();
  await expect(page.locator('[data-report-sources]')).toContainText('Open segment only');
  await page.emulateMedia({ media: 'print' });
  await expect(page.getByRole('button', { name: 'Print or save as PDF' })).toBeHidden();
  await expect(page.locator('h1', { hasText: 'Fake Defence GmbH' }).last()).toBeVisible();
});
