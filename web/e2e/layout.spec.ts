import { expect, test, type Page } from '@playwright/test';
import { BLOCK_WIDTHS, paragraphsNarrowerThanBlock, paragraphsOutsideFrame, visit } from './helpers';

/**
 * The layout foundation of WP-44 (docs/verification/product/wp44-selfcheck.md): one measure, the page-header scale, a card that reads as a
 * card, rhythm between sections, a grid that does not leave a half-empty row, and list cards that are short. Every check reads computed
 * styles or boxes, never copy. Runs at 1280 px and at 375 px (CI runs it; it was not run on the laptop).
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const px = (v: string) => parseFloat(v);

test('the page container is centred, with gutters of 16 px on a phone and 28 px from 768 px (brand book), and never wider than 1256 px', async ({ page }) => {
  await visit(page, '/about', { title: /About/i, h1: 'About' });
  const box = await page.evaluate(() => {
    const m = document.querySelector('main')!;
    const r = m.getBoundingClientRect();
    const s = getComputedStyle(m);
    return { left: r.left, right: document.documentElement.clientWidth - r.right, width: r.width, pad: parseFloat(s.paddingLeft) };
  });
  expect(Math.abs(box.left - box.right), 'left and right margin are equal').toBeLessThanOrEqual(1);
  expect(box.width).toBeLessThanOrEqual(1256);
  expect(box.pad).toBe(isMobile(page) ? 16 : 28);
});

test('the page title is the h1 of the book, 40/48 (32/40 on a phone), and the lead is larger than the body and in the ink colour', async ({ page }) => {
  await visit(page, '/about', { title: /About/i, h1: 'About' });
  const t = await page.evaluate(() => {
    const h1 = document.querySelector('main h1')!;
    const lead = document.querySelector('main h1 + p')!;
    const body = getComputedStyle(document.body);
    const ls = getComputedStyle(lead);
    const hs = getComputedStyle(h1);
    return { h1: hs.fontSize, h1lh: hs.lineHeight, lead: ls.fontSize, leadColor: ls.color, ink: body.color };
  });
  expect(t.h1).toBe(isMobile(page) ? '32px' : '40px');
  expect(t.h1lh).toBe(isMobile(page) ? '40px' : '48px');
  expect(px(t.lead)).toBeGreaterThan(16);
  expect(t.leadColor, 'the lead is not the muted grey').toBe(t.ink);
});

test('text-h4 is defined: the three questions on the home page are headings, not plain text', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  // WP-117: the questions are the headings of the three tiles
  const h = page.getByRole('heading', { name: 'What is open?', exact: true }).first();
  await expect(h).toBeVisible();
  const style = await h.evaluate((e) => ({ size: getComputedStyle(e).fontSize, weight: getComputedStyle(e).fontWeight }));
  expect(style.size).toBe('18px');
  expect(Number(style.weight)).toBeGreaterThanOrEqual(600);
});

test('no paragraph of a reading page leaves the content frame, a running paragraph fills its block, and the page is a centred column', async ({ page }) => {
  for (const path of ['/about', '/methodology', '/privacy', '/glossary']) {
    await visit(page, path, { title: /.+/, h1: /.+/ });
    // WP-83 (owner, 22 Oct 2026, replacing the 62ch measure of WP-62): the frame keeps the header width and a running paragraph takes the
    // full width of its card or column, at 1440 and 1024 px (at 375 px `visit` checks that nothing scrolls sideways).
    expect(await paragraphsOutsideFrame(page), `${path}: paragraphs outside the header's left and right edges`).toEqual([]);
    if (!isMobile(page)) {
      for (const width of BLOCK_WIDTHS) {
        await page.setViewportSize({ width, height: 800 });
        expect(await paragraphsNarrowerThanBlock(page), `${path} at ${width} px: paragraphs narrower than 90 % of their block`).toEqual([]);
      }
      await page.setViewportSize({ width: 1280, height: 800 });
    }
    // WP-45: the page frame is exactly as wide as the header pill (a 988 px column left the page narrower than the header).
    const col = await page.evaluate(() => {
      const r = document.querySelector('main h1')!.closest('div')!.getBoundingClientRect();
      const h = document.querySelector('header')!.getBoundingClientRect();
      return { left: r.left, right: r.right, headerLeft: h.left, headerRight: h.right };
    });
    expect(Math.abs(col.left - col.headerLeft), `${path}: frame left against the header`).toBeLessThanOrEqual(1);
    expect(Math.abs(col.right - col.headerRight), `${path}: frame right against the header`).toBeLessThanOrEqual(1);
  }
});

test('sections are at least 32 px apart, and a heading is closer to its own content than to the section above', async ({ page }) => {
  await visit(page, '/about', { title: /About/i, h1: 'About' });
  const gaps = await page.evaluate(() => {
    const h = [...document.querySelectorAll('main h2')].find((e) => /How we work/.test(e.textContent ?? ''))!;
    const section = h.closest('section')!;
    const prev = section.previousElementSibling!.getBoundingClientRect();
    const own = section.querySelector('ul, ol, div:not(:has(h2))')!.getBoundingClientRect();
    return { above: section.getBoundingClientRect().top - prev.bottom, below: own.top - h.getBoundingClientRect().bottom };
  });
  expect(gaps.above).toBeGreaterThanOrEqual(31.5);
  expect(gaps.below).toBeLessThan(gaps.above);
});

test('a grid of cards fills its rows: four cards in two columns, no card alone on a row', async ({ page }) => {
  test.skip(isMobile(page), 'one column on a phone');
  await visit(page, '/about', { title: /About/i, h1: 'About' });
  const tops = await page.evaluate(() => {
    const section = [...document.querySelectorAll('main section')].find((s) => /How we work/.test(s.querySelector('h2')?.textContent ?? ''))!;
    return [...section.querySelectorAll('li')].map((li) => Math.round(li.getBoundingClientRect().top));
  });
  const perRow = new Map<number, number>();
  for (const t of tops) perRow.set(t, (perRow.get(t) ?? 0) + 1);
  expect([...perRow.values()].every((n) => n >= 2), `cards per row: ${[...perRow.values()].join(',')}`).toBe(true);
});

// WP-62 (brand book): a card has no outline, it is the surface on the page; a list card shows a 1.5px --ink-muted edge under the pointer.
// The border is there but transparent (the box does not move on hover, and forced-colours mode draws it).
test('a card has no outline in the light and in the dark theme, its surface differs from the page, and a list card shows its edge on hover', async ({ page }) => {
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i });
  const card = page.locator('main article').first();
  const light = await card.evaluate((e) => ({ c: getComputedStyle(e).borderTopColor, bg: getComputedStyle(e).backgroundColor, page: getComputedStyle(document.body).backgroundColor }));
  expect(light.c, 'no outline at rest').toBe('rgba(0, 0, 0, 0)');
  expect(light.bg, 'the card is the surface, not the page').not.toBe(light.page);
  await card.locator('h2 a, h3 a').first().hover();
  await expect.poll(() => card.evaluate((e) => getComputedStyle(e).borderTopColor), { message: 'the edge on hover is --ink-muted' }).toBe('rgb(86, 96, 90)');
  // The pointer leaves the card, so the dark page below is read at rest.
  await page.mouse.move(0, 0);
  await page.addInitScript(() => window.localStorage.setItem('dg-theme', 'dark'));
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i });
  const dark = await page.locator('main article').first().evaluate((e) => ({ card: getComputedStyle(e).backgroundColor, page: getComputedStyle(document.body).backgroundColor, edge: getComputedStyle(e).borderTopColor }));
  expect(dark.edge, 'no outline at rest (dark)').toBe('rgba(0, 0, 0, 0)');
  expect(dark.card, 'the dark surface of the book').toBe('rgb(23, 41, 31)');
  expect(dark.page, 'the dark page of the book').toBe('rgb(15, 29, 23)');
});

// WP-62, owner's decision of 21 Oct 2026: the book's full card anatomy (padding 28, 20 px gaps, a 28/36 title) made call cards 331-371 px
// and tender cards 388-429 px at 1280. The compact card (padding 20, 12 px gaps, a 20/28 two-line title, facts as small inset cells in a
// 22rem column, provenance on one line under both) measures call 205-225, tender 220-289 at 1280, call 419-465, tender 438-553 at 375 on
// the demo data; before WP-62 it was
// call 193-233, tender 229-298 at 1280 and call 437-519, tender 457-593 at 375. The limits are the owner's targets and "no taller than before".
test('list cards are compact: a call card at most 260 px and a tender card at most 300 px (520 / 600 px at 375)', async ({ page }) => {
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i });
  const calls = await page.locator('main article').evaluateAll((a) => a.map((e) => Math.round(e.getBoundingClientRect().height)));
  expect(calls.length).toBeGreaterThan(0);
  const callMax = isMobile(page) ? 520 : 260;
  expect(Math.max(...calls), `call card heights ${calls.join(',')}`).toBeLessThanOrEqual(callMax);
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.locator('main article').first()).toBeVisible();
  const tenders = await page.locator('main article').evaluateAll((a) => a.map((e) => Math.round(e.getBoundingClientRect().height)));
  expect(tenders.length).toBeGreaterThan(0);
  expect(Math.max(...tenders), `tender card heights ${tenders.join(',')}`).toBeLessThanOrEqual(isMobile(page) ? 600 : 300);
  // the title is the card-title step, 20/28
  const title = await page.locator('main article h2').first().evaluate((e) => ({ s: getComputedStyle(e).fontSize, l: getComputedStyle(e).lineHeight }));
  expect(title).toEqual({ s: '20px', l: '28px' });
});

test('the facts of a call page are a hairline grid of at most three columns', async ({ page }) => {
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i });
  const href = await page.locator('a[href^="/funding/"]:not([href*="export"])').first().getAttribute('href');
  await visit(page, href!, { title: /DefenceGate/, h1: /.+/ });
  // WP-150: the Key facts card's grid (the page head now has a row of four short facts, the profile-head layout of a buyer page, first)
  const cols = await page.getByLabel('Key facts').locator('dl.facts-grid').first().evaluate((e) => getComputedStyle(e).gridTemplateColumns.split(' ').length);
  expect(cols).toBeLessThanOrEqual(3);
  expect(cols).toBeGreaterThanOrEqual(1);
  if (isMobile(page)) expect(cols).toBe(1);
});

test('shared interactive elements of the lists are at least 32 px high', async ({ page }) => {
  for (const path of ['/funding', '/calendar', '/market']) {
    await visit(page, path, { title: /.+/, h1: /.+/ });
    await page.waitForTimeout(300);
    const small = await page.evaluate(() => {
      const out: string[] = [];
      for (const el of Array.from(document.querySelectorAll<HTMLElement>('main a[href], main button, main summary, main select'))) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0 || getComputedStyle(el).visibility === 'hidden') continue;
        if (el.tagName === 'A' && getComputedStyle(el).display === 'inline') continue;
        if (el.closest('.sr-only')) continue;
        if (r.height < 32) out.push(`${el.tagName.toLowerCase()} "${(el.textContent ?? '').trim().slice(0, 30)}" ${Math.round(r.width)}x${Math.round(r.height)}`);
      }
      return out;
    });
    expect(small, `${path}: targets under 32 px`).toEqual([]);
  }
});
