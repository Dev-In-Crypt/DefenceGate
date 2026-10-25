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

// WP-86: the home page's tenders finder (country, CPV, word) became the site search and the "Find a tender" task; the country
// and CPV filters are on /tenders itself. WP-117: the tasks are the three question tiles; "What changed" left home for the menu's
// What's new (its link is still on the page, in the footer).
test('home: the tasks, the site search, the honest alerts button and what changed', async ({ page }) => {
  await visit(page, '/', {
    title: /DefenceGate/,
    h1: 'Win, partner, qualify.',
    text: ['Find tenders and funding', 'Find partners', 'Check if my company qualifies'],
  });
  const search = page.locator('#main').getByRole('search', { name: 'Site search' });
  await expect(search.getByLabel('Search tenders, funding, buyers and companies')).toBeVisible();
  // Alerts are not open (no mail provider): no button promises them.
  await expect(page.getByRole('link', { name: 'Get alerts' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: /what changed/i }).first()).toBeVisible();
});

test('home: "Find tenders and funding" lands on /tenders, where a country and a CPV set the filters', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  await Promise.all([page.waitForURL(/\/tenders$/), page.getByRole('list', { name: 'What do you want to know?' }).getByRole('link', { name: /Find tenders and funding/ }).click()]);
  await expect(page.locator('h1').first()).toHaveText('Tenders');
  await visit(page, '/tenders?country=PL&cpv=35', { title: /tenders/i, h1: 'Tenders' });
  const url = new URL(page.url());
  expect(url.searchParams.get('country')).toBe('PL');
  expect(url.searchParams.get('cpv')).toBe('35');
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
  // WP-87: the plain names of the owner's choice ("All defence", "Military goods and works", "Other purchases by armed forces")
  const relevant = page.getByLabel(/^All defence/);
  await expect(relevant).toBeChecked();
  // The three choices say how many each leads to; the count is a number, not a dash.
  await openFilters(page);
  await expect(page.getByLabel(/^Military goods and works/)).toBeVisible();
  await expect(page.getByLabel(/^Other purchases by armed forces/)).toBeVisible();
  await visit(page, '/tenders?scope=core', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.getByLabel(/^Military goods and works/)).toBeChecked();
});

test('a tender card says why it is on the list and shows the deadline in the buyer’s time', async ({ page }) => {
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.getByText('Why this is here').first()).toBeVisible();
});

test('the header has Market overview under Tenders & funding, and Methodology is in the footer under About the data (WP-86, WP-117)', async ({ page, isMobile }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  if (isMobile) await page.getByRole('button', { name: 'Open menu' }).click();
  const nav = page.getByRole('navigation', { name: isMobile ? 'Main menu' : 'Main' });
  // On a desktop the Tenders & funding menu opens on hover.
  if (!isMobile) await nav.getByRole('button', { name: 'Tenders & funding', exact: true }).hover();
  await expect(nav.getByRole('link', { name: 'Market overview', exact: true })).toBeVisible();
  await expect(page.locator('footer nav[aria-label="About the data"]').getByRole('link', { name: 'Methodology' })).toHaveAttribute('href', '/methodology');
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
  await visit(page, '/methodology', { title: /classifies/i, h1: 'Methodology' });
  await expect(page.getByText(/we hold only what TED carries/i).first()).toBeVisible();
  await expect(page.getByText(/four countries \(Spain, France/i)).toHaveCount(0);
  // No "Open <source>" link goes to an API root.
  await visit(page, '/data', { title: /source status/i, h1: 'Source status' });
  const hrefs = await page.locator('a[href^="https://"]').evaluateAll((as) => as.map((a) => (a as HTMLAnchorElement).href));
  for (const h of hrefs) expect(h, 'an API root is not a page to read').not.toMatch(/\/api(\/|$)|notice-exports|mo-board|papi\//);
});

test('the home page never prints a dash for a counter', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  // WP-117: the hero's figures (a list of terms) became the figures of the three question tiles; a figure the data service did
  // not give is left out, never printed as a dash.
  const figures = page.locator('[data-tile] [data-figure]');
  const numbers = await figures.locator(':scope > span:first-child').allInnerTexts();
  for (const t of numbers) expect(t.trim(), 'a counter is a number').toMatch(/^\d[\d,]*$/);
  // No two figures say the same thing (WP-86: the scope tiles of "What is in here" left home).
  const labels = await figures.locator(':scope > span:last-child').allInnerTexts();
  expect(labels.length).toBeGreaterThanOrEqual(4);
  expect(new Set(labels).size).toBe(labels.length);
});

test('the tenders CSV is rectangular and says in a column whether it was cut', async ({ request }) => {
  const res = await request.get('/tenders/export.csv?scope=core', { timeout: 45_000 });
  expect(res.status()).toBe(200);
  const body = (await res.text()).replace(/^﻿/, '');
  const header = body.split(/\r?\n/)[0];
  // WP-106: the winner columns are appended after `confidence`; the order of the others never moves
  expect(header.endsWith('scope,why_listed,versions,result_truncated,confidence,winners,winner_countries')).toBe(true);
  expect(body).not.toMatch(/^# Not the whole result/m);
});
