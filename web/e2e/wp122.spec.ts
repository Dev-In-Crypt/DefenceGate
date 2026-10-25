import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-122 (docs/verification/home/wp122-selfcheck.md): /pricing with the owner's plans and prices (25 October 2026). Nothing is on
 * sale yet. A paid plan's "Choose" buttons lead to /signup?plan=<id>&billing=<period> only when NEXT_PUBLIC_BILLING_OPEN=1 at build
 * time; without it (the default, and CI) each paid plan says "Opens soon". Run against a build of each setting: the test of the other
 * state skips itself.
 */

const BILLING_OPEN = ['1', 'true'].includes(process.env.NEXT_PUBLIC_BILLING_OPEN ?? '');
const open = (page: Page) => visit(page, '/pricing', { title: /pricing/i, h1: 'Pricing' });
const plan = (page: Page, name: string) => page.getByRole('list', { name: 'Plans' }).locator(':scope > li').filter({ has: page.getByRole('heading', { name, exact: true }) });
const PAID: [string, string, ('monthly' | 'yearly')[]][] = [
  ['Pro', 'pro', ['monthly', 'yearly']], ['Team', 'team', ['monthly', 'yearly']],
  ['Consultant', 'consultant', ['monthly', 'yearly']], ['Founding customer', 'founding', ['yearly']],
];

test('/pricing: the lead, and the five plans with the owner’s exact prices', async ({ page }) => {
  await open(page);
  await expect(page.getByText('Browsing stays free, and no paid plan is on sale yet: nothing is charged until a feature works and its terms are published.')).toBeVisible();
  await expect(page.getByText('Prices in euros, excluding VAT.')).toBeVisible();
  await expect(page.getByRole('list', { name: 'Plans' }).locator(':scope > li h3')).toHaveText(['Free', 'Pro', 'Team', 'Consultant', 'Founding customer']);
  const prices: [string, string[]][] = [
    ['Free', ['€0']],
    ['Pro', ['€59 / month', 'or €590 / year']],
    ['Team', ['€149 / month', 'or €1,490 / year']],
    ['Consultant', ['€299 / month', 'or €2,990 / year']],
    ['Founding customer', ['€390 / year', 'Price fixed']],
  ];
  for (const [name, lines] of prices) for (const l of lines) await expect(plan(page, name), `${name}: ${l}`).toContainText(l);
  await expect(plan(page, 'Founding customer')).toContainText('For the first 20 customers');
  await expect(plan(page, 'Founding customer')).not.toContainText('/ month');
});

test('/pricing: the on-request items, each "On request, opens soon"', async ({ page }) => {
  await open(page);
  const items = page.getByRole('list', { name: 'On request' }).locator(':scope > li');
  await expect(items.locator('h3')).toHaveText(['Call & Consortium Brief', 'Cluster or association licence', 'White-label, API or data licence']);
  for (const [i, price] of ['€450–900, one-off', '€4,900–9,900 / year', 'From €12,000 / year'].entries()) {
    await expect(items.nth(i)).toContainText(price);
    await expect(items.nth(i)).toContainText('On request, opens soon');
    await expect(items.nth(i).locator('a')).toHaveCount(0);
  }
  await expect(items.nth(0)).toContainText('a shortlist of 10–20 partners');
  await expect(items.nth(1)).toContainText('up to 50 companies');
});

test('/pricing: "Coming" sits only on features that are not live, and Free has none', async ({ page }) => {
  await open(page);
  const coming = await page.locator('main li:has(> [data-coming])').evaluateAll((els) => els.map((e) => e.firstChild?.textContent?.trim()));
  // WP-131: saved searches and alerts are built and open with sign-in (their own tag); consortium gap analysis is live and free
  expect(coming).toEqual(['Export of the eligibility check', 'Shared workspace',
    'Supplier-map export', 'Up to 15 client profiles', 'Branded PDF reports', 'Access for members, up to 50 companies', 'A co-branded digest',
    'White-label', 'API (offered only here)']);
  await expect(page.locator('main [data-coming]').first()).toHaveText('Coming');
  const free = plan(page, 'Free');
  await expect(free.locator('[data-coming]')).toHaveCount(0);
  await expect(free.locator('li')).toHaveText(['Browse tenders, funding calls, buyers and companies', 'What changed in the last 14 days',
    'Atom and calendar feeds', 'CSV export of the lists', 'Readiness check (answers saved in your browser, not on our server)']);
});

