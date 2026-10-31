import { readFileSync } from 'node:fs';
import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-160 against the fake API (e2e/support/fake-api.mjs), with the plans on sale: contracts ending soon. Anonymous visitors and a free
 * account see the first 10 of 14 rows and what the rest needs; Pro the whole list without the CSV; Consultant (Team's CSV) the CSV, whose
 * rows say where each end date comes from. The state "no plan on sale" is the demo build's (e2e/wp160.spec.ts). Tagged @fake-api.
 * With WP160_SHOTS=<dir> each state is also saved as a screenshot there.
 */
const S = { pro: 'a'.repeat(43), none: 'b'.repeat(43), consultant: 'c'.repeat(43) } as const;
const WANT = { title: /Contracts ending soon/, h1: 'Contracts ending soon' };

async function signIn(context: BrowserContext, baseURL: string | undefined, session: string) {
  const host = new URL(baseURL ?? 'http://127.0.0.1').hostname;
  await context.addCookies([{ name: '__Host-dg_session', value: session, domain: host, path: '/', secure: true, httpOnly: true, sameSite: 'Lax' }]);
}

async function shot(page: Page, name: string) {
  const dir = process.env.WP160_SHOTS;
  if (!dir) return;
  await page.screenshot({ path: `${dir}/${name}-${page.viewportSize()?.width ?? 0}.png`, fullPage: true });
}

test('contracts ending soon: first 10 free, the list for Pro, the CSV for Team and Consultant', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  const rows = page.locator('[data-ending-list] [data-ending-row]');
  await visit(page, '/tenders/ending', WANT);
  await expect(rows).toHaveCount(10);
  await expect(page.locator('[data-full-state="signin"]')).toContainText('The first 10 of 14 contracts.');
  await expect(page.locator('[data-full-state="signin"]')).toContainText('sign in');
  await expect(rows.nth(0).locator('[data-basis]')).toHaveText('Stated end date');
  await expect(rows.nth(1).locator('[data-basis]')).toHaveText('Computed from start + duration');
  await expect(page.locator('[data-coverage]')).toContainText('Germany (9,613), France (1,423)');
  await shot(page, 'api-anonymous');

  await signIn(context, baseURL, S.none);
  await visit(page, '/tenders/ending', WANT);
  await expect(rows).toHaveCount(10);
  await expect(page.locator('[data-full-state="plan"]')).toContainText('part of Pro');
  await shot(page, 'api-free');

  await signIn(context, baseURL, S.pro);
  await visit(page, '/tenders/ending', WANT);
  await expect(rows).toHaveCount(14);
  await expect(page.locator('[data-csv-plan]')).toContainText('Team and Consultant');
  await expect(page.getByText('Download CSV')).toHaveCount(0);
  // the CSV route itself refuses Pro (back to the page), with the session sent as the browser would
  const refused = await page.request.get('/tenders/ending/export.csv', { maxRedirects: 0, headers: { cookie: `__Host-dg_session=${S.pro}` } });
  expect(refused.status()).toBe(303);
  expect(refused.headers()['location']).toBe('/tenders/ending');
  await shot(page, 'api-pro');

  await signIn(context, baseURL, S.consultant);
  await visit(page, '/tenders/ending', WANT);
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByText('Download CSV').click()]);
  expect(download.suggestedFilename()).toBe('defencegate-contracts-ending-12m-2026-10-12.csv');
  const text = readFileSync((await download.path())!, 'utf8');
  const [header, first, second] = text.replace(/^﻿/, '').split('\r\n');
  expect(header).toContain('contract_end,end_basis');
  expect(first).toContain(',stated end date,');
  expect(first).toContain('renewal options: up to 2 renewals');
  expect(second).toContain(',computed from start + duration,12 months,');
  await shot(page, 'api-consultant');
});
