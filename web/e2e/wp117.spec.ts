import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-117 (docs/verification/home/wp117-selfcheck.md): the simpler home page of the owner's option A (25 October 2026). The owner's
 * headline and lead, one search, three question tiles with live counts, two short closing-soon lists, a trust line, the digest
 * without an e-mail field and four questions; "Why DefenceGate", "How it works" and the full FAQ moved to /about. The menu has four items.
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const LEAD = 'Defence and dual-use tenders and EU funding calls, the companies already in EU-funded projects, and a five-question check against EDF, EDIP and SAFE rules. Free to browse, every fact linked to its source.';
const ldOf = (page: Page) => page.locator('script[type="application/ld+json"]').evaluateAll((s) => s.map((n) => JSON.parse(n.textContent ?? '{}')));
const faqOf = async (page: Page) => ((await ldOf(page)).find((b) => b['@type'] === 'FAQPage')?.mainEntity ?? []).map((q: { name: string }) => q.name) as string[];
/** "Showing 1–20 of 1,234 tenders": the list's own total. */
const listTotal = async (page: Page, path: string) => {
  await visit(page, path, { title: /.+/, h1: /.+/ });
  return (await page.locator('#results-heading').innerText()).match(/of ([\d,]+)/)![1];
};

test('home: the owner’s headline and lead, one search and nothing else in the hero', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  const hero = page.locator('section[aria-labelledby="hero"]');
  await expect(hero.locator('h1')).toHaveText('Win, partner, qualify. Across Europe’s defence market.');
  await expect(hero.locator('p').first()).toHaveText(LEAD);
  await expect(hero.getByRole('search')).toHaveCount(1);
  await expect(hero.getByRole('link')).toHaveCount(0);
  await expect(hero.getByRole('button')).toHaveText(['Search']);
  // no statistics row, no examples, no CPV link, no "Why DefenceGate" on the home page
  await expect(page.locator('main dl')).toHaveCount(0);
  await expect(page.locator('#main a[href="/cpv"]')).toHaveCount(0);
  for (const name of ['Why DefenceGate', 'How it works', 'Three questions, three parts', /What changed in the last/, 'Save searches and keep a shortlist']) {
    await expect(page.getByRole('heading', { name }), String(name)).toHaveCount(0);
  }
});

test('home: exactly three tiles, each one link to its page, with the live counts of those pages', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  const tiles = page.locator('[data-tile]');
  await expect(tiles).toHaveCount(3);
  const hrefs = await tiles.evaluateAll((els) => els.map((e) => e.getAttribute('href')));
  expect(hrefs).toEqual(['/tenders', '/companies', '/check']);
  for (const [name, href] of [[/What is open\? Find tenders and funding/, '/tenders'], [/Who is already in\? Find partners/, '/companies'], [/Can I take part\? Check if my company qualifies/, '/check']] as const) {
    await expect(page.getByRole('link', { name }), String(name)).toHaveAttribute('href', href);
  }
  // the tile is the link: nothing else to click inside it
  for (const t of await tiles.all()) await expect(t.locator('a, button, input')).toHaveCount(0);
  const figure = (i: number, label: RegExp) => tiles.nth(i).locator('[data-figure]').filter({ hasText: label }).locator(':scope > span:first-child').innerText();
  const tenders = await figure(0, /open tenders?$/);
  const calls = await figure(0, /open funding calls?$/);
  const companies = await figure(1, /won contracts$/);
  await expect(tiles.nth(2)).toContainText('Five short sets of questions');
  await expect(tiles.nth(2).locator('[data-figure]')).toContainText('5');
  // the same numbers as the lists the tiles lead to (never hard-coded)
  expect(tenders).toBe(await listTotal(page, '/tenders'));
  expect(calls).toBe(await listTotal(page, '/funding'));
  // the supplier map's own count ("How we count: N suppliers and M wins …", the same summary)
  await visit(page, '/suppliers', { title: /.+/, h1: 'Companies' });
  expect(await page.locator('#main').textContent()).toContain(`${companies} supplier`);
  // the supplier route that /check leads to
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  await expect(page.getByText('Make parts or provide services?')).toBeVisible();
  await expect(page.getByRole('link', { name: 'See who buys what you make' })).toHaveAttribute('href', '/readiness/supplier');
  // keyboard: the tile takes focus and shows it
  const first = page.locator('[data-tile]').first();
  await page.locator('#home-search').focus();
  await page.keyboard.press('Tab');   // the Search button
  await page.keyboard.press('Tab');
  await expect(first).toBeFocused();
  expect(await first.evaluate((e) => getComputedStyle(e).outlineStyle)).not.toBe('none');
});

