import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * The layout foundation of WP-44 (docs/verification/product/wp44-selfcheck.md): one measure, the page-header scale, a card that reads as a
 * card, rhythm between sections, a grid that does not leave a half-empty row, and list cards that are short. Every check reads computed
 * styles or boxes, never copy. Runs at 1280 px and at 375 px (CI runs it; it was not run on the laptop).
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const px = (v: string) => parseFloat(v);

test('the page container is centred, with gutters of 16 px on a phone and 32 px from 1024 px, and never wider than 1360 px', async ({ page }) => {
  await visit(page, '/about', { title: /About/i, h1: 'About' });
  const box = await page.evaluate(() => {
    const m = document.querySelector('main')!;
    const r = m.getBoundingClientRect();
    const s = getComputedStyle(m);
    return { left: r.left, right: document.documentElement.clientWidth - r.right, width: r.width, pad: parseFloat(s.paddingLeft) };
  });
  expect(Math.abs(box.left - box.right), 'left and right margin are equal').toBeLessThanOrEqual(1);
  expect(box.width).toBeLessThanOrEqual(1360);
  expect(box.pad).toBe(isMobile(page) ? 16 : 32);
});

test('the page title is 36/44 (32/40 on a phone) and the lead is larger than the body and in the ink colour', async ({ page }) => {
  await visit(page, '/about', { title: /About/i, h1: 'About' });
  const t = await page.evaluate(() => {
    const h1 = document.querySelector('main h1')!;
    const lead = document.querySelector('main h1 + p')!;
    const body = getComputedStyle(document.body);
    const ls = getComputedStyle(lead);
    const hs = getComputedStyle(h1);
    return { h1: hs.fontSize, h1lh: hs.lineHeight, lead: ls.fontSize, leadColor: ls.color, ink: body.color };
  });
  expect(t.h1).toBe(isMobile(page) ? '32px' : '36px');
  expect(t.h1lh).toBe(isMobile(page) ? '40px' : '44px');
  expect(px(t.lead)).toBeGreaterThan(16);
  expect(t.leadColor, 'the lead is not the muted grey').toBe(t.ink);
});

test('text-h4 is defined: the three questions on the home page are headings, not plain text', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Defence and dual-use tenders and funding' });
  const h = page.getByRole('heading', { name: /What is open to me\?/ }).first();
  await expect(h).toBeVisible();
  const style = await h.evaluate((e) => ({ size: getComputedStyle(e).fontSize, weight: getComputedStyle(e).fontWeight }));
  expect(style.size).toBe('18px');
  expect(Number(style.weight)).toBeGreaterThanOrEqual(600);
});

test('no paragraph of a reading page is wider than the reading measure (680 px), and the page is a centred column', async ({ page }) => {
  for (const path of ['/about', '/methodology', '/privacy', '/glossary']) {
    await visit(page, path, { title: /.+/, h1: /.+/ });
    const wide = await page.evaluate(() => [...document.querySelectorAll('main p')]
      .map((p) => ({ w: p.getBoundingClientRect().width, t: (p.textContent ?? '').trim().slice(0, 30) }))
      .filter((p) => p.w > 681));
    expect(wide, `${path}: paragraphs wider than 680 px`).toEqual([]);
    const col = await page.evaluate(() => {
      const r = document.querySelector('main h1')!.closest('div')!.getBoundingClientRect();
      return { w: r.width, left: r.left, right: document.documentElement.clientWidth - r.right };
    });
    if (!isMobile(page)) {
      expect(col.w, `${path}: the reading column`).toBeLessThanOrEqual(990);
      expect(Math.abs(col.left - col.right), `${path}: the column is centred`).toBeLessThanOrEqual(2);
    }
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

test('a card has a 1px edge in the light and in the dark theme, and the dark card is lighter than the page', async ({ page }) => {
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i });
  const light = await page.locator('main article').first().evaluate((e) => ({ w: getComputedStyle(e).borderTopWidth, c: getComputedStyle(e).borderTopColor }));
  expect(light.w).toBe('1px');
  expect(light.c).not.toBe('rgba(0, 0, 0, 0)');
  await page.addInitScript(() => window.localStorage.setItem('dg-theme', 'dark'));
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i });
  const dark = await page.locator('main article').first().evaluate((e) => ({ card: getComputedStyle(e).backgroundColor, page: getComputedStyle(document.body).backgroundColor, edge: getComputedStyle(e).borderTopColor }));
  const lum = (rgb: string) => {
    const c = (rgb.match(/\d+/g) ?? ['0', '0', '0']).slice(0, 3).map((v) => Number(v) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const ratio = (a: string, b: string) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  expect(ratio(dark.card, dark.page), 'dark card against the page').toBeGreaterThanOrEqual(1.25);
  expect(ratio(dark.edge, dark.page), 'dark card edge against the page').toBeGreaterThanOrEqual(1.4);
});

test('list cards are short: a call card at most 300 px and a tender card at most 340 px (650 px at 375)', async ({ page }) => {
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i });
  const calls = await page.locator('main article').evaluateAll((a) => a.map((e) => Math.round(e.getBoundingClientRect().height)));
  expect(calls.length).toBeGreaterThan(0);
  const callMax = isMobile(page) ? 650 : 300;
  expect(Math.max(...calls), `call card heights ${calls.join(',')}`).toBeLessThanOrEqual(callMax);
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.locator('main article').first()).toBeVisible();
  const tenders = await page.locator('main article').evaluateAll((a) => a.map((e) => Math.round(e.getBoundingClientRect().height)));
  expect(tenders.length).toBeGreaterThan(0);
  expect(Math.max(...tenders), `tender card heights ${tenders.join(',')}`).toBeLessThanOrEqual(isMobile(page) ? 650 : 340);
  // the title is 20/28, not the old 28/36
  const title = await page.locator('main article h2').first().evaluate((e) => ({ s: getComputedStyle(e).fontSize, l: getComputedStyle(e).lineHeight }));
  expect(title).toEqual({ s: '20px', l: '28px' });
});

test('the facts of a call page are a hairline grid of at most three columns', async ({ page }) => {
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i });
  const href = await page.locator('a[href^="/funding/"]:not([href*="export"])').first().getAttribute('href');
  await visit(page, href!, { title: /DefenceGate/, h1: /.+/ });
  const cols = await page.locator('dl.facts-grid').first().evaluate((e) => getComputedStyle(e).gridTemplateColumns.split(' ').length);
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
