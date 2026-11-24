import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-174 (full QA of 24 November 2026, tenders and feeds) on the demo build: the sort box of a one-group list (B-7), a list of one
 * (F29), the tender card on a phone (B-13, B-14, F30), the results brought into view after "Apply filters" (B-10), the feed
 * stylesheet (F24) and the rows of the contracts ending soon (B-12). WP174_SHOTS=<folder> keeps the screenshots.
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 768;
const shot = async (page: Page, name: string) => {
  if (process.env.WP174_SHOTS) await page.screenshot({ path: path.join(process.env.WP174_SHOTS, `${name}-${isMobile(page) ? '375' : '1280'}.png`) });
};

test('a list of one group does not claim to put the military goods first; Everything does', async ({ page }) => {
  await visit(page, '/tenders?scope=supply', { title: /tenders/i, h1: 'Tenders' });
  const select = page.locator('select').filter({ has: page.locator('option', { hasText: 'Deadline, soonest first' }) }).first();
  await expect(select).toHaveValue('deadline-asc');
  expect(await select.locator('option').allTextContents()).not.toContain('Military goods and works first');
  await visit(page, '/tenders?scope=all', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.locator('select').filter({ has: page.locator('option', { hasText: 'Deadline, soonest first' }) }).first()).toHaveValue('core-first');
});

test('a list of one says "1 tender"', async ({ page }) => {
  await visit(page, '/tenders?q=machined+aluminium+housings', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.locator('#results-heading')).toHaveText('1 tender');
});

test('on a phone the card keeps the code name and the original title readable, and the notice id whole', async ({ page }) => {
  test.skip(!isMobile(page), 'phone only');
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  const card = page.locator('article').filter({ hasText: 'machined aluminium housings' }).first();
  await card.scrollIntoViewIfNeeded();
  await shot(page, 'tender-card-after');
  // the original title is not cut to a few letters beside its label, and the label is in the text face
  const original = card.locator('span[lang="nl"]').first();
  expect((await original.boundingBox())!.width).toBeGreaterThan(200);
  const label = card.getByText(/^Original title/).first();
  expect(await label.evaluate((e) => getComputedStyle(e).fontFamily)).not.toMatch(/mono/i);
  const wide = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(wide).toBeLessThanOrEqual(375);
});

test('after "Apply filters" the results are in view', async ({ page }) => {
  test.skip(isMobile(page), 'desktop: the filter column stays on screen while the page scrolls');
  await visit(page, '/tenders?status=all&size=50', { title: /tenders/i, h1: 'Tenders' });
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.getByRole('searchbox', { name: 'Search', exact: true }).fill('framework');
  await page.getByRole('button', { name: 'Apply filters' }).click();
  await expect(page).toHaveURL(/q=framework/);
  await expect.poll(async () => page.evaluate(() => document.getElementById('results')!.getBoundingClientRect().top)).toBeGreaterThanOrEqual(-1);
  const top = await page.evaluate(() => document.getElementById('results')!.getBoundingClientRect().top);
  expect(top).toBeLessThan(800);
  await shot(page, 'apply-after');
});

test('a feed opened in a browser has a stylesheet', async ({ page, request }) => {
  const feed = await request.get('/changes.atom');
  expect(feed.status()).toBe(200);
  expect((await feed.text()).split('\n')[1]).toBe('<?xml-stylesheet type="text/css" href="/feed.css"?>');
  const css = await request.get('/feed.css');
  expect(css.status()).toBe(200);
  expect(css.headers()['content-type']).toMatch(/text\/css/);
  // a browser gets XML and draws it with the stylesheet; a reader (above) the Atom type
  const opened = await page.goto('/changes.atom');
  expect(opened!.headers()['content-type']).toContain('application/xml');
  expect(await page.evaluate(() => getComputedStyle(document.documentElement, '::before').content)).toContain('news feed');
  await shot(page, 'feed-after');
});

test('a contract ending soon: the title is not underlined, the row shows the hover', async ({ page }) => {
  await visit(page, '/tenders/ending', { title: /Contracts ending soon/, h1: 'Contracts ending soon' });
  const row = page.locator('[data-ending-row]').first();
  test.skip((await row.count()) === 0, 'no contract in the demo window');
  const title = row.locator('a').first();
  expect(await title.evaluate((e) => getComputedStyle(e).textDecorationLine)).toBe('none');
  await row.hover();
  expect(await title.evaluate((e) => getComputedStyle(e).textDecorationLine)).toBe('none');
  await shot(page, 'ending-after');
});
