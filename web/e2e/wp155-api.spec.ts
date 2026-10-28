import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-155 against the fake API (e2e/support/fake-api.mjs), with the plans on sale: the owner's plan split as the site shows it. The
 * supplier page names five competitors and links the full list, which needs a sign-in and a plan; the company report counts against
 * the plan (a quota refusal says when it renews) and links the sample report, which opens for everyone; a Consultant's name is printed
 * on it; the signals show anonymous visitors no small company's row and say so, Pro the full list without the CSV, Consultant the CSV;
 * the consortium gap analysis is Team and Consultant. The state "no plan on sale" is the demo build's (wp152, wp154 and the gap page
 * specs). Tagged @fake-api. With WP155_SHOTS=<dir> each state is also saved as a screenshot there.
 */
const PRIME = '155001-fake-prime-sa';
const OTHER = '152001-fake-defence-gmbh';
const S = { pro: 'a'.repeat(43), none: 'b'.repeat(43), consultant: 'c'.repeat(43), spent: 'd'.repeat(43) } as const;

async function signIn(context: BrowserContext, baseURL: string | undefined, session: string) {
  const host = new URL(baseURL ?? 'http://127.0.0.1').hostname;
  await context.addCookies([{ name: '__Host-dg_session', value: session, domain: host, path: '/', secure: true, httpOnly: true, sameSite: 'Lax' }]);
}

async function shot(page: Page, name: string) {
  const dir = process.env.WP155_SHOTS;
  if (!dir) return;
  const w = page.viewportSize()?.width ?? 1280;
  await page.screenshot({ path: `${dir}/${name}-${w}.png`, fullPage: true });
}

test('competitors: five on the supplier page, the full list for a plan that has it', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  await visit(page, `/suppliers/${PRIME}`, { title: /Fake Prime SA/, h1: 'Fake Prime SA' });
  await expect(page.locator('section[aria-labelledby="competitors"] [data-competitor]')).toHaveCount(5);
  await expect(page.locator('[data-competitors-all]')).toHaveAttribute('href', `/suppliers/${PRIME}/competitors`);
  await shot(page, 'supplier-free');
  const all = `/suppliers/${PRIME}/competitors`;
  const want = { title: /Competitors/, h1: 'Competitors of Fake Prime SA' };
  await visit(page, all, want);
  await expect(page.locator('[data-competitors-gate]')).toContainText('for signed-in accounts');
  await expect(page.locator('[data-competitor]')).toHaveCount(5);
  await shot(page, 'competitors-anonymous');
  await signIn(context, baseURL, S.none);
  await visit(page, all, want);
  await expect(page.locator('[data-competitors-plan]')).toContainText('Pro, Team and Consultant');
  await expect(page.locator('[data-competitor]')).toHaveCount(5);
  await shot(page, 'competitors-free');
  await signIn(context, baseURL, S.pro);
  await visit(page, all, want);
  await expect(page.locator('[data-competitors-gate]')).toHaveCount(0);
  await expect(page.locator('[data-competitor]')).toHaveCount(8);
  await shot(page, 'competitors-pro');
});

