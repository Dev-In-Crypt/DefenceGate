import { expect, test, type Locator } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-175 (QA of 24 November 2026, organisations and market data) on the demo build: a table's row starts its name and its figures on
 * one line (D-1, F-2, F07: the name sat at the bottom of its row, beside the next row's numbers), at 1280 and at 375 (both projects);
 * the competitors' column headers sit on one line (F-3); the buyer page counts the names it can show (D-6); the Ukraine partners page
 * says what its table holds (D-12, F04, D-13); the consortium gaps say when the country takes part in no project of the area (D-14);
 * /networks is no 404 (D-19); the market's buyer table has its heading (D-22).
 */

/** WP175_SHOTS (a folder): the after-screenshots of the self-check, per project. */
async function shot(page: import('@playwright/test').Page, name: string): Promise<void> {
  const dir = process.env.WP175_SHOTS;
  if (dir) await page.screenshot({ path: `${dir}/${name}-${test.info().project.name}.png`, fullPage: true });
}

/** Every body row of the table: the top of its first cell and of its other cells are the same (within 6 px). */
async function rowsTopAligned(table: Locator): Promise<void> {
  const off = await table.evaluate((t) => [...t.querySelectorAll('tbody tr')].map((tr) => {
    const cells = [...tr.children] as HTMLElement[];
    // a name of several lines, whatever the demo data: the row header is made narrow, so the alignment shows
    Object.assign(cells[0].style, { minWidth: '0', width: '60px', maxWidth: '60px' });
    // the top of a cell's first line of text (its box would count the padding, a link inside it would not)
    // (the first text node: an element's box, a badge's padding, would not be the text's line)
    const top = (c: HTMLElement) => {
      const walk = document.createTreeWalker(c, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.textContent?.trim() ? 1 : 2) });
      const text = walk.nextNode();
      if (!text) return null;
      const r = document.createRange();
      r.selectNodeContents(text);
      const rect = [...r.getClientRects()].find((x) => x.height > 0);
      return rect ? rect.top + rect.height / 2 - (parseFloat(getComputedStyle(text.parentElement!).lineHeight) || rect.height) / 2 : null;
    };
    const first = top(cells[0]);
    const others = cells.slice(1).map(top).filter((t): t is number => t !== null);
    return first === null || !others.length ? 0 : Math.max(...others.map((t) => Math.abs(t - first)));
  }));
  expect(off.length).toBeGreaterThan(0);
  for (const d of off) expect(d, 'a row header and its figures start on one line').toBeLessThanOrEqual(6);   // fonts differ by a pixel or two; the defect was a whole line (20 px and more)
}

test('D-1: the buyer page\'s top suppliers and the market\'s value tables start each row on one line', async ({ page }) => {
  await visit(page, '/buyers/1-demo-armaments-agency', { title: /Demo Armaments Agency/i, h1: 'Demo Armaments Agency' });
  const top = page.locator('table').filter({ has: page.locator('[data-top-supplier-value]') });
  await shot(page, 'after-buyer');
  if (await top.count()) await rowsTopAligned(top.first());
  await visit(page, '/market', { title: /Market overview/, h1: 'Market overview' });
  for (const t of await page.locator('[data-market-money] table').all()) await rowsTopAligned(t);
});

test('D-1, F-3: a supplier page\'s tables are top-aligned and the competitors\' headers keep one line', async ({ page }) => {
  await visit(page, '/suppliers/1-demo-airframes-gmbh', { title: /Demo Airframes/i, h1: 'Demo Airframes GmbH' });
  await shot(page, 'after-supplier');
  const competitors = page.locator('section[aria-labelledby="competitors"] table');
  await rowsTopAligned(competitors);
  await rowsTopAligned(page.locator('section[aria-labelledby="share"] table'));
  const heights = await competitors.locator('thead th').evaluateAll((ths) => ths.slice(1).map((th) => (th as HTMLElement).offsetHeight));
  const line = await competitors.locator('thead th').first().evaluate((th) => (th as HTMLElement).offsetHeight);
  for (const h of heights) expect(h).toBeLessThanOrEqual(line + 2);
});

test('D-6: the buyer page counts the names it shows and the records behind them', async ({ page }) => {
  await visit(page, '/buyers/1-demo-armaments-agency', { title: /Demo Armaments Agency/i, h1: 'Demo Armaments Agency' });
  await expect(page.locator('[data-variant-names] summary')).toHaveText('Published under 2 other names (2 other records of this body): show the names');
});

test('D-12, D-13: the Ukraine partners page says what its table holds, with headers that read', async ({ page }) => {
  await visit(page, '/networks/ukraine-partners?programme=all', { title: /Ukrainian/, h1: 'Ukraine partners' });
  await shot(page, 'after-ukraine-partners');
  await expect(page.getByText('primes that already work with Ukrainian companies')).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Projects, latest start' })).toBeVisible();
  await expect(page.locator('[data-ua-latest]').first()).toHaveText(/^latest \d{4}$/);
});

test('D-14: the consortium gaps say when nobody from the country took part in the area', async ({ page }) => {
  await visit(page, '/networks/consortium-gaps', { title: /consortium|Repeat participants/i, h1: 'Consortium gaps' });
  await shot(page, 'after-consortium-gaps');
  await expect(page.locator('[data-gaps-none]')).toContainText('No project of this area has a participant from Ukraine at all');
  await expect(page.locator('[data-ua-partners-link]')).toContainText('coordinated: Ukraine partners');
  await visit(page, '/networks/consortium-gaps?lacking=FR', { title: /consortium|Repeat participants/i, h1: 'Consortium gaps' });
  await expect(page.locator('[data-gaps-none]')).toHaveCount(0);
});

test('D-19: /networks leads to the organisations, not to a 404', async ({ page }) => {
  await visit(page, '/networks', { title: /Organisations|Companies/, h1: 'Companies' });
  await expect(page).toHaveURL(/\/organisations$/);
});

test('D-22: the market\'s buyer value table has its own heading', async ({ page }) => {
  await visit(page, '/market', { title: /Market overview/, h1: 'Market overview' });
  await shot(page, 'after-market');
  const heading = page.locator('[data-money-buyers-heading]');
  if (await page.locator('[data-money-buyer]').count()) await expect(heading).toHaveText('Buyers with the most contracts that state a value');
});
