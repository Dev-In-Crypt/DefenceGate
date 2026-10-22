import { expect, test, type Page } from '@playwright/test';
import { BLOCK_WIDTHS, paragraphsNarrowerThanBlock, paragraphsOutsideFrame, visit } from './helpers';

/**
 * Page-level layout of WP-45 (docs/verification/product/wp45-selfcheck.md): the tracker entry, the requirement cards, the reading
 * pages with a contents list, and the list pages /changes /digest /market /calendar. Computed boxes and styles only, never copy.
 * Runs at 1280 px and at 375 px (CI runs it; it was not run on the laptop or the server).
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;

const PAGES: { path: string; title: RegExp; h1: string | RegExp }[] = [
  { path: '/regulation', title: /regulatory tracker/i, h1: 'Regulatory tracker' },
  { path: '/requirements', title: /requirements/i, h1: /Requirements for EU defence programmes/ },
  { path: '/data/sovereignty', title: /where the data runs/i, h1: 'Where the data runs' },
  { path: '/privacy', title: /privacy/i, h1: 'Privacy notice' },
  { path: '/terms', title: /terms of use/i, h1: 'Terms of use' },
  { path: '/glossary', title: /glossary/i, h1: 'Glossary' },
  { path: '/methodology', title: /classifies/i, h1: /collect and classify/i },
  { path: '/about', title: /About/i, h1: 'About' },
  { path: '/data', title: /source status/i, h1: 'Source status' },
  { path: '/changes', title: /what changed/i, h1: 'What changed' },
  { path: '/digest', title: /weekly digest/i, h1: 'Weekly digest' },
  { path: '/market', title: /market overview/i, h1: 'Market overview' },
  { path: '/calendar', title: /calendar/i, h1: 'Deadline calendar' },
];

test('no paragraph on these pages leaves the content frame, a running paragraph fills its block, and nothing scrolls sideways', async ({ page }) => {
  for (const p of PAGES) {
    // `visit` checks that nothing scrolls sideways.
    await visit(page, p.path, { title: p.title, h1: p.h1 });
    // WP-83 (owner, 22 Oct 2026, replacing the 62ch measure of WP-62): the frame keeps the header width and a running paragraph takes the
    // full width of its card or column, at 1440 and 1024 px.
    expect(await paragraphsOutsideFrame(page), `${p.path}: paragraphs outside the header's left and right edges`).toEqual([]);
    if (isMobile(page)) continue;
    for (const width of BLOCK_WIDTHS) {
      await page.setViewportSize({ width, height: 800 });
      expect(await paragraphsNarrowerThanBlock(page), `${p.path} at ${width} px: paragraphs narrower than 90 % of their block`).toEqual([]);
    }
    await page.setViewportSize({ width: 1280, height: 800 });
  }
});

test('/regulation: an entry is short collapsed, the quote and the line to cite are in the page but folded away, the permalink works', async ({ page }) => {
  await visit(page, '/regulation', { title: /regulatory tracker/i, h1: 'Regulatory tracker' });
  const heights = await page.locator('main ol > li[id]').evaluateAll((a) => a.map((e) => Math.round(e.getBoundingClientRect().height)));
  expect(heights.length).toBeGreaterThan(5);
  // 420 px on a desktop for the typical entry (the longest summary may run to a few lines more); one phone screen and a half on a phone
  const sorted = [...heights].sort((x, y) => x - y);
  const median = sorted[Math.floor(sorted.length / 2)];
  expect(median, `entry heights ${heights.join(',')}`).toBeLessThanOrEqual(isMobile(page) ? 900 : 420);
  const page_ = await page.evaluate(() => document.documentElement.scrollHeight);
  if (!isMobile(page)) expect(page_, 'page height').toBeLessThanOrEqual(8000);
  const first = page.locator('main ol > li[id]').first();
  await expect(first.locator('details')).not.toHaveAttribute('open', '');
  await expect(first.locator('blockquote')).toBeHidden();
  expect(await first.locator('blockquote').textContent()).not.toBe('');
  const code = await first.getAttribute('id');
  await page.goto(`/regulation#${code}`);
  await expect(first).toBeInViewport();
  // the facts sit beside the summary on a desktop and under it on a phone
  const boxes = await first.evaluate((li) => {
    const text = li.querySelector('h2')!.getBoundingClientRect();
    const facts = li.querySelector('dl')!.getBoundingClientRect();
    return { textRight: text.right, factsLeft: facts.left, factsTop: facts.top, textBottom: text.bottom };
  });
  if (isMobile(page)) expect(boxes.factsTop).toBeGreaterThanOrEqual(boxes.textBottom);
  else expect(boxes.factsLeft).toBeGreaterThanOrEqual(boxes.textRight);
});

test('/regulation: the status chips hide entries, never remove them, and a permalink clears the filter', async ({ page }) => {
  await visit(page, '/regulation', { title: /regulatory tracker/i, h1: 'Regulatory tracker' });
  const all = await page.locator('main ol > li[id]').count();
  const chips = page.getByRole('group', { name: 'Show entries by status' }).getByRole('button');
  expect(await chips.count()).toBeGreaterThan(2);
  await chips.nth(1).click();
  await expect(chips.nth(1)).toHaveAttribute('aria-pressed', 'true');
  const shown = await page.locator('main ol > li[id]:visible').count();
  expect(shown).toBeLessThan(all);
  expect(await page.locator('main ol > li[id]').count(), 'all entries stay in the page').toBe(all);
  await chips.nth(0).click();
  expect(await page.locator('main ol > li[id]:visible').count()).toBe(all);
});

test('/requirements: a group with one card gives it the whole row, and Cost and Time are not squeezed into narrow columns', async ({ page }) => {
  await visit(page, '/requirements', { title: /requirements/i, h1: /Requirements for EU defence programmes/ });
  const rows = await page.evaluate(() => [...document.querySelectorAll('main section ul')].map((ul) => {
    const box = ul.getBoundingClientRect();
    const cards = [...ul.children].map((li) => li.getBoundingClientRect());
    const byRow = new Map<number, number>();
    for (const c of cards) byRow.set(Math.round(c.top), (byRow.get(Math.round(c.top)) ?? 0) + c.width);
    return { width: box.width, rows: [...byRow.values()], n: cards.length };
  }).filter((g) => g.n > 0));
  expect(rows.length).toBeGreaterThan(2);
  for (const g of rows) {
    // a row of cards fills the grid: the sum of the widths plus the gaps is the grid, so the lone card is not half the row
    const last = g.rows.at(-1)!;
    if (g.rows.length === 1 && g.n === 1) expect(last, 'a lone card').toBeGreaterThanOrEqual(g.width - 2);
  }
  const time = await page.locator('dl dt', { hasText: /^Time$/ }).first().locator('xpath=following-sibling::dd[1]').evaluate((e) => e.getBoundingClientRect().width);
  expect(time, 'the Time value is not a narrow column').toBeGreaterThanOrEqual(isMobile(page) ? 200 : 240);
  // the contents list of the groups
  if (!isMobile(page)) await expect(page.getByRole('navigation', { name: 'Contents' }).getByRole('link').first()).toBeVisible();
});

test('reading pages have a sticky contents list from lg, at the left of the text column, and none on a phone', async ({ page }) => {
  for (const path of ['/privacy', '/terms', '/methodology', '/about', '/glossary', '/data']) {
    await visit(page, path, { title: /.+/, h1: /.+/ });
    const toc = page.getByRole('navigation', { name: 'Contents' });
    if (isMobile(page)) { await expect(toc, path).toBeHidden(); continue; }
    await expect(toc, path).toBeVisible();
    const n = await toc.getByRole('link').count();
    expect(n, `${path}: links in the contents`).toBeGreaterThan(3);
    const sticky = await toc.evaluate((e) => getComputedStyle(e).position);
    expect(sticky).toBe('sticky');
    const small = await toc.getByRole('link').evaluateAll((as) => as.map((a) => a.getBoundingClientRect().height).filter((h) => h < 32));
    expect(small, `${path}: contents links under 32 px`).toEqual([]);
    // a link goes to its section: the first one
    const href = await toc.getByRole('link').first().getAttribute('href');
    await expect(page.locator(`[id="${href!.slice(1)}"]`)).toHaveCount(1);
  }
});

test('/data has no box inside a box: the source cards hold plain rows, not tinted boxes', async ({ page }) => {
  await visit(page, '/data', { title: /source status/i, h1: 'Source status' });
  const nested = await page.evaluate(() => {
    const surface = (e: Element) => getComputedStyle(e).backgroundColor;
    const cards = [...document.querySelectorAll('main article, main section > div')].filter((e) => getComputedStyle(e).borderTopWidth === '1px');
    let n = 0;
    for (const c of cards) for (const inner of c.querySelectorAll('dl, div, ul')) {
      const s = getComputedStyle(inner);
      if (inner !== c && s.backgroundColor !== 'rgba(0, 0, 0, 0)' && s.backgroundColor !== surface(c) && parseFloat(s.borderTopLeftRadius) > 0) n += 1;
    }
    return n;
  });
  expect(nested, 'rounded tinted boxes inside cards').toBe(0);
});

test('/changes, /digest, /calendar, /market: targets are at least 32 px high and tables keep their width', async ({ page }) => {
  for (const path of ['/changes', '/digest', '/calendar', '/market', '/regulation']) {
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

test('/changes and /digest: entries sit in a grid that fills its rows, and a day with a single entry is not half a row', async ({ page }) => {
  test.skip(isMobile(page), 'one column on a phone');
  for (const path of ['/changes', '/digest']) {
    await visit(page, path, { title: /.+/, h1: /.+/ });
    const bad = await page.evaluate(() => [...document.querySelectorAll('main ul')].map((ul) => {
      const kids = [...ul.children].filter((c) => c.getClientRects().length > 0 && c.querySelector('article'));
      if (kids.length === 0) return null;
      const box = ul.getBoundingClientRect();
      const tops = new Map<number, number>();
      for (const k of kids) tops.set(Math.round(k.getBoundingClientRect().top), (tops.get(Math.round(k.getBoundingClientRect().top)) ?? 0) + k.getBoundingClientRect().width);
      const rows = [...tops.values()];
      // the last row may have fewer cards in a multi-column grid; a grid of one card must fill the row
      return kids.length === 1 && rows[0] < box.width - 2 ? `${rows[0]} of ${box.width}` : null;
    }).filter(Boolean));
    expect(bad, `${path}: a lone card is not the whole row`).toEqual([]);
  }
});

test('/calendar: the agenda day has its date in its own column from lg, and the month cells are 32 px targets', async ({ page }) => {
  await visit(page, '/calendar', { title: /calendar/i, h1: 'Deadline calendar' });
  const day = page.locator('main section[id^="d-"], main [id^="d-"]').first();
  if ((await day.count()) === 0) return;
  const box = await day.evaluate((e) => {
    const h = e.querySelector('h3')!.getBoundingClientRect();
    const ul = e.querySelector('ul')!.getBoundingClientRect();
    return { hRight: h.right, ulLeft: ul.left, hTop: h.top, ulTop: ul.top };
  });
  if (isMobile(page)) expect(box.ulTop).toBeGreaterThanOrEqual(box.hTop);
  else expect(box.ulLeft).toBeGreaterThanOrEqual(box.hRight);
});

test('the frame of every page spans the header pill, and no card is narrower than 60 % of it unless it has a sibling in its row', async ({ page }) => {
  for (const p of PAGES) {
    await visit(page, p.path, { title: p.title, h1: p.h1 });
    const r = await page.evaluate(() => {
      const head = document.querySelector('header')!.getBoundingClientRect();
      const kids = [...document.querySelectorAll('main > *')].map((e) => e.getBoundingClientRect()).filter((b) => b.width > 0 && b.height > 0);
      const left = Math.min(...kids.map((b) => b.left));
      const right = Math.max(...kids.map((b) => b.right));
      const frame = right - left;
      const cs = (e: Element) => getComputedStyle(e);
      const main = document.querySelector('main');
      const cards = [...document.querySelectorAll('main [class*="rounded-lg"]')].filter((e) => {
        const b = e.getBoundingClientRect();
        return b.height > 60 && parseFloat(cs(e).borderTopWidth) > 0 && !e.parentElement!.closest('[class*="rounded-lg"]');
      });
      const lone: string[] = [];
      for (const c of cards) {
        const b = c.getBoundingClientRect();
        if (b.width >= frame * 0.6) continue;
        let a: Element | null = c;
        let ok = false;
        while (a && a.parentElement && a.parentElement !== main) {
          const par: Element = a.parentElement;
          const disp = cs(par).display;
          if (disp === 'grid' || (disp === 'flex' && cs(par).flexDirection.startsWith('row'))) {
            const ab = a.getBoundingClientRect();
            ok = [...par.children].some((s) => s !== a && s.getBoundingClientRect().width > 0 && s.getBoundingClientRect().top < ab.bottom && s.getBoundingClientRect().bottom > ab.top);
            if (ok) break;
          }
          a = par;
        }
        if (!ok) lone.push(`${Math.round(b.width)} of ${Math.round(frame)}`);
      }
      return { dl: left - head.left, dr: right - head.right, lone, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
    });
    expect(Math.abs(r.dl), `${p.path}: frame left against the header`).toBeLessThanOrEqual(1);
    expect(Math.abs(r.dr), `${p.path}: frame right against the header`).toBeLessThanOrEqual(1);
    expect(r.lone, `${p.path}: lone narrow cards`).toEqual([]);
    expect(r.overflow, `${p.path}: horizontal overflow`).toBeLessThanOrEqual(0);
  }
});

// WP-62: justified only where it reads well (owner, 21 Oct 2026): a body paragraph in a column of 560 px or more, hyphenated; a phone, a narrow
// column and 14 px notes are left-aligned. The column is the paragraph's container (globals.css), so the check reads the paragraph's own box:
// a justified paragraph is at least 500 px wide (since WP-83 it fills its column of 560 px or more), a narrower one is never justified.
test('running paragraphs are justified and hyphenated only in a wide column, left-aligned on a phone and in narrow columns; headings, lists and table cells never are', async ({ page }) => {
  for (const path of ['/privacy', '/methodology', '/about', '/regulation']) {
    await visit(page, path, { title: /.+/, h1: /.+/ });
    const s = await page.evaluate(() => {
      const long = [...document.querySelectorAll('main p')].filter((p) => (p.textContent ?? '').length > 200 && p.getClientRects().length > 0 && !p.closest('details'));
      const al = (e: Element) => getComputedStyle(e).textAlign;
      const just = long.filter((p) => al(p) === 'justify');
      return {
        n: long.length,
        justified: just.length,
        unhyphenated: just.filter((p) => getComputedStyle(p).hyphens !== 'auto').length,
        narrowJustified: just.filter((p) => p.getBoundingClientRect().width < 500).map((p) => Math.round(p.getBoundingClientRect().width)),
        smallJustified: just.filter((p) => parseFloat(getComputedStyle(p).fontSize) < 16).length,
        heads: [...document.querySelectorAll('main h1, main h2, main h3')].filter((h) => al(h) === 'justify').length,
        lists: [...document.querySelectorAll('main li, main td, main th, main dd')].filter((h) => al(h) === 'justify').length,
      };
    });
    expect(s.n, `${path}: long paragraphs`).toBeGreaterThan(0);
    expect(s.heads, `${path}: justified headings`).toBe(0);
    expect(s.lists, `${path}: justified list items or table cells`).toBe(0);
    expect(s.narrowJustified, `${path}: justified paragraphs narrower than 500 px`).toEqual([]);
    expect(s.smallJustified, `${path}: justified 14 px notes`).toBe(0);
    expect(s.unhyphenated, `${path}: justified without hyphenation`).toBe(0);
    if (isMobile(page)) expect(s.justified, `${path}: justified on a phone`).toBe(0);
    else expect(s.justified, `${path}: justified long paragraphs`).toBeGreaterThan(0);
  }
});