test('the company report: the sample for everyone, the paywall links it, the count and its refusal', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  const title = { title: /Company report/i, h1: 'Company report: Fake Prime SA' };
  await visit(page, `/suppliers/${PRIME}/report`, title);                       // the sample, signed out
  await expect(page.locator('[data-company-report]')).toBeVisible();
  await expect(page.locator('[data-report-quota-line]')).toContainText('A sample report');
  await shot(page, 'report-sample-anonymous');
  await visit(page, `/suppliers/${OTHER}/report`, { title: /Company report/i, h1: 'Company report: Fake Defence GmbH' });
  await expect(page.locator('[data-report-gate]')).toContainText('for signed-in accounts');
  await expect(page.locator('[data-sample-link]')).toHaveAttribute('href', `/suppliers/${PRIME}/report`);
  await shot(page, 'report-gate-anonymous');
  await signIn(context, baseURL, S.none);
  await visit(page, `/suppliers/${OTHER}/report`, { title: /Company report/i, h1: 'Company report: Fake Defence GmbH' });
  await expect(page.locator('[data-report-plan]')).toContainText('comes with a paid plan');
  await expect(page.locator('[data-sample-link]')).toBeVisible();
  await signIn(context, baseURL, S.pro);
  await visit(page, `/suppliers/${OTHER}/report`, { title: /Company report/i, h1: 'Company report: Fake Defence GmbH' });
  await expect(page.locator('[data-report-quota-line]')).toHaveText('1 of 3 company reports this month opened; the count starts again on 1 Nov 2026.');
  await expect(page.locator('[data-report-name]')).toHaveCount(0);
  await shot(page, 'report-pro');
  await signIn(context, baseURL, S.spent);
  await visit(page, `/suppliers/${OTHER}/report`, { title: /Company report/i, h1: 'Company report: Fake Defence GmbH' });
  await expect(page.locator('[data-report-quota]')).toContainText('No company reports left this month: 3 of 3 opened; the count starts again on 2026-11-01 (UTC)');
  await expect(page.locator('[data-company-report]')).toHaveCount(0);
  await shot(page, 'report-quota-used');
});

test('a Consultant\'s own name is printed in the report head, as text', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  await signIn(context, baseURL, S.consultant);
  await visit(page, `/suppliers/${OTHER}/report`, { title: /Company report/i, h1: 'Company report: Fake Defence GmbH' });
  await expect(page.locator('[data-report-quota-line]')).toHaveCount(0);                   // no limit on Consultant
  await expect(page.locator('[data-report-name-screen]')).toContainText('Acme Advisory Ltd');
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('[data-report-name]')).toHaveText('Acme Advisory Ltd');
  await shot(page, 'report-consultant-print');
});

test('signals: no small company among the anonymous rows, the full list for Pro, the CSV for Consultant', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  const want = { title: /Company signals/, h1: 'Company signals' };
  const rows = page.locator('[data-signal-list="growing"] [data-signal-row]');
  await visit(page, '/signals', want);
  await expect(rows).toHaveCount(1);
  await expect(page.locator('[data-first-rows]')).toHaveText('1 of 14 companies shown; sign in for the rest. Rows of companies with fewer than 10 awarded procurements in three years are shown only after sign-in.');
  await expect(page.getByText('Small Company')).toHaveCount(0);
  await shot(page, 'signals-anonymous');
  await signIn(context, baseURL, S.none);
  await visit(page, '/signals', want);
  await expect(rows).toHaveCount(3);
  await expect(page.locator('[data-full-state="plan"]')).toContainText('The first 3 of 14 companies.');
  await shot(page, 'signals-free');
  await signIn(context, baseURL, S.pro);
  await visit(page, '/signals', want);
  await expect(rows).toHaveCount(14);
  await expect(page.locator('[data-csv-plan]')).toContainText('Team and Consultant');
  await expect(page.getByText('Download CSV')).toHaveCount(0);
  await shot(page, 'signals-pro');
  await signIn(context, baseURL, S.consultant);
  await visit(page, '/signals', want);
  await expect(page.getByText('Download CSV')).toBeVisible();
  await shot(page, 'signals-consultant');
});

test('the consortium gap analysis is Team and Consultant once the plans are on sale', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  const want = { title: /partner country/i, h1: 'Consortium gaps' };
  await visit(page, '/networks/consortium-gaps', want);
  await expect(page.locator('[data-gaps-gate]')).toContainText('sign in');
  await shot(page, 'gaps-anonymous');
  await signIn(context, baseURL, S.pro);
  await visit(page, '/networks/consortium-gaps', want);
  await expect(page.locator('[data-gaps-gate]')).toContainText('Team and Consultant plans');
  await signIn(context, baseURL, S.consultant);
  await visit(page, '/networks/consortium-gaps', want);
  await expect(page.locator('[data-gaps-gate]')).toHaveCount(0);
  await expect(page.locator('form[aria-label="Choose the area and the country"]')).toBeVisible();
  await shot(page, 'gaps-consultant');
});
