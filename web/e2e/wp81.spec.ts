import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Locator, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-81 (owner decision of 22 October 2026): the sum of contract values per supplier, in a "Contract values" block collapsed by default,
 * on the supplier page and under each named winner of "who to approach" (the report). What this proves: the block is closed on arrival
 * (the sums are not shown), opens from the keyboard, then states the sum per currency, how many contracts state no value and the rules
 * (single winner, PLACSP adds none, each contract once, framework ceilings), and the period and sources it covers.
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
const DEMO = JSON.parse(readFileSync(path.join(__dirname, '..', 'lib', 'mock', 'demand.json'), 'utf8'));
type V = { byCurrency: { currency: string; amount: number; count: number }[]; of: number; withoutValue: number };
type W = { name: string; contracts: number; values: V };
const fmt = (n: number) => new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 }).format(n);

async function closedThenOpenedByKeyboard(block: Locator, page: Page) {
  const details = block.locator('details', { has: page.locator('summary', { hasText: 'Contract values' }) }).first();
  const summary = details.locator('summary');
  await expect(summary).toHaveText(/Contract values/);
  expect(await details.evaluate((d) => (d as HTMLDetailsElement).open)).toBe(false);
  await expect(details.locator('[data-value-totals]')).toBeHidden();
  await summary.focus();
  await page.keyboard.press('Enter');
  expect(await details.evaluate((d) => (d as HTMLDetailsElement).open)).toBe(true);
  await expect(details.locator('[data-value-totals]')).toBeVisible();
  return details;
}

test('who to approach: each named winner has its contract values, collapsed, per currency and with the unvalued count', async ({ page }) => {
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); },
    fixture('profile-es-sup-civil.json'));
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('assess-es-sup-civil.json')) }));
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  const s = page.locator('[data-report-section="r-approach"]');
  await expect(s.locator('[data-approach-winner]').first()).toBeVisible();
  const winners: W[] = DEMO.approach.winners;
  await expect(s.locator('[data-approach-winner] summary', { hasText: 'Contract values' })).toHaveCount(winners.length);

  const w = winners.find((x) => x.values.byCurrency.length > 0)!;
  const item = s.locator('[data-approach-winner]', { hasText: w.name }).first();
  const details = await closedThenOpenedByKeyboard(item, page);
  const v = w.values.byCurrency[0];
  await expect(details.locator('[data-value-sum]').first()).toHaveText(new RegExp(`^${v.currency} ${fmt(v.amount)} over ${v.count} contracts?`));
  await expect(details.locator('[data-value-without]')).toHaveText(`${w.values.withoutValue} of ${w.contracts} contracts state no value for this company alone.`);
  await expect(details).toContainText('Summed per currency, never converted');
  await expect(details).toContainText('names this one winner');
  await expect(details).toContainText('some may be framework ceilings');
  await expect(details).toContainText(`The contracts of this list: `);

  const bare = winners.find((x) => x.values.byCurrency.length === 0)!;
  const none = await closedThenOpenedByKeyboard(s.locator('[data-approach-winner]', { hasText: bare.name }).first(), page);
  await expect(none).toContainText('No value to sum.');
  await expect(page.getByText(/market share|top supplier|sole source|single point of failure/i)).toHaveCount(0);
});

test('a capped list links to every winner for these codes, a page at a time, each with its contract values', async ({ page }) => {
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); },
    fixture('profile-es-sup-civil.json'));
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('assess-es-sup-civil.json')) }));
  const sent: { page?: number; cpv?: string[]; countries?: string[] }[] = [];
  page.on('request', (r) => { if (r.url().endsWith('/api/readiness/winners')) sent.push(r.postDataJSON()); });
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  const all = page.locator('[data-approach-all] a');
  await expect(all).toHaveText(`All ${DEMO.total.winners} winners for these codes`);
  // the per-country lists that stop at ten link to their own country
  const es = DEMO.byCountry.find((c: { country: string; otherWinners: { winners: number } }) => c.otherWinners.winners > 0);
  await expect(page.locator(`[data-demand-country="${es.country}"] [data-demand-all] a`)).toHaveAttribute('href', `/readiness/supplier/winners?country=${es.country}`);
  await Promise.all([page.waitForURL(/\/readiness\/supplier\/winners$/), all.click()]);
  await expect(page.locator('h1')).toHaveText('Every winner for your codes');
  const rows = page.locator('[data-all-winners] [data-approach-winner]');
  await expect(rows).toHaveCount(20);                       // the demo answers in pages of 20
  await expect(rows.first().locator('summary', { hasText: 'Contract values' })).toBeVisible();
  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(page.getByText('Page 2 of')).toBeVisible();
  await expect(rows.first()).toContainText(DEMO.approach.winners[20].name);
  expect(sent.map((b) => b.page)).toEqual([1, 2]);
  expect(Object.keys(sent[0]).sort()).toEqual(['countries', 'cpv', 'page']);   // the codes and countries only, nothing else of the profile
});

test('a supplier page: contract values collapsed, every notice counted, not only the listed ones', async ({ page }) => {
  await visit(page, '/suppliers/1-demo-airframes-gmbh', { title: /Demo Airframes/i, h1: 'Demo Airframes GmbH' });
  const details = await closedThenOpenedByKeyboard(page.locator('main'), page);
  await expect(details.locator('[data-value-sum]')).toHaveText(['EUR 4,500,000 over 3 notices']);
  await expect(details.locator('[data-value-without]')).toHaveText('11 of 14 notices state no value for this company alone; 3 of them name several winners.');
  await expect(details).toContainText('All 14 notices naming it a winner, not only the ones listed below');
  await expect(details).toContainText('PLACSP');
  await expect(page.getByText(/market share|top supplier|sole source|single point of failure/i)).toHaveCount(0);
});
