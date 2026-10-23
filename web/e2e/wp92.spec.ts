import { mkdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-92, on the demo build (lib/mock): a call page says what the call funds in the topic description's own commercial sentences,
 * with the way to the full text, on the first screen together with "Can I apply?" (phone included); a call without a summary keeps
 * the title, the keywords and "Read the topic description"; a card whose call document reserves the call for SMEs says so.
 * Screenshots go to WP92_SHOTS when it is set.
 */

const SHOTS = process.env.WP92_SHOTS;
const SSA = '/funding/4-edf-2026-space-situational-awareness-data-fusion';
const USI = '/funding/6-edip-2026-supply-chain-security-raw-materials';
const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));

async function quietApis(page: Page) {
  await page.route('**/api/fit/facts*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: {} }) }));
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('assess-ua.json')) }));
}

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: `${SHOTS}/${name}-${page.viewportSize()!.width}.png`, fullPage: false });
}

test('a call page says what it funds from the topic description, with the full text one tap away, above the fold', async ({ page }) => {
  await quietApis(page);
  await visit(page, SSA, { title: /Space situational awareness/, h1: /Space situational awareness/ });
  const funds = page.locator('[data-funds-summary]');
  await expect(funds).toContainText('What it funds: The objective is to strengthen the European space surveillance capability of Member States');
  await expect(funds).toContainText('From the topic description; see the full text');
  const link = funds.getByRole('link', { name: /see the full text/ });
  await expect(link).toHaveAttribute('href', /topic-details|edf-2026-da-space-ssadf/i);
  await expect(link).toHaveAttribute('target', '_blank');
  // the keywords line and its link are not repeated beside the summary
  await expect(page.getByRole('link', { name: /Read the topic description at/ })).toHaveCount(0);
  // the summary and "Can I apply?" are both on the first screen, on a phone too
  const fold = page.viewportSize()!.height;
  expect((await funds.boundingBox())!.y).toBeLessThan(fold);
  expect((await page.locator('[data-apply-summary]').boundingBox())!.y).toBeLessThan(fold);
  await shot(page, 'call-what-it-funds');
});

test('a call with no summary keeps the title, the keywords and the link to the topic description', async ({ page }) => {
  await quietApis(page);
  await visit(page, USI, { title: /Supply chain security/, h1: /Supply chain security/ });
  await expect(page.locator('[data-funds-summary]')).toHaveCount(0);
  const funds = page.locator('[data-what-it-funds]');
  await expect(funds).toContainText('The source’s keywords for this topic');
  await expect(funds.getByRole('link', { name: /Read the topic description at/ })).toBeVisible();
});

test('a card whose call document reserves the call for SMEs says SMEs only beside who may apply', async ({ page }) => {
  await visit(page, '/funding?status=all', { title: /funding/i, h1: 'Funding' });
  const card = page.locator('#results article').filter({ hasText: 'SME open call for disruptive technologies' });
  await expect(card.locator('[data-who="companies"]')).toHaveText('Companies can take part');
  await expect(card.locator('[data-sme-only]')).toHaveText('SMEs only');
  await expect(page.locator('#results article [data-sme-only]')).toHaveCount(1);
  await shot(page, 'funding-sme-only');
});
