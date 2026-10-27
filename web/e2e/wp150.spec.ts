import { expect, test, type Locator, type Page } from '@playwright/test';
import { visit, watchErrors } from './helpers';

/**
 * WP-150 (design pass, phase 2, docs/verification/round6/wp150-selfcheck.md): the home tiles are one line, a big number and one action;
 * the lists, forms, readiness pages and record pages follow WP-149's first-screen rule; two account-area defects are fixed at the cause.
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const firstScreen = (page: Page) => page.setViewportSize(isMobile(page) ? { width: 375, height: 812 } : { width: 1440, height: 900 });
const bottom = (l: Locator) => l.first().evaluate((e) => e.getBoundingClientRect().bottom);
const TENDER = '/tenders/1-framework-agreement-machined-aluminium-housings';
const CALL = '/funding/1-edf-2026-additive-manufacturing-spare-parts';

test('home: the owner’s shorter lead; each tile is its question, one line, a big number and one action', async ({ page }) => {
  await firstScreen(page);
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  await expect(page.locator('section[aria-labelledby="hero"] p').first())
    .toHaveText('Defence tenders, EU funding calls, partners and an eligibility check. Free, every fact linked to its source.');
  const tiles = page.locator('[data-tile]');
  await expect(tiles).toHaveCount(3);
  for (const tile of await tiles.all()) {
    // the question (h2), one short line and the action: no paragraph of description
    const words = (await tile.locator('h2 + span').innerText()).split(/\s+/).length;
    expect(words, 'one short line').toBeLessThanOrEqual(5);
    await expect(tile.locator('[id$="-b"]')).toHaveCount(0);
    // every number is the big element of its tile: at least 32 px
    for (const n of await tile.locator('[data-figure] > span:first-child').all()) {
      expect(await n.evaluate((e) => parseFloat(getComputedStyle(e).fontSize))).toBeGreaterThanOrEqual(32);
    }
  }
  // on a desktop the three tiles, their numbers and actions included, are on the first screen
  if (!isMobile(page)) expect(await tiles.evaluateAll((ts) => Math.max(...ts.map((t) => t.getBoundingClientRect().bottom)))).toBeLessThanOrEqual(900);
});

test('forms: a label sits 8 px above its field (the funding search, a readiness field)', async ({ page }) => {
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i });
  if (isMobile(page)) await page.getByRole('button', { name: /^Show filters/ }).click();
  const gap = (input: Locator) => input.evaluate((i) => {
    const label = document.querySelector(`label[for="${i.id}"]`)!.getBoundingClientRect();
    return Math.round(i.parentElement!.getBoundingClientRect().top - label.bottom);
  });
  expect(await gap(page.getByRole('search', { name: 'Filter funding calls' }).getByLabel('Search', { exact: true }))).toBe(8);
  await visit(page, '/readiness/supplier', { title: /supplier/i, h1: 'Supplier profile' });
  expect(await page.getByLabel('Country where your company is established').evaluate((s) => {
    const label = document.querySelector(`label[for="${s.id}"]`)!.getBoundingClientRect();
    return Math.round(s.closest('div.relative')!.getBoundingClientRect().top - label.bottom);
  })).toBe(8);
});

test('/funding: a one-line lead, a one-line search hint with the rest behind "What is searched", phone tools as a row of links', async ({ page }) => {
  await firstScreen(page);
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i, text: ['EU and national funding calls for defence and dual-use projects, each linked to its source.'] });
  if (!isMobile(page)) {
    const lines = await page.locator('main header p.lead').evaluate((p) => Math.round(p.getBoundingClientRect().height / parseFloat(getComputedStyle(p).lineHeight)));
    expect(lines).toBe(1);
  }
  if (isMobile(page)) await page.getByRole('button', { name: /^Show filters/ }).click();
  const form = page.getByRole('search', { name: 'Filter funding calls' });
  await expect(form.getByText('Matches whole words.')).toBeVisible();
  const about = form.locator('[data-about]').filter({ hasText: 'What is searched' });
  await expect(about.locator('details')).not.toHaveAttribute('open', '');
  await about.getByText('What is searched').click();
  await expect(about).toContainText('Titles, call IDs and the source’s topic keywords, as whole words; drone also finds unmanned.');
  if (isMobile(page)) {
    await page.goto('/funding');
    const tools = page.locator('#results').getByRole('link', { name: 'Download CSV' });
    await expect(tools).toBeVisible();
    await expect(page.locator('#results').getByText('The public fields of this result, up to 2,000 rows')).toBeHidden();
  }
});

test('a tender page: title, status, deadline, value and buyer on the first screen', async ({ page }) => {
  await firstScreen(page);
  await visit(page, TENDER, { title: /DefenceGate/, h1: /machined aluminium housings/ });
  const h = page.viewportSize()!.height;
  const facts = page.locator('[data-head-facts]');
  await expect(facts).toContainText('Estimated value');
  await expect(facts.getByRole('link', { name: 'Demo Defence Materiel Organisation' })).toHaveAttribute('href', /^\/buyers\//);
  expect(await bottom(facts)).toBeLessThanOrEqual(h);
  expect(await bottom(page.locator('main header').getByText('Open', { exact: true }))).toBeLessThanOrEqual(h);
  const deadline = isMobile(page) ? page.locator('[data-phone-first] [data-deadline]') : page.locator('aside [data-deadline]');
  await expect(deadline).toBeVisible();
  expect(await bottom(deadline)).toBeLessThanOrEqual(h);
});

test('a call page: title, status, deadline, budget and funder on the first screen', async ({ page }) => {
  await firstScreen(page);
  await visit(page, CALL, { title: /DefenceGate/, h1: 'Additive manufacturing of certified spare parts' });
  const facts = page.locator('[data-head-facts]');
  for (const t of ['Deadline', 'Budget', 'Funder', 'European Commission · European Defence Fund', 'in 45 days']) await expect(facts).toContainText(t);
  expect(await bottom(facts)).toBeLessThanOrEqual(page.viewportSize()!.height);
  expect(await bottom(page.locator('main header').getByText('Open', { exact: true }))).toBeLessThanOrEqual(page.viewportSize()!.height);
});

test('/search: the large page search fills the column, as on home', async ({ page }) => {
  await visit(page, '/search', { title: /Search/, h1: 'Search' });
  const m = await page.evaluate(() => {
    const header = document.querySelector('main header')!.getBoundingClientRect();
    const input = document.getElementById('page-search')!;
    const button = input.closest('form')!.querySelector('button[type="submit"]')!.getBoundingClientRect();
    return { header: header.width, row: Math.max(input.parentElement!.getBoundingClientRect().right, button.right) - input.parentElement!.getBoundingClientRect().left };
  });
  expect(m.row).toBeGreaterThanOrEqual(m.header - 1);
});

test('readiness pages: the privacy statement is a line with its full text one click away, not a box', async ({ page }) => {
  for (const [path, h1] of [['/readiness/supplier', 'Supplier profile'], ['/readiness/spain-automotive', /Spain/]] as const) {
    await visit(page, path, { title: /./, h1 });
    await expect(page.locator('main aside', { hasText: 'Your answers are not stored on our server' })).toHaveCount(0);
    const line = page.locator('main [data-privacy-line]');
    await expect(line).toContainText('Your answers are not stored on our server.');
    await expect(line.locator('[data-what-is-sent]')).toBeHidden();
    await line.getByText('What is kept and what is sent').click();
    await expect(line.locator('[data-what-is-sent]')).toBeVisible();
  }
  // the supplier form starts on a desktop's first screen
  if (!isMobile(page)) {
    await page.setViewportSize({ width: 1440, height: 900 });
    await visit(page, '/readiness/supplier', { title: /supplier/i, h1: 'Supplier profile' });
    expect(await page.locator('main form').first().evaluate((f) => f.getBoundingClientRect().top)).toBeLessThan(900);
  }
});

test('/organisations: the programme scope is a line, not a tinted box; the tab says what it is in one line', async ({ page }) => {
  await visit(page, '/organisations', { title: /organisations/i, h1: 'Companies', text: ['Companies and research bodies in EU-funded defence and research projects.'] });
  const scope = page.locator('main [role="status"]', { hasText: 'Show all programmes' });
  await expect(scope).toBeVisible();
  expect(await scope.evaluate((e) => getComputedStyle(e).backgroundColor)).toBe('rgba(0, 0, 0, 0)');
});

test('no page of this pass scrolls sideways at 320 px', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  for (const path of ['/', '/funding', '/buyers', '/organisations', '/suppliers', '/check', '/calendar', '/search?q=ammunition', TENDER, CALL,
    '/buyers/1-demo-armaments-agency', '/organisations/101-alpha-systems-gmbh', '/readiness/supplier', '/readiness/spain-automotive']) {
    await visit(page, path, { title: /./, h1: /.+/ });
  }
});

// ---------------------------------------------------------------- the account area (needs the fake account API, as e2e/wp79.spec.ts)

test.describe('the dashboard, against the fake account API', () => {
  test.skip(!process.env.E2E_FAKE_ACCOUNTS, 'needs E2E_FAKE_ACCOUNTS=1 and a site started with DG_API_URL pointing at e2e/support/fake-accounts.mjs');
  test.use({ ignoreHTTPSErrors: true });

  test.beforeEach(async ({ page }) => {
    await page.goto('/signin');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill('ann@example.test');
    await page.getByLabel('Password', { exact: true }).fill('right password here');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForURL(/\/app$/);
  });

  test('C1: /app hydrates without React error #418, load after load', async ({ page }) => {
    // the error came on some loads only (about 1 in 5, at 375 and at 1280 px). Not `visit`: the account's own address is on its pages.
    const errors = watchErrors(page);
    for (let i = 0; i < 12; i++) {
      await page.goto('/app', { waitUntil: 'networkidle' });
      await expect(page.locator('h1')).toContainText('Welcome');
    }
    expect(errors).toEqual([]);
  });

  test('C2: no title in a dashboard block is underlined at rest; a title underlines on its own hover', async ({ page }) => {
    await page.goto('/app', { waitUntil: 'networkidle' });
    await page.mouse.move(0, 0);   // the pointer is left where "Sign in" was, over a title of the dashboard: away, so nothing is hovered
    const titles = page.locator('main [data-item-title] a');
    await expect(page.locator('section[aria-labelledby="changes"] [data-item-title] a')).toHaveCount(1);
    for (const a of await titles.all()) expect(await a.evaluate((e) => getComputedStyle(e).textDecorationLine), await a.innerText()).toBe('none');
    if (!isMobile(page)) {
      const change = page.locator('section[aria-labelledby="changes"] [data-item-title] a');
      await change.hover();
      await expect.poll(() => change.evaluate((e) => getComputedStyle(e).textDecorationLine)).toContain('underline');
    }
  });
});
