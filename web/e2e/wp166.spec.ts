import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Locator, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-166 (owner, 31 Oct 2026): the home page leads with the job "assemble a consortium for a call" (find a call, check eligibility, the
 * consortium's gaps, partners) with the Ukraine lists in sight; Funding leads the Tenders & funding menu, which holds Contracts ending
 * soon; partner suggestions show each organisation's past roles, mark Ukrainian organisations and filter to them.
 * Screenshots go to WP166_SHOTS when it is set (the self-check).
 */
const SHOTS = process.env.WP166_SHOTS;
const HOME = { title: /DefenceGate/, h1: 'Win, partner, qualify.' } as const;
const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;

async function shot(page: Page, name: string, full = true) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: full });
}

test('home: the consortium path comes first, four steps through existing pages, with the Ukraine lists and their counts', async ({ page }) => {
  await visit(page, '/', HOME);
  const pathBox = page.locator('[data-consortium-path]');
  await expect(pathBox.getByRole('heading', { level: 2 })).toHaveText('Build a consortium for an EU defence call');
  const steps = pathBox.locator('[data-step]');
  expect(await steps.evaluateAll((as) => as.map((a) => a.getAttribute('href')))).toEqual(['/funding', '/check', '/networks/consortium-gaps', '/organisations']);
  await expect(steps.locator('h3')).toHaveText(['1 Find a call', '2 Check eligibility', '3 See the gaps', '4 Find partners']);
  // it stands between the search and the three question tiles
  const top = async (l: Locator) => (await l.boundingBox())!.y;
  expect(await top(pathBox)).toBeGreaterThan(await top(page.locator('section[aria-labelledby="hero"]')));
  expect(await top(pathBox)).toBeLessThan(await top(page.locator('[data-tile]').first()));
  // WP-166: on a desktop the four steps are on the first screen (the place the tiles held, WP-117/WP-150)
  if (!isMobile(page)) expect(await steps.evaluateAll((ts) => Math.max(...ts.map((t) => t.getBoundingClientRect().bottom)))).toBeLessThanOrEqual(page.viewportSize()!.height);
  // the Ukraine flags in sight, with the counts of the lists they open
  const ua = pathBox.locator('[data-ukraine-line]');
  await expect(ua.getByRole('link', { name: /open to Ukrainian participants$/ })).toHaveAttribute('href', '/funding?ukraine=true');
  await expect(ua.getByRole('link', { name: /Ukraine Support Instrument calls?$/ })).toHaveAttribute('href', '/funding?programme=EDIP-USI');
  await expect(ua.getByRole('link', { name: 'Ukraine partners' })).toHaveAttribute('href', '/networks/ukraine-partners');
  const n = (await ua.getByRole('link', { name: /open to Ukrainian participants$/ }).innerText()).match(/^([\d,]+) calls? open/)![1];
  await visit(page, '/funding?ukraine=true', { title: /funding/i, h1: /funding/i });
  expect((await page.locator('#results-heading').innerText()).match(/of ([\d,]+)/)?.[1] ?? '0').toBe(n);
  // funding before tenders: the first tile's actions and the closing lists
  await visit(page, '/', HOME);
  expect(await page.locator('[data-tile]').first().locator('a').evaluateAll((as) => as.map((a) => a.getAttribute('href')))).toEqual(['/funding', '/tenders']);
  const f = await top(page.locator('section[aria-labelledby="closing"]'));
  const t = await top(page.locator('section[aria-labelledby="closing-tenders"]'));
  expect(f).toBeLessThanOrEqual(t);
  await shot(page, `home-${isMobile(page) ? '375' : '1280'}`);
});

for (const theme of ['light', 'dark'] as const) {
  test(`home: a step card shows hover and focus on its edge, never an underline (${theme})`, async ({ page }) => {
    test.skip(isMobile(page), 'hover is a pointer state');
    await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: theme });
    await page.addInitScript((t) => { try { localStorage.setItem('dg-theme', t); } catch { /* none */ } }, theme);
    await page.setViewportSize({ width: 1440, height: 900 });
    await visit(page, '/', HOME);
    const look = (l: Locator) => l.evaluate((e) => { const c = getComputedStyle(e); return `${c.borderColor}|${c.backgroundColor}`; });
    const underlined = (l: Locator) => l.evaluate((root) => [root, ...root.querySelectorAll('*')].some((e) => getComputedStyle(e).textDecorationLine.includes('underline')));
    for (const a of await page.locator('[data-step]').all()) {
      await page.mouse.move(1, 1);
      const rest = await look(a);
      await a.hover();
      await expect.poll(() => look(a)).not.toBe(rest);
      expect(await underlined(a), 'no underline on hover').toBe(false);
      await page.mouse.move(1, 1);
      await a.focus();
      await expect.poll(() => look(a)).not.toBe(rest);
      await a.blur();
    }
    await shot(page, `home-1440-${theme}`, false);
  });
}

test('home at 320 px: no horizontal scroll with the consortium path', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await visit(page, '/', HOME);              // visit fails on a horizontal scroll
  const w = await page.evaluate(() => ({ s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth }));
  expect(w.s).toBeLessThanOrEqual(w.c);
});