test('home: the closing-soon lists have at most three compact rows and a link to the full list', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  for (const [id, href, more] of [['closing-tenders', '/tenders', /^All [\d,]+ open tenders?$/], ['closing', '/funding', /^All [\d,]+ open calls?$/]] as const) {
    const list = page.locator(`section[aria-labelledby="${id}"]`);
    const rows = list.locator('li');
    expect(await rows.count(), id).toBeGreaterThan(0);
    expect(await rows.count(), id).toBeLessThanOrEqual(3);
    // each row: one link (the title), its deadline with days left and the date
    for (const r of await rows.all()) {
      await expect(r.getByRole('link')).toHaveCount(1);
      await expect(r.locator('time')).toHaveCount(1);
    }
    for (const word of [/licen[cs]e/i, /confidence/i, /why this is here/i, /original title/i, /View original/i, /Notice ID/i]) await expect(list, `${id}: ${word}`).not.toContainText(word);
    await expect(list.getByRole('link', { name: more })).toHaveAttribute('href', href);
  }
  await expect(page.getByRole('heading', { name: 'Tenders closing soon' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Funding closing soon' })).toBeVisible();
  if (!isMobile(page)) {
    // side by side on a wide screen
    const a = await page.locator('section[aria-labelledby="closing-tenders"]').boundingBox();
    const b = await page.locator('section[aria-labelledby="closing"]').boundingBox();
    expect(Math.abs(a!.y - b!.y)).toBeLessThanOrEqual(1);
  }
});

test('home: the trust line, the digest without an e-mail field, four questions and a link to the rest', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  const trust = page.getByRole('region', { name: 'About the data' });
  await expect(trust.locator('[data-trust="sources"]')).toContainText(/^\d+ sources? \(TED and national portals\)$/);
  await expect(trust.locator('[data-trust="update"]')).toContainText(/^Last update \d{1,2} \w{3} \d{4}, \d{2}:\d{2} UTC$/);
  await expect(trust.getByRole('link', { name: 'Methodology' })).toHaveAttribute('href', '/methodology');
  await expect(trust.getByRole('link', { name: 'Source status' })).toHaveAttribute('href', '/data');
  const digest = page.locator('section[aria-labelledby="digest"]');
  await expect(digest.getByRole('link', { name: 'Read the latest digest' })).toHaveAttribute('href', '/digest');
  await expect(digest.getByRole('link', { name: 'Atom feed' })).toHaveAttribute('href', '/digest.atom');
  await expect(digest.locator('input, form')).toHaveCount(0);
  await expect(page.locator('main input[type="email"]')).toHaveCount(0);
  const faq = page.locator('section[aria-labelledby="faq"]');
  const asked = await faq.locator('summary').allInnerTexts();
  expect(asked.length).toBeLessThanOrEqual(4);
  expect(asked.map((q) => q.trim())).toEqual(['Is it free?', 'Where does the data come from?', 'How current is it?', 'How do you decide what counts as defence or dual-use?']);
  await expect(faq.getByRole('link', { name: 'More questions' })).toHaveAttribute('href', '/about');
  // the structured data names only the questions on the page
  expect(await faqOf(page)).toEqual(asked.map((q) => q.trim()));
});

test('/about carries Why DefenceGate, How it works and every question; its structured data the ones home does not show', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  const home = await faqOf(page);
  await visit(page, '/about', { title: /About/i, h1: 'About DefenceGate' });
  await expect(page.getByRole('heading', { name: 'Why DefenceGate', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Many portals, one list' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'How it works', exact: true })).toBeVisible();
  for (const name of ['We collect', 'You search and filter', 'You verify and act']) await expect(page.getByRole('heading', { name })).toBeVisible();
  const faq = page.locator('section[aria-labelledby="faq"]');
  const asked = (await faq.locator('summary').allInnerTexts()).map((q) => q.trim());
  expect(asked).toHaveLength(11);
  for (const q of home) expect(asked, q).toContain(q);
  await expect(page.getByRole('complementary', { name: 'Please note' })).toBeVisible();
  const ld = await faqOf(page);
  expect(ld.filter((q) => home.includes(q))).toEqual([]);
  expect([...home, ...ld].sort()).toEqual([...asked].sort());
});

test('the header has four items (by the three questions and What’s new)', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  if (isMobile(page)) {
    await page.getByRole('button', { name: 'Open menu' }).click();
    const menu = page.getByRole('navigation', { name: 'Main menu' });
    for (const name of ['Tenders & funding', 'Partners', 'What’s new']) await expect(menu.getByText(name, { exact: true })).toBeVisible();
    await expect(menu.getByRole('link', { name: 'Check my company', exact: true })).toBeVisible();
    return;
  }
  const nav = page.getByRole('navigation', { name: 'Main' });
  await expect(nav.locator(':scope > *')).toHaveCount(4);
  await expect(nav.locator(':scope > * > :first-child')).toHaveText(['Tenders & funding', 'Partners', 'Check my company', 'What’s new']);
});

test('home at 375 px: no horizontal scroll; the tiles and the lists stack', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  const w = await page.evaluate(() => ({ s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth }));
  expect(w.s).toBeLessThanOrEqual(w.c);
  const lefts = await page.locator('[data-tile]').evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().left)));
  expect(new Set(lefts).size, 'one column of tiles').toBe(1);
  const a = await page.locator('section[aria-labelledby="closing-tenders"]').boundingBox();
  const b = await page.locator('section[aria-labelledby="closing"]').boundingBox();
  expect(b!.y, 'the funding list under the tenders list').toBeGreaterThanOrEqual(a!.y + a!.height);
});

test('home in the dark theme: the page, the tiles and the lists take the dark colours', async ({ browser }) => {
  const context = await browser.newContext({ colorScheme: 'dark' });
  const page = await context.newPage();
  await page.goto('/', { waitUntil: 'load' });
  const m = await page.evaluate(() => {
    const bg = (el: Element) => getComputedStyle(el).backgroundColor;
    const lum = (c: string) => { const [r, g, b] = (c.match(/\d+/g) ?? ['0', '0', '0']).slice(0, 3).map(Number); return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255; };
    const tile = document.querySelector('[data-tile]')!;
    const list = document.querySelector('section[aria-labelledby="closing-tenders"] ul')!;
    return { theme: document.documentElement.dataset.theme, body: lum(bg(document.body)), tile: lum(bg(tile)), list: lum(bg(list)), ink: lum(getComputedStyle(document.querySelector('h1')!).color) };
  });
  expect(m.theme).toBe('dark');
  expect(m.body, 'a dark page').toBeLessThan(0.3);
  expect(m.tile, 'a dark tile').toBeLessThan(0.3);
  expect(m.list, 'a dark list').toBeLessThan(0.3);
  expect(m.ink, 'light text').toBeGreaterThan(0.7);
  await context.close();
});
