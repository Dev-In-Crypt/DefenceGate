import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';
import { MAIN_NAV } from '../lib/nav';

/**
 * WP-139 (verification round 8, 25 October 2026): the phone menu's groups are all headings of one kind ("Check my company" was a
 * dark link among grey headings), its pages are links under them, hover and focus included; robots.txt keeps crawlers off every
 * address with a query string; /regulation's description says what the page holds.
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const HOME = { title: /DefenceGate/, h1: 'Win, partner, qualify.' };

test('on a phone every group of the menu is a heading of the same kind, with its pages as links under it', async ({ page }) => {
  test.skip(!isMobile(page), 'the phone menu');
  await visit(page, '/', HOME);
  await page.getByRole('button', { name: 'Open menu' }).click();
  const menu = page.getByRole('navigation', { name: 'Main menu' });
  const headings = menu.locator(':scope > div > p');
  await expect(headings).toHaveText(MAIN_NAV.map((n) => n.label));
  const colours = await headings.evaluateAll((els) => els.map((e) => [getComputedStyle(e).color, getComputedStyle(e).fontWeight].join()));
  expect(new Set(colours).size, 'one look for every heading').toBe(1);
  const check = menu.locator(':scope > div').filter({ has: page.locator('p', { hasText: 'Check my company' }) });
  const own = check.getByRole('link', { name: 'Check my company', exact: true });
  await expect(own).toHaveAttribute('href', '/check');
  // a link of the menu, hovered or focused, looks like the other links of the menu do then (never like a heading)
  const other = check.getByRole('link', { name: 'Requirements', exact: true });
  await own.hover();
  const hovered = await own.evaluate((e) => getComputedStyle(e).textDecorationLine);
  await other.hover();
  expect(await other.evaluate((e) => getComputedStyle(e).textDecorationLine)).toBe(hovered);
  await own.focus();
  await expect(own).toBeFocused();
  await own.click();
  await expect(page.locator('h1')).toHaveText('Check my company');
});

test('robots.txt keeps crawlers off filtered, sorted and paged addresses and leaves the plain pages open', async ({ request }) => {
  const res = await request.get('/robots.txt');
  expect(res.status()).toBe(200);
  const body = await res.text();
  expect(body).toMatch(/^Disallow: \/\*\?$/m);
  expect(body).toMatch(/^Allow: \/$/m);
  expect(body).toMatch(/^Allow: \/_next\/$/m);
  expect(body).not.toMatch(/^Disallow: \/suppliers$/m);
});

test('/regulation has a description that says which rules it tracks', async ({ page }) => {
  await visit(page, '/regulation', { title: /Regulatory tracker/, h1: 'Regulatory tracker' });
  const d = await page.locator('meta[name="description"]').getAttribute('content');
  expect(d?.length ?? 0).toBeGreaterThanOrEqual(110);
  expect(d).toContain('directive 2009/81');
});