test('the menu: Funding leads Tenders & funding, which holds Contracts ending soon; it is no top-level item', async ({ page }) => {
  await visit(page, '/', HOME);
  if (isMobile(page)) {
    await page.getByRole('button', { name: 'Open menu' }).click();
    const menu = page.getByRole('navigation', { name: 'Main menu' });
    await expect(menu.getByRole('link', { name: 'Contracts ending soon', exact: true })).toHaveAttribute('href', '/tenders/ending');
    await shot(page, 'nav-mobile-375', false);
    await menu.getByRole('link', { name: 'Contracts ending soon', exact: true }).click();
  } else {
    await page.setViewportSize({ width: 1440, height: 900 });
    const nav = page.getByRole('navigation', { name: 'Main' });
    await expect(nav.locator(':scope > * > :first-child')).toHaveText(['Tenders & funding', 'Partners', 'Check my company', 'What’s new']);
    await nav.getByRole('button', { name: 'Tenders & funding', exact: true }).click();
    await expect(page.locator('#sub-open a')).toHaveText(['Funding', 'Tenders', 'Contracts ending soon', 'Buyers', 'Market overview']);
    await shot(page, 'nav-desktop-1440', false);
    await page.locator('#sub-open').getByRole('link', { name: 'Contracts ending soon', exact: true }).click();
  }
  await page.waitForURL(/\/tenders\/ending$/);
  await expect(page.locator('#main h1')).toHaveText('Contracts ending soon');
});

// ------------------------------------------------------------------ partner suggestions: past roles and Ukrainian organisations

const ROLES = { coordinator: 3, participant: 9, thirdParty: 1, other: 0 };
const ANSWER = {
  call: { id: '1', slug: '1-x', topic: 'EDF-2026-DA-SPACE-PRS-STEP' },
  area: { kind: 'edf-category', label: 'EDF capability category SPACE', rule: 'EDF projects whose factsheet file name names the category SPACE, as this call’s topic code does.', projects: 12, organisations: 40, firstYear: 2022, lastYear: 2025, broaderThanCall: false },
  partners: [
    { organisationId: '11', slug: '11-alpha-sa', name: 'Alpha SA', country: 'FR', projects: 5, coordinated: 2, firstYear: 2022, lastYear: 2025, roles: ROLES, evidence: [{ projectId: '1', acronym: 'ORBITX', title: 'Orbit', year: 2025, role: 'coordinator' }] },
    { organisationId: '13', slug: '13-kyiv-space-institute', name: 'Kyiv Space Institute', country: 'UA', projects: 1, coordinated: 0, firstYear: 2024, lastYear: 2024, roles: { coordinator: 0, participant: 2, thirdParty: 0, other: 0 }, evidence: [{ projectId: '3', acronym: 'MOON', title: 'Moon', year: 2024, role: 'participant' }] },
  ],
  countries: [{ country: 'FR', organisations: 30 }, { country: 'ES', organisations: 9 }, { country: 'UA', organisations: 1 }],
  total: 40, country: null, note: null,
  source: { readAt: '2026-10-17T12:00:00Z', sources: ['CORDIS, European Commission', 'European Commission, DG DEFIS, EDF results factsheets'], licence: 'Commission Decision 2011/833/EU (reuse of Commission documents)' },
};

test('partner suggestions: past roles per organisation, Ukrainian ones marked, and a filter to them', async ({ page }) => {
  const asked: string[] = [];
  await page.route('**/api/funding/*/partners*', async (route) => {
    const country = new URL(route.request().url()).searchParams.get('country');
    asked.push(country ?? '');
    const partners = country ? ANSWER.partners.filter((p) => p.country === country) : ANSWER.partners;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...ANSWER, partners, country, total: partners.length }) });
  });
  await page.goto('/funding?programme=EDF&status=all');
  const href = await page.locator('a[href^="/funding/"]:not([href*="export"])').first().getAttribute('href');
  await visit(page, href!, { title: /DefenceGate/, h1: /.+/ });
  await page.getByRole('button', { name: 'Show organisations from earlier projects' }).click();
  const alpha = page.getByRole('listitem').filter({ has: page.getByRole('link', { name: 'Alpha SA' }) });
  await expect(alpha.locator('[data-past-roles]')).toHaveText('Past roles, all its projects: coordinator in 3 projects, participant in 9, third party in 1.');
  await expect(alpha.locator('[data-ua-mark]')).toHaveCount(0);
  const kyiv = page.getByRole('listitem').filter({ has: page.getByRole('link', { name: 'Kyiv Space Institute' }) });
  await expect(kyiv.locator('[data-ua-mark]')).toHaveText('Ukrainian organisation');
  await kyiv.scrollIntoViewIfNeeded();
  await shot(page, `call-partner-roles-${isMobile(page) ? '375' : '1280'}`);
  const filter = page.locator('[data-ua-filter]');
  await expect(filter).toHaveText('Ukrainian organisations only (1)');
  await expect(filter).toHaveAttribute('aria-pressed', 'false');
  await filter.click();
  await expect(page.getByRole('link', { name: 'Alpha SA' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Kyiv Space Institute' })).toBeVisible();
  await expect(filter).toHaveAttribute('aria-pressed', 'true');
  await filter.click();
  await expect(page.getByRole('link', { name: 'Alpha SA' })).toBeVisible();
  expect(asked).toEqual(['', 'UA', '']);
});

test('consortium gaps: each organisation’s past roles, and the way to the Ukrainian organisations', async ({ page }) => {
  await visit(page, '/networks/consortium-gaps?topic=CYBER&lacking=UA', { title: /Repeat participants/i, h1: 'Consortium gaps' });
  await expect(page.locator('[data-past-roles]').first()).toHaveText('Past roles: coordinator in 1 project, participant in 3');
  await expect(page.locator('[data-ua-partners-link]').getByRole('link', { name: 'Ukraine partners' })).toHaveAttribute('href', '/networks/ukraine-partners');
});
