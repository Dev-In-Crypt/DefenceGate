import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-116 (coverage audit of 24 October 2026, site): CSV byte-order mark on all four exports, the 404 title of an unknown
 * company group and of a week outside the archive, the market's out-of-range year, the consortium gaps' unknown programme,
 * the readiness forms without JavaScript, the list's scroll position after Back, the sign-in return path, and one redirect
 * status (307) for a page past the end of every list. At 1440 px (desktop project) and 375 px (mobile-375).
 */

test.beforeEach(async ({ page }, info) => {
  if (info.project.name === 'desktop') await page.setViewportSize({ width: 1440, height: 900 });
});

const EXPORTS = ['/tenders/export.csv', '/funding/export.csv', '/market/export.csv', '/suppliers/1-demo-airframes-gmbh/contracts.csv'];

for (const path of EXPORTS) {
  test(`item 1: ${path} starts with the UTF-8 byte-order mark, once, then the header`, async ({ request }) => {
    const res = await request.get(path, { timeout: 45_000 });
    expect(res.status()).toBe(200);
    expect(res.headers()['content-type']).toBe('text/csv; charset=utf-8');
    // the bytes, not res.text(): a UTF-8 decoder strips the mark (the audit's bom=false)
    const body = await res.body();
    expect([...body.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
    expect([...body.subarray(3, 6)]).not.toEqual([0xef, 0xbb, 0xbf]);
    const text = body.subarray(3).toString('utf8');
    expect(text).toMatch(/^[a-z_]+,[a-z_]+/);
    expect(text).not.toContain('�');
  });
}

test('item 2: an unknown company group and a week outside the archive are titled Page not found', async ({ page }) => {
  await visit(page, '/suppliers?group=zzz', { status: 404, title: /^Page not found · DefenceGate$/, h1: 'This page is not in the directory' });
  await visit(page, '/changes?week=2026-W01', { status: 404, title: /^Page not found · DefenceGate$/, h1: 'This page is not in the directory' });
  // a known group and a week of the archive keep their own titles
  await visit(page, '/suppliers?group=demo', { title: /supplier map/i, h1: 'Companies' });
  await visit(page, '/changes?week=2026-W40', { title: /What changed/, h1: /changed/i });
});

test('item 3: a market year outside the data is said, as the calendar says a month outside it', async ({ page }) => {
  const thisYear = new Date().getUTCFullYear();
  for (const y of ['2019', '2099']) {
    await visit(page, `/market?year=${y}`, { title: /Market/, h1: 'Market overview',
      text: [`The market covers 2021 to ${thisYear}. ${y} is outside it, so the last 12 months are shown.`] });
  }
  await visit(page, '/market?year=abc', { title: /Market/, h1: 'Market overview', text: [/Ignored filter: year=abc/] });
  await visit(page, '/market?year=2025', { title: /Market/, h1: 'Market overview' });
  await expect(page.getByText(/is outside it|Ignored filter: year/)).toHaveCount(0);
});

test('item 4: an unknown programme of the consortium gaps falls back to the EDF and says so', async ({ page }) => {
  await visit(page, '/networks/consortium-gaps?programme=ZZZ', { title: /Repeat participants/, h1: 'Consortium gaps',
    text: ['Unknown programme ZZZ: the European Defence Fund is shown.', 'Area and result'] });
  await expect(page.getByText(/too broad/)).toHaveCount(0);
  await visit(page, '/networks/consortium-gaps?programme=edf', { title: /Repeat participants/, h1: 'Consortium gaps', text: ['Area and result'] });
  await expect(page.getByText(/Unknown programme/)).toHaveCount(0);
});

test.describe('item 5: without JavaScript', () => {
  test.use({ javaScriptEnabled: false });
  for (const path of ['/readiness/supplier', '/readiness']) {
    test(`${path} says the form needs JavaScript instead of loading forever`, async ({ page }) => {
      await page.goto(path);
      await expect(page.locator('[data-noscript-notice]')).toBeVisible();
      await expect(page.locator('[data-noscript-notice]')).toContainText('This form needs JavaScript');
      await expect(page.getByText('Loading your saved answers from this browser…')).toBeHidden();
    });
  }
});

test('item 5: with JavaScript the notice is not shown and the form is', async ({ page }) => {
  await page.goto('/readiness/supplier');
  await expect(page.locator('main form').first()).toBeVisible();
  await expect(page.getByText('This form needs JavaScript')).toBeHidden();
  await expect(page.getByText('Loading your saved answers from this browser…')).toHaveCount(0);
});

/** Scroll the list, open the first tender, come back: the position must be where it was. */
async function backKeepsScroll(page: Page, list: string) {
  await page.goto(list, { waitUntil: 'load' });
  const want = await page.evaluate(() => {
    const y = Math.min(1200, document.documentElement.scrollHeight - innerHeight - 10);
    window.scrollTo(0, y);
    return Math.round(scrollY);
  });
  expect(want).toBeGreaterThan(300);
  await page.waitForTimeout(300);
  // a tender in view at that position
  const href = await page.evaluate(() => [...document.querySelectorAll<HTMLAnchorElement>('main a[href^="/tenders/"]')]
    .find((a) => /^\/tenders\/\d+/.test(a.getAttribute('href') ?? '') && a.getBoundingClientRect().top > 80 && a.getBoundingClientRect().bottom < innerHeight - 20)
    ?.getAttribute('href') ?? null);
  expect(href).not.toBeNull();
  await Promise.all([page.waitForURL((u) => /^\/tenders\/\d+/.test(u.pathname)), page.locator(`main a[href="${href}"]`).first().click()]);
  await expect(page.locator('h1').first()).toBeVisible();
  await page.goBack({ waitUntil: 'load' });
  await expect(page).toHaveURL(new RegExp(`${list.replace(/[?]/g, '\\?')}$`));
  await expect.poll(() => page.evaluate(() => Math.round(scrollY)), { timeout: 5_000 }).toBeGreaterThan(want - 40);
  expect(await page.evaluate(() => Math.round(scrollY))).toBeLessThan(want + 40);
}

test('item 6: Back from a tender returns to the same place in the list (client navigation, prefetch on)', async ({ page }) => {
  await backKeepsScroll(page, '/tenders?status=all&page=2');
});

test('item 6: Back from a tender returns to the same place in the list (prefetch and client data blocked)', async ({ page }) => {
  // as the audit measured: every RSC request fails, so each link is a full page load
  await page.route((u) => u.search.includes('_rsc='), (r) => r.abort());
  await backKeepsScroll(page, '/tenders?status=all&page=2');
});

test('item 7: an /app page asked without a session goes to sign-in with the page to return to', async ({ page, request }) => {
  await page.goto('/app/shortlist');
  await expect(page).toHaveURL(/\/signin\?next=%2Fapp%2Fshortlist$/);
  await expect(page).toHaveTitle(/Sign in/);
  await page.goto('/app');
  await expect(page).toHaveURL(/\/signin$/);
  // the query of the page is kept
  const q = await request.get('/app/searches?tab=2', { maxRedirects: 0 });
  expect(q.status()).toBe(307);
  expect(q.headers().location).toBe('/signin?next=%2Fapp%2Fsearches%3Ftab%3D2');
  // a forwarded-path header sent by the visitor is replaced by the middleware's own
  const spoof = await request.get('/app/shortlist', { maxRedirects: 0, headers: { 'x-dg-path': '//evil.example/app' } });
  expect(spoof.headers().location).toBe('/signin?next=%2Fapp%2Fshortlist');
});

test('item 7: a return path that is not an /app page of this site is dropped (no open redirect)', async ({ request }) => {
  for (const bad of ['//evil.example', 'https://evil.example/app', '/app//evil.example', '/\\evil.example', '/tenders', '/app/%2e%2e/x']) {
    const r = await request.get(`/auth/expired?next=${encodeURIComponent(bad)}`, { maxRedirects: 0 });
    expect(r.status(), bad).toBe(307);
    expect(r.headers().location, bad).toBe('/signin');
  }
  const ok = await request.get(`/auth/expired?next=${encodeURIComponent('/app/following')}`, { maxRedirects: 0 });
  expect(ok.headers().location).toBe('/signin?next=%2Fapp%2Ffollowing');
  // the sign-in page answers as without one (accounts are closed in the demo, so it has no form; lib/safe-url.check.ts covers the rest)
  const page = await request.get(`/signin?next=${encodeURIComponent('//evil.example')}`);
  expect(page.status()).toBe(200);
  expect(await page.text()).not.toContain('name="next"');
});

test('item 8: a page past the end of every list answers 307 (temporary), never 308', async ({ request }) => {
  for (const list of ['/tenders', '/buyers', '/funding', '/calendar', '/changes', '/suppliers', '/organisations']) {
    const r = await request.get(`${list}?page=99`, { maxRedirects: 0 });
    expect(r.status(), list).not.toBe(308);
    if (['/tenders', '/buyers', '/funding', '/calendar', '/changes'].includes(list)) {
      expect(r.status(), list).toBe(307);
      expect(r.headers().location, list).toMatch(new RegExp(`^${list}(\\?|$)`));
    }
  }
});
