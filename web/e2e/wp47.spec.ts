import { expect, test, type Page } from '@playwright/test';
import { BLOCK_WIDTHS, paragraphsNarrowerThanBlock, paragraphsOutsideFrame, visit } from './helpers';

/**
 * Page-level layout of the record and list pages (WP-47, docs/verification/product/wp47-selfcheck.md): a call and a tender page with a
 * side column and a sticky index, list cards that are short, a filter column that folds and stays on screen, buyer pages that say the
 * automatic-classification line once, tables that stay readable at 375 px. Every check reads computed styles or boxes, never copy, and
 * runs at 1280 px and at 375 px (CI runs it; it was not run on the laptop).
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const CALL = '/funding/1-edf-2026-additive-manufacturing-spare-parts';
const TENDER = '/tenders/1-framework-agreement-machined-aluminium-housings';

test('a call page puts its key facts and deadline in a side column and the index at its left, from 1280 px', async ({ page }) => {
  test.skip(isMobile(page), 'one column on a phone');
  await visit(page, CALL, { title: /DefenceGate/, h1: /additive manufacturing/i });
  const box = await page.evaluate(() => {
    const rect = (sel: string) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, w: r.width, h: r.height }; };
    const nav = document.querySelector('.d-nav');
    return { nav: rect('.d-nav'), main: rect('.d-main'), side: rect('.d-side'), facts: rect('.d-facts'), navPos: nav ? getComputedStyle(nav).position : '' };
  });
  expect(box.nav && box.main && box.side && box.facts, 'the four parts exist').toBeTruthy();
  expect(box.nav!.right, 'the index is left of the text').toBeLessThanOrEqual(box.main!.left);
  expect(box.main!.right, 'the text is left of the side column').toBeLessThanOrEqual(box.side!.left);
  expect(box.facts!.left, 'facts are in the side column').toBeGreaterThanOrEqual(box.main!.right);
  expect(box.facts!.top, 'facts are under the deadline').toBeGreaterThan(box.side!.top);
  expect(box.main!.w, 'the text column is wide enough to read').toBeGreaterThanOrEqual(560);
  expect(box.navPos).toBe('sticky');
});

test('the index of a call page stays on screen while the page scrolls', async ({ page }) => {
  test.skip(isMobile(page), 'a phone has the index at the top of the page');
  await visit(page, CALL, { title: /DefenceGate/, h1: /additive manufacturing/i });
  const nav = page.getByRole('navigation', { name: 'On this page' });
  await page.evaluate(() => window.scrollTo(0, 1600));
  await expect(nav).toBeInViewport();
});

test('a call page on a phone is one column: deadline, index, facts, then the panels', async ({ page }) => {
  test.skip(!isMobile(page), 'desktop has a side column');
  await visit(page, CALL, { title: /DefenceGate/, h1: /additive manufacturing/i });
  const tops = await page.evaluate(() => ['.d-top', '.d-nav', '.d-facts', '.d-main'].map((s) => document.querySelector(s)?.getBoundingClientRect().top ?? -1));
  expect(tops.every((t) => t >= 0)).toBe(true);
  expect([...tops].sort((a, b) => a - b)).toEqual(tops);
});

test('a tender page has the same side column, and its related notices are a list, not three squeezed columns', async ({ page }) => {
  await visit(page, TENDER, { title: /DefenceGate/, h1: /.+/ });
  const g = await page.evaluate(() => {
    const main = document.querySelector('.d-main')!.getBoundingClientRect();
    const facts = document.querySelector('.d-facts')!.getBoundingClientRect();
    const cards = [...document.querySelectorAll('section[aria-labelledby=related] ul > li > article')].map((a) => a.getBoundingClientRect().width);
    return { mainRight: main.right, factsLeft: facts.left, factsW: facts.width, cards };
  });
  if (!isMobile(page)) expect(g.factsLeft).toBeGreaterThanOrEqual(g.mainRight);
  expect(g.cards.length, 'the page has related notices of the same buyer').toBeGreaterThan(0);
  for (const w of g.cards) expect(w, 'a related card is as wide as the text column').toBeGreaterThan(isMobile(page) ? 300 : 800);
});

// WP-62 (owner, 21 Oct 2026): the compact card, measured median 232 at 1280 and 490 at 375 (WP-47: 245 / 560).
test('a tender card is short, and the classification line is said once above the list, not on every card', async ({ page }) => {
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.locator('main article').first()).toBeVisible();
  const heights = await page.locator('main article').evaluateAll((a) => a.map((e) => Math.round(e.getBoundingClientRect().height)));
  const sorted = [...heights].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  expect(median, `tender card heights ${heights.join(',')}`).toBeLessThanOrEqual(isMobile(page) ? 540 : 260);
  expect(Math.max(...heights), `tender card heights ${heights.join(',')}`).toBeLessThanOrEqual(isMobile(page) ? 600 : 300);
  const lines = await page.getByText(/^Classified automatically/).count();
  expect(lines, 'the line is on the page once').toBe(1);
  await expect(page.getByText(/^Classified automatically/).locator('xpath=ancestor::article')).toHaveCount(0);
});

test('a buyer page says how notices are classified once, not on each of its cards', async ({ page }) => {
  await visit(page, '/buyers/1-demo-armaments-agency', { title: /DefenceGate/, h1: /.+/ });
  expect(await page.getByText(/^Classified automatically/).count()).toBe(1);
});

test('the filter column folds into groups, keeps every filter, and stays on screen from 1024 px', async ({ page }) => {
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  if (isMobile(page)) {
    const button = page.getByRole('button', { name: /^Show filters/ });
    await expect(button).toBeVisible();
    await button.click();
    await expect(page.getByRole('button', { name: /^Hide filters/ })).toBeVisible();
  }
  const form = page.getByRole('search', { name: 'Filter tenders' });
  const groups = form.locator('details');
  expect(await groups.count(), 'the filter groups').toBeGreaterThanOrEqual(4);
  // The country list is folded away but still in the form: a closed group is submitted.
  const country = form.locator('details', { hasText: 'Buyer country' });
  expect(await country.evaluate((d) => (d as HTMLDetailsElement).open)).toBe(false);
  expect(await country.locator('input[type=checkbox]').count(), 'every country stays a filter').toBeGreaterThanOrEqual(20);
  await country.locator('summary').click();
  await expect(country.locator('input[type=checkbox]').first()).toBeVisible();
  // Every option row of a filter is at least 32 px high (a checkbox or radio label is the target).
  const sizes = await form.evaluate((f) => [...f.querySelectorAll('label:has(input[type=checkbox]), label:has(input[type=radio])')]
    .filter((l) => l.getBoundingClientRect().height > 0).map((l) => Math.round(l.getBoundingClientRect().height)));
  expect(sizes.length).toBeGreaterThan(5);
  expect(Math.min(...sizes), 'option rows are at least 32 px high').toBeGreaterThanOrEqual(32);
  if (!isMobile(page)) {
    const col = await page.evaluate(() => {
      const f = document.querySelector('main form[role=search]')!;
      let e: HTMLElement | null = f.parentElement;
      while (e && getComputedStyle(e).position !== 'sticky') e = e.parentElement;
      return e ? { pos: getComputedStyle(e).position, top: getComputedStyle(e).top } : null;
    });
    expect(col?.pos, 'the filter column is sticky').toBe('sticky');
  }
});

test('the funding filters fold too, and the cascade and Ukraine filters stay in reach', async ({ page }) => {
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i });
  if (isMobile(page)) await page.getByRole('button', { name: /^Show filters/ }).click();
  const form = page.getByRole('search', { name: 'Filter funding calls' });
  await expect(form.getByLabel(/^Only calls with cascade funding/)).toBeVisible();
  await expect(form.getByLabel(/^Only calls open to Ukraine/)).toBeVisible();
  const height = await form.evaluate((f) => f.getBoundingClientRect().height);
  expect(height, 'the folded filter form (2,100 px before)').toBeLessThanOrEqual(1700);
});

test('no paragraph of a list or record page leaves the content frame, and a running paragraph fills its block', async ({ page }) => {
  // WP-83 adds the pages of the owner's screenshots: the supplier map, a supplier page and the Spain automotive entry.
  for (const path of ['/funding', '/tenders', '/organisations', CALL, TENDER, '/organisations/101-alpha-systems-gmbh',
    '/suppliers', '/suppliers/1-demo-airframes-gmbh', '/readiness/spain-automotive']) {
    await visit(page, path, { title: /.+/, h1: /.+/ });
    // WP-83 (owner, 22 Oct 2026, replacing the 62ch measure of WP-62): the frame keeps the header width and a running paragraph takes the
    // full width of its card or column, at 1440 and 1024 px (at 375 px `visit` checks that nothing scrolls sideways).
    const wide = await paragraphsOutsideFrame(page, { skip: 'table, nav, [role=region], article, .reading', minLength: 121 });
    expect(wide, `${path}: paragraphs outside the header's left and right edges`).toEqual([]);
    if (isMobile(page)) continue;
    for (const width of BLOCK_WIDTHS) {
      await page.setViewportSize({ width, height: 800 });
      expect(await paragraphsNarrowerThanBlock(page, { skip: 'table' }), `${path} at ${width} px: paragraphs narrower than 90 % of their block`).toEqual([]);
    }
    await page.setViewportSize({ width: 1280, height: 800 });
  }
});

test('an organisation with one programme shows it as facts, not as a one-row table; one with three keeps the table', async ({ page }) => {
  await visit(page, '/organisations/104-echo-iberica-sl', { title: /.+/, h1: /.+/ });
  await expect(page.getByRole('region', { name: 'Projects by programme' })).toHaveCount(0);
  await expect(page.locator('main dl.facts-grid--4')).toHaveCount(1);
  await visit(page, '/organisations/101-alpha-systems-gmbh', { title: /.+/, h1: /.+/ });
  await expect(page.getByRole('region', { name: 'Projects by programme' })).toHaveCount(1);
});

test('the tables of a profile keep their width and scroll inside their own box; no cell with text is squeezed under 100 px', async ({ page }) => {
  for (const path of ['/organisations/101-alpha-systems-gmbh?tab=partners', '/organisations/101-alpha-systems-gmbh?tab=projects', '/projects/201-alpha']) {
    await visit(page, path, { title: /.+/, h1: /.+/ });
    const t = await page.locator('main [role=region]:has(table)').first().evaluate((box) => {
      const table = box.querySelector('table')!;
      const squeezed = [...table.querySelectorAll('td, th')].filter((c) => {
        const text = (c.textContent ?? '').trim();
        if (text.length < 8 || c.getBoundingClientRect().width >= 100) return false;
        const range = document.createRange(); range.selectNodeContents(c);
        return new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size > 1;
      }).length;
      return { min: parseFloat(getComputedStyle(table).minWidth), squeezed };
    });
    expect(t.min, `${path}: the table keeps its width`).toBeGreaterThanOrEqual(480);
    expect(t.squeezed, `${path}: cells squeezed under 100 px`).toBe(0);
  }
});

test('a supplier page lists its buyers in a table, and a supplier in the list is a target of at least 32 px', async ({ page }) => {
  await visit(page, '/suppliers', { title: /supplier map/i, h1: 'Defence supplier map' });
  const first = page.locator('#results-heading').locator('xpath=following::ul[1]//a').first();
  const h = await first.evaluate((e) => e.getBoundingClientRect().height);
  expect(h).toBeGreaterThanOrEqual(32);
  await Promise.all([page.waitForURL(/\/suppliers\/\d+/), first.click()]);
  await expect(page.getByRole('region', { name: /Buyers whose notices/ }).locator('table')).toHaveCount(1);
  await expect(page.getByRole('region', { name: 'Result notices of this supplier' }).locator('table')).toHaveCount(1);
});

test('the CPV finder is a column of sections in two columns of codes from 1024 px', async ({ page }) => {
  test.skip(isMobile(page), 'one column on a phone');
  await visit(page, '/cpv', { title: /CPV/, h1: 'CPV finder' });
  const cols = await page.locator('main section ul').first().evaluate((u) => getComputedStyle(u).columnCount);
  expect(cols).toBe('2');
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  expect(h, 'page height (it was 18,700 px with one column)').toBeLessThan(14000);
});