test('/pricing with billing off: no button, no sign-up or mail link, "Opens soon" on each paid plan', async ({ page }) => {
  test.skip(BILLING_OPEN, 'this build has NEXT_PUBLIC_BILLING_OPEN set');
  await open(page);
  await expect(page.locator('main a[href*="signup"], main a[href^="mailto:"]')).toHaveCount(0);
  for (const [name] of PAID) {
    await expect(plan(page, name).locator('[data-opens-soon]')).toHaveText('Opens soon');
    await expect(plan(page, name).locator('a')).toHaveCount(0);
  }
  await expect(plan(page, 'Free').getByText('Opens soon')).toHaveCount(0);
  await page.getByText('How do I get access?').click();
  await expect(page.getByText('Plans open soon: each paid plan will then have a button to choose it.')).toBeVisible();
});

test('/pricing with billing on: each paid plan’s buttons lead to /signup with its plan and period', async ({ page }) => {
  test.skip(!BILLING_OPEN, 'this build has NEXT_PUBLIC_BILLING_OPEN unset');
  await open(page);
  for (const [name, id, billings] of PAID) {
    const links = plan(page, name).getByRole('link');
    await expect(links).toHaveCount(billings.length);
    for (const [i, b] of billings.entries()) {
      await expect(links.nth(i)).toHaveAttribute('href', `/signup?plan=${id}&billing=${b}`);
      await expect(links.nth(i)).toHaveText(billings.length > 1 ? `Choose ${name}, ${b}` : `Choose ${name}`);
    }
    await expect(plan(page, name).locator('[data-opens-soon]')).toHaveCount(0);
  }
  await expect(plan(page, 'Free').getByRole('link')).toHaveCount(0);
  await expect(page.locator('main a[href^="mailto:"]')).toHaveCount(0);
});

test('/pricing at 375 px: no sideways scroll, the cards in one column', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
  const page = await context.newPage();
  await open(page);   // visit checks the page's horizontal scroll
  const lefts = await page.getByRole('list', { name: 'Plans' }).locator(':scope > li').evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().left)));
  expect(new Set(lefts).size, 'one column').toBe(1);
  for (const card of await page.locator('main li').filter({ has: page.locator('h3') }).all()) {
    const { scroll, client } = await card.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
    expect(scroll).toBeLessThanOrEqual(client + 1);
  }
  await context.close();
});

for (const scheme of ['light', 'dark'] as const) {
  test(`/pricing in the ${scheme} theme: colours, and the card hover rule (no card highlight, no underline; buttons own their hover)`, async ({ browser }) => {
    const context = await browser.newContext({ colorScheme: scheme });
    const page = await context.newPage();
    await page.goto('/pricing', { waitUntil: 'load' });
    const lum = (sel: string, prop: 'color' | 'backgroundColor') => page.locator(sel).first().evaluate((el, p) => {
      const [r, g, b] = (getComputedStyle(el)[p].match(/\d+/g) ?? ['0', '0', '0']).slice(0, 3).map(Number);
      return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    }, prop);
    if (scheme === 'dark') expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('dark');
    const card = plan(page, 'Pro');
    if (scheme === 'dark') {
      expect(await lum('body', 'backgroundColor'), 'a dark page').toBeLessThan(0.3);
      expect(await lum('main ul[aria-label="Plans"] > li', 'backgroundColor'), 'a dark card').toBeLessThan(0.3);
      expect(await lum('main ul[aria-label="Plans"] > li h3', 'color'), 'light text').toBeGreaterThan(0.7);
    } else {
      expect(await lum('main ul[aria-label="Plans"] > li', 'backgroundColor'), 'a light card').toBeGreaterThan(0.9);
    }
    // A plan card is not a link: hovering it changes neither its surface nor its edge and underlines nothing
    expect(await card.evaluate((e) => e.closest('a'))).toBeNull();
    const look = () => card.evaluate((e) => ({ bg: getComputedStyle(e).backgroundColor, border: getComputedStyle(e).borderColor,
      lines: [...e.querySelectorAll('h3, p, li')].map((n) => getComputedStyle(n).textDecorationLine) }));
    const before = await look();
    await card.locator('h3').hover();
    const after = await look();
    expect(after.bg).toBe(before.bg);
    expect(after.border).toBe(before.border);
    expect(after.lines.every((l) => l === 'none'), 'nothing underlined on hover').toBe(true);
    if (BILLING_OPEN) {
      // the button: no underline on its own hover either (a button, not a text link), and its focus is visible
      const button = card.getByRole('link').first();
      await button.hover();
      expect(await button.evaluate((e) => getComputedStyle(e).textDecorationLine)).toBe('none');
      await button.focus();
      await page.keyboard.press('Shift+Tab');
      await page.keyboard.press('Tab');
      await expect(button).toBeFocused();
      expect(await button.evaluate((e) => getComputedStyle(e).outlineStyle)).not.toBe('none');
    }
    await context.close();
  });
}
