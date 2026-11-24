import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-176 (QA of 24 November 2026: site-wide UX and the closed pages). Demo data; the signed-in header against the fake account API
 * (E2E_FAKE_ACCOUNTS). Screenshots go to WP176_SHOTS when it is set (the self-check).
 */
const SHOTS = process.env.WP176_SHOTS;
const HOME = { title: /DefenceGate/, h1: /Win, partner, qualify\./ };
const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;

async function shot(page: Page, name: string, full = false) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}-${page.viewportSize()?.width ?? 0}.png`), fullPage: full });
}

test.describe('demo data', () => {
  test.skip(!!process.env.E2E_FAKE_ACCOUNTS, 'the demo-data build');

  test('A-13: a small menu of the desktop bar closes on a click outside it', async ({ page }) => {
    test.skip(isMobile(page), 'the desktop bar');
    await visit(page, '/about', { title: /About/, h1: /.+/ });
    const nav = page.getByRole('navigation', { name: 'Main' });
    await nav.getByRole('button', { name: 'What’s new', exact: true }).click();
    await expect(page.locator('#sub-new')).toBeVisible();
    await page.mouse.move(5, 700);
    await page.locator('h1').click();
    await expect(page.locator('#sub-new')).toBeHidden();
  });

  test('A-14: at 1024 px the bar holds the four items and a search button, no menu button', async ({ page }) => {
    test.skip(isMobile(page), 'the desktop bar');
    await page.setViewportSize({ width: 1024, height: 800 });
    await visit(page, '/about', { title: /About/, h1: /.+/ });
    const nav = page.getByRole('navigation', { name: 'Main' });
    await expect(nav).toBeVisible();
    await expect(nav.locator(':scope > * > :first-child')).toHaveText(['Tenders & funding', 'Partners', 'Check my company', 'What’s new']);
    await expect(page.getByRole('button', { name: 'Open menu' })).toBeHidden();
    await expect(page.locator('header').getByRole('link', { name: 'Search', exact: true })).toHaveAttribute('href', '/search');
    const w = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(w).toBeLessThanOrEqual(0);
    await shot(page, 'header-1024');
  });

  test('A-15: the phone menu ends with About, Pricing, Methodology, Source status and Glossary', async ({ page }) => {
    test.skip(!isMobile(page), 'the phone menu');
    await visit(page, '/', HOME);
    await page.getByRole('button', { name: 'Open menu' }).click();
    const menu = page.getByRole('navigation', { name: 'Main menu' });
    for (const [label, href] of [['About DefenceGate', '/about'], ['Pricing', '/pricing'], ['Methodology', '/methodology'], ['Source status', '/data'], ['Glossary', '/glossary']]) {
      await expect(menu.getByRole('link', { name: label, exact: true })).toHaveAttribute('href', href);
    }
    await shot(page, 'phone-menu', true);
  });

  test('F25 and A-22: a closing-soon row is tinted on hover, its title never underlined and without the country first', async ({ page }) => {
    await visit(page, '/', HOME);
    const row = page.locator('[aria-labelledby="closing-tenders"] li').first();
    const link = row.locator('a').first();
    await link.hover();
    expect(await link.evaluate((e) => getComputedStyle(e).textDecorationLine)).toBe('none');
    await page.waitForTimeout(400);
    expect(await row.evaluate((e) => getComputedStyle(e).backgroundColor)).not.toBe('rgba(0, 0, 0, 0)');
    const titles = await page.locator('[aria-labelledby="closing-tenders"] li a span').allTextContents();
    expect(titles.length).toBeGreaterThan(0);
    for (const t of titles) expect(t, t).not.toMatch(/^(France|Germany|Poland|Spain|Italy|Belgium|Netherlands) [–-] /);
  });

  test('F-6/F26: a neutral chip has an edge in the light theme', async ({ page }) => {
    await visit(page, '/funding', { title: /Funding|funding/, h1: /.+/ });
    const tag = page.locator('.tag-neutral').first();
    await expect(tag).toBeVisible();
    expect(await tag.evaluate((e) => getComputedStyle(e).boxShadow)).toMatch(/inset/);
  });

  test('A-29: the footer of a short page sits at the bottom of the screen', async ({ page }) => {
    await page.setViewportSize({ width: isMobile(page) ? 375 : 1440, height: 1600 });
    await visit(page, '/unsubscribe', { title: /Stop e-mails/, h1: /Stop the weekly digest/ });
    const bottom = await page.locator('footer').last().evaluate((e) => e.getBoundingClientRect().bottom);
    expect(bottom).toBeGreaterThanOrEqual(1600 - 2);
    // A-16: the page is in its own breadcrumb
    await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('Stop the weekly digest');
  });

  test('A-5, A-32: robots.txt has no Host line; the home page names its Atom feed', async ({ page, request }) => {
    expect(await (await request.get('/robots.txt')).text()).not.toMatch(/^Host:/m);
    await visit(page, '/', HOME);
    await expect(page.locator('link[rel="alternate"][type="application/atom+xml"]')).toHaveAttribute('href', /\/changes\.atom$/);
  });

  test('A-17, F-12: a 404 has the 404 title and robots of every other 404', async ({ page }) => {
    for (const p of ['/requirements/no-such-requirement', '/reports/who-to-sell-to']) {
      const r = await page.goto(p);
      expect(r?.status(), p).toBe(404);
      await expect(page, p).toHaveTitle(/^Page not found/);
      await expect(page.locator('meta[name="robots"][content="noindex, follow"]').first(), p).toBeAttached();
      await expect(page.locator('meta[name="robots"][content*="nofollow"]'), p).toHaveCount(0);
    }
  });

  test('A-25, A-26: glossary terms are 44 px targets on a phone; the official sources link to them', async ({ page }) => {
    await visit(page, '/glossary', { title: /glossary/i, h1: 'Glossary' });
    await expect(page.locator('dd a[href="https://eur-lex.europa.eu/eli/dir/2009/81/oj"]').first()).toBeVisible();
    if (!isMobile(page)) return;
    await page.getByText('Jump to a term').click();
    const h = await page.locator('nav[aria-label="Terms"] li a').evaluateAll((els) => els.map((e) => Math.min(e.getBoundingClientRect().height, e.getBoundingClientRect().width)));
    expect(Math.min(...h)).toBeGreaterThanOrEqual(43.5);
  });

  test('screenshots of the changed pages (self-check)', async ({ page }) => {
    test.skip(!SHOTS, 'only for the self-check');
    for (const [p, name] of [['/pricing', 'pricing'], ['/', 'home'], ['/glossary', 'glossary'], ['/funding', 'funding'], ['/tenders', 'tenders'], ['/readiness', 'readiness']] as const) {
      await page.goto(p);
      await shot(page, name, true);
    }
    const buyer = await page.goto('/buyers').then(() => page.locator('a[href^="/buyers/"]').first().getAttribute('href'));
    if (buyer) { await page.goto(buyer); await page.locator('[data-buyer-cpv]').scrollIntoViewIfNeeded(); await shot(page, 'buyer-filters'); }
  });

  test('A-12: where the data runs no longer says a plaintext dump stays on the server', async ({ page }) => {
    await visit(page, '/data/sovereignty', { title: /Where the data runs/, h1: 'Where the data runs' });
    await expect(page.locator('main')).not.toContainText('plaintext');
    await shot(page, 'sovereignty');
  });
});

test.describe('signed in, against the fake account API', () => {
  test.skip(!process.env.E2E_FAKE_ACCOUNTS, 'needs E2E_FAKE_ACCOUNTS=1 and a site started with DG_API_URL pointing at e2e/support/fake-accounts.mjs');
  test.use({ ignoreHTTPSErrors: true });

  test('E-01: with a session the header says "My account" and leads to the account, not "Sign in"', async ({ page }) => {
    await page.goto('/signin');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill('team@example.test');
    await page.getByLabel('Password', { exact: true }).fill('right password here');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForURL(/\/app$/);
    await page.goto('/about');
    const header = page.locator('header').first();
    if (isMobile(page)) await page.getByRole('button', { name: 'Open menu' }).click();
    const mine = (isMobile(page) ? page.getByRole('navigation', { name: 'Main menu' }) : header).getByRole('link', { name: 'My account', exact: true });
    await expect(mine).toHaveAttribute('href', '/app');
    await expect(page.getByRole('link', { name: 'Sign in', exact: true })).toHaveCount(0);
    await shot(page, 'header-signed-in');
    for (const p of ['/app', '/app/billing', '/app/clients', '/app/following', '/app/settings']) {
      await page.goto(p);
      await shot(page, `cabinet${p.replaceAll('/', '-')}`, true);
    }
  });
});
