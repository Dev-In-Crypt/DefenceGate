import { expect, test } from '@playwright/test';
import { pace, visit } from './helpers';

/**
 * The main routes: status, title, headline, key text, no console error, no horizontal scroll, no e-mail address.
 * The same file runs in the `desktop` and the `mobile-375` project.
 */


/** Below the `lg` breakpoint the filters sit behind a "Filters" button; open it so the text is on screen. */
async function openFilters(page: import('@playwright/test').Page) {
  const button = page.getByRole('button', { name: /^(Show|Hide) filters/ });
  if (await button.isVisible() && (await button.getAttribute('aria-expanded')) !== 'true') await button.click();
}

test('home: the finder, the honest alerts button and what is in here', async ({ page }) => {
  await visit(page, '/', {
    title: /DefenceGate/,
    h1: 'Defence and dual-use tenders and funding',
    text: ['What is in here', 'Find tenders'],
  });
  const finder = page.getByRole('search', { name: /find tenders by country/i });
  await expect(finder.getByLabel('Country of the buyer')).toBeVisible();
  await expect(finder.getByLabel('Product code (CPV)')).toBeVisible();
  // Alerts are not open (no mail provider): no button promises them.
  await expect(page.getByRole('link', { name: 'Get alerts' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: /what changed/i }).first()).toBeVisible();
});

test('home finder: a country and a CPV land on /tenders with the filters set', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Defence and dual-use tenders and funding' });
  const finder = page.getByRole('search', { name: /find tenders by country/i });
  await finder.getByLabel('Country of the buyer').selectOption('PL');
  await finder.getByLabel('Product code (CPV)').fill('35');
  await Promise.all([page.waitForURL(/\/tenders\?/), finder.getByRole('button', { name: 'Find tenders' }).click()]);
  const url = new URL(page.url());
  expect(url.pathname).toBe('/tenders');
  expect(url.searchParams.get('country')).toBe('PL');
  expect(url.searchParams.get('cpv')).toBe('35');
  await expect(page.locator('h1').first()).toHaveText('Tenders');
  await expect(page.locator('#results-heading')).toBeVisible();
  await pace(page);
});

test('/tenders with a country and a CPV filter', async ({ page }) => {
  await visit(page, '/tenders?country=PL&cpv=35', { title: /tenders/i, h1: 'Tenders' });
  // Either some results or the honest empty state; never a broken page.
  await expect(page.locator('#results-heading')).toBeVisible();
  await expect(page.getByLabel('CPV code')).toHaveValue('35');
});

test('/tenders: the Defence goods only switch travels in the URL and explains itself', async ({ page }) => {
  await visit(page, '/tenders?goods=defence', { title: /tenders/i, h1: 'Tenders' });
  const box = page.getByLabel('Defence goods only');
  await expect(box).toBeChecked();
  await openFilters(page);
  await expect(page.getByText(/say defence themselves/i).first()).toBeVisible();
});

test('a tender detail page', async ({ page }) => {
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  const first = page.locator('a[href^="/tenders/"]:not([href$=".csv"])').first();
  const href = await first.getAttribute('href');
  expect(href, 'a tender link on /tenders').toMatch(/^\/tenders\/\d+/);
  await visit(page, href!, { title: /DefenceGate/, h1: /.+/, text: ['Version history'] });
});

test('/funding', async ({ page }) => {
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i });
});

test('/buyers', async ({ page }) => {
  await visit(page, '/buyers', { title: /buyers/i, h1: /buyers/i });
});

test('/data', async ({ page }) => {
  await visit(page, '/data', { title: /source status/i, h1: 'Source status', text: ['Known gaps'] });
});

test('/terms', async ({ page }) => {
  await visit(page, '/terms', { title: /terms of use/i, h1: 'Terms of use' });
});

test('/alerts says what is not open and what works today', async ({ page }) => {
  await visit(page, '/alerts', {
    title: /alerts/i,
    h1: 'Alerts and saved searches',
    text: ['What works today, without an account'],
  });
  await expect(page.getByText(/not open yet/i).first()).toBeVisible();
});

test('the 404 page', async ({ page }) => {
  await visit(page, '/this-page-does-not-exist-e2e', {
    status: 404,
    title: /page not found/i,
    h1: 'This page is not in the directory',
  });
});

test('the tenders CSV downloads for the default scope and for closed notices, never as a 5xx', async ({ request }) => {
  for (const query of ['', '?status=closed']) {
    const res = await request.get(`/tenders/export.csv${query}`, { timeout: 45_000 });
    expect(res.status(), `export.csv${query}`).toBe(200);
    expect(res.headers()['content-type']).toContain('text/csv');
    expect(res.headers()['content-disposition']).toContain('attachment');
    const body = await res.text();
    const lines = body.replace(/^\uFEFF/, '').split(/\r?\n/).filter(Boolean);
    expect(lines[0].startsWith('id,notice_id,title,buyer,country')).toBe(true);
    // 2,000 rows, a marker row and the header at most.
    expect(lines.length).toBeLessThanOrEqual(2002);
    expect(body).not.toMatch(/[A-Z0-9._%+-]+@[A-Z0-9-]+\.[A-Z]{2,}/i);
  }
});

