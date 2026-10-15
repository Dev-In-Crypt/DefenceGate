import { expect, test } from '@playwright/test';
import { pace, visit } from './helpers';

/**
 * The main routes: status, title, headline, key text, no console error, no horizontal scroll, no e-mail address.
 * The same file runs in the `desktop` and the `mobile-375` project.
 */

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