// ---- WP-20 (UX walk-throughs of 16 October 2026; owner decision on the default scope) ----

test('/tenders: the default scope is defence-relevant, with counts, and an explicit scope keeps its meaning', async ({ page }) => {
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  const relevant = page.getByLabel(/Defence-relevant \(core \+ supplies to defence buyers\)/);
  await expect(relevant).toBeChecked();
  // The three choices say how many each leads to; the count is a number, not a dash.
  await openFilters(page);
  await expect(page.getByText(/Core: the notice itself is defence/)).toBeVisible();
  await expect(page.getByText(/Supplies to defence buyers only/)).toBeVisible();
  await visit(page, '/tenders?scope=core', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.getByLabel(/Core: the notice itself is defence/)).toBeChecked();
});

test('a tender card says why it is on the list and shows the deadline in the buyer’s time', async ({ page }) => {
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.getByText('Why this is here').first()).toBeVisible();
});

test('the header has Market, and Methodology under Data', async ({ page, isMobile }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Defence and dual-use tenders and funding' });
  if (isMobile) await page.getByRole('button', { name: 'Open menu' }).click();
  const nav = page.getByRole('navigation', { name: isMobile ? 'Main menu' : 'Main' });
  await expect(nav.getByRole('link', { name: 'Market', exact: true })).toBeVisible();
  // On a desktop the Data menu opens on hover.
  if (!isMobile) await nav.getByRole('link', { name: 'Data', exact: true }).hover();
  await expect(nav.getByRole('link', { name: 'Methodology' })).toHaveCount(1);
});

test('/market: a year and a country can be chosen, and the country rows lead to the tenders', async ({ page }) => {
  await visit(page, '/market?year=2025&country=PL', { title: /market overview/i, h1: 'Market overview' });
  await expect(page.getByLabel('Year of publication')).toHaveValue('2025');
  // exact: the table under the filters is a region whose label also says "buyer country"
  await expect(page.getByLabel('Buyer country', { exact: true })).toHaveValue('PL');
  await visit(page, '/market', { title: /market overview/i, h1: 'Market overview' });
  const row = page.locator('a[href^="/tenders?country="]').first();
  await expect(row).toHaveAttribute('href', /status=all&scope=core/);
});

test('/data and /methodology say the same about the national portals and name Germany', async ({ page }) => {
  await visit(page, '/data', { title: /source status/i, h1: 'Source status', text: ['Using the data'] });
  await expect(page.getByText(/collected for \w+ countries only|collected for \w+ countries:/).first()).toBeVisible();
  await expect(page.getByText(/four countries only/i)).toHaveCount(0);
  await expect(page.getByText(/Germany, Italy and the Nordic/i)).toHaveCount(0);
  await expect(page.getByText(/Atom/).first()).toBeVisible();
  await visit(page, '/methodology', { title: /classifies/i, h1: /collect and classify/i });
  await expect(page.getByText(/we hold only what TED carries/i).first()).toBeVisible();
  await expect(page.getByText(/four countries \(Spain, France/i)).toHaveCount(0);
  // No "Open <source>" link goes to an API root.
  await visit(page, '/data', { title: /source status/i, h1: 'Source status' });
  const hrefs = await page.locator('a[href^="https://"]').evaluateAll((as) => as.map((a) => (a as HTMLAnchorElement).href));
  for (const h of hrefs) expect(h, 'an API root is not a page to read').not.toMatch(/\/api(\/|$)|notice-exports|mo-board|papi\//);
});

test('the home page never prints a dash for a counter', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Defence and dual-use tenders and funding' });
  const counters = page.getByRole('term').locator('xpath=following-sibling::*[1]');
  const texts = await counters.allInnerTexts();
  for (const t of texts) expect(t.trim(), 'a counter is a number or says it is not available').not.toBe('–');
  // The two scope tiles that say the same thing are not both shown.
  const tiles = await page.locator('#inside dt').allInnerTexts();
  expect(new Set(tiles).size).toBe(tiles.length);
});

test('the tenders CSV is rectangular and says in a column whether it was cut', async ({ request }) => {
  const res = await request.get('/tenders/export.csv?scope=core', { timeout: 45_000 });
  expect(res.status()).toBe(200);
  const body = (await res.text()).replace(/^﻿/, '');
  const header = body.split(/\r?\n/)[0];
  expect(header.endsWith('scope,why_listed,versions,result_truncated,confidence')).toBe(true);
  expect(body).not.toMatch(/^# Not the whole result/m);
});
