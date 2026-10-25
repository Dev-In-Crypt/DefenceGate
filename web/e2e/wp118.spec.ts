import { expect, test, type Locator, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-118 (docs/verification/home/wp118-selfcheck.md, owner's screenshot of 25 October 2026): a card that is one link shows its hover
 * (and keyboard focus) on its box, and no text inside it is underlined; a text link inside a card underlines on its own hover only.
 * Before, `a:hover { text-decoration: underline }` (0,1,1) beat every link's `no-underline` (0,1,0) and the decoration reached every line
 * of a homepage tile. Hover is a pointer state: the desktop project only.
 */

test.skip(({ isMobile }) => isMobile, 'hover is a pointer state');
test.beforeEach(async ({ page }) => { await page.emulateMedia({ reducedMotion: 'reduce' }); });

/** The box's look (border, background, shadow) and every element in or around it whose own text decoration is an underline. */
function readCard(card: Locator) {
  return card.evaluate((root) => {
    const ul = (e: Element) => getComputedStyle(e).textDecorationLine.includes('underline');
    const name = (e: Element) => `${e.tagName.toLowerCase()} "${(e.textContent ?? '').trim().slice(0, 40)}"`;
    const underlined: string[] = [];
    // A decoration propagates to everything inside: the card itself and its ancestors count too.
    for (let e: Element | null = root; e; e = e.parentElement) if (ul(e)) underlined.push(name(e));
    for (const e of root.querySelectorAll('*')) {
      // the text link under the pointer may underline, with what is inside it
      if (e.closest('[data-wp118-target]')) continue;
      if (ul(e)) underlined.push(name(e));
    }
    const c = getComputedStyle(root);
    return { look: `${c.borderColor} | ${c.backgroundColor} | ${c.boxShadow}`, underlined };
  });
}

const away = (page: Page) => page.mouse.move(1, 1);

/** Hover the card in its padding (the stretched title link covers the whole card): no underline anywhere, and the box changes. */
async function expectCardHover(page: Page, card: Locator, label: string) {
  await card.scrollIntoViewIfNeeded();
  await away(page);
  const before = await readCard(card);
  expect(before.underlined, `${label}: nothing underlined at rest`).toEqual([]);
  await card.hover({ position: { x: 12, y: 12 } });
  await expect.poll(async () => (await readCard(card)).look, { message: `${label}: the box shows the hover` }).not.toBe(before.look);
  expect((await readCard(card)).underlined, `${label}: no text underlined on hover`).toEqual([]);
  await away(page);
}

/** Hover a text link inside a card: that link underlines, nothing else in the card does. */
async function expectOwnLinkHover(page: Page, card: Locator, link: Locator, label: string) {
  await link.evaluate((e) => e.setAttribute('data-wp118-target', ''));
  await link.scrollIntoViewIfNeeded();
  await link.hover();
  await expect.poll(() => link.evaluate((e) => getComputedStyle(e).textDecorationLine), { message: `${label}: the link underlines` }).toContain('underline');
  expect((await readCard(card)).underlined, `${label}: nothing else in the card is underlined`).toEqual([]);
  await link.evaluate((e) => e.removeAttribute('data-wp118-target'));
  await away(page);
}

for (const theme of ['light', 'dark'] as const) {
  test(`home tiles (${theme}): the tile shows hover and keyboard focus on its border; no text in it is underlined`, async ({ page }) => {
    await page.addInitScript((t) => { try { localStorage.setItem('dg-theme', t); } catch { /* none */ } }, theme);
    await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
    // the light theme is the default and carries no attribute
    if (theme === 'dark') await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    else await expect(page.locator('html')).not.toHaveAttribute('data-theme', 'dark');
    const tiles = page.locator('[data-tile]');
    await expect(tiles).toHaveCount(3);
    // WP-121 (moved): the first tile is not a link but two actions, each a box with the card's hover (it was one link); tiles 2 and 3 are links
    const actions = tiles.first().locator('[data-tile-action]');
    await expect(actions).toHaveCount(2);
    for (let i = 0; i < 2; i++) await expectCardHover(page, actions.nth(i), `tile 1, action ${i + 1}`);
    for (let i = 1; i < 3; i++) await expectCardHover(page, tiles.nth(i), `tile ${i + 1}`);
    // keyboard: the focused tile has the same edge, and its focus ring
    const tile = tiles.nth(2);
    const rest = (await readCard(tile)).look;
    await tile.focus();
    expect(await tile.evaluate((e) => e.matches(':focus-visible'))).toBe(true);
    await expect.poll(async () => (await readCard(tile)).look).not.toBe(rest);
    expect(await tile.evaluate((e) => getComputedStyle(e).outlineStyle)).toBe('solid');
    expect((await readCard(tile)).underlined).toEqual([]);
  });
}

test('tender card: the card shows the hover, its title is not underlined; the buyer link underlines on its own hover', async ({ page }) => {
  await visit(page, '/tenders', { title: /.+/, h1: /.+/ });
  const card = page.locator('main article').filter({ has: page.locator('a[href^="/buyers/"]') }).first();
  await expectCardHover(page, card, 'tender card');
  await expectOwnLinkHover(page, card, card.locator('a[href^="/buyers/"]').first(), 'buyer link in a tender card');
  await expectOwnLinkHover(page, card, card.locator('a[target="_blank"]').first(), 'View original in a tender card');
  // keyboard focus on the title link draws the card's edge too
  const rest = (await readCard(card)).look;
  await card.locator('h2 a, h3 a').first().focus();
  await expect.poll(async () => (await readCard(card)).look).not.toBe(rest);
});

for (const [kind, path, href] of [
  ['funding card', '/funding', '/funding/'],
  ['buyer card', '/buyers', '/buyers/'],
  ['company card (organisations)', '/organisations', '/organisations/'],
] as const) {
  test(`${kind}: the card shows the hover; no text in it is underlined`, async ({ page }) => {
    await visit(page, path, { title: /.+/, h1: /.+/ });
    const card = page.locator('main article').filter({ has: page.locator(`h2 a[href^="${href}"], h3 a[href^="${href}"]`) }).first();
    await expectCardHover(page, card, kind);
  });
}

test('rows that are one link (search results, calendar, funding calendar, CPV codes): the row is tinted; no text is underlined', async ({ page }) => {
  await visit(page, '/search?q=demo', { title: /.+/, h1: /.+/ });
  await expectCardHover(page, page.locator('main li:has(> a[class*="flex-col"])').first(), 'search result');
  await visit(page, '/calendar', { title: /.+/, h1: /.+/ });
  await expectCardHover(page, page.locator('main li.group:has(a[href^="/tenders/"], a[href^="/funding/"])').first(), 'calendar entry');
  await visit(page, '/funding?view=calendar', { title: /.+/, h1: /.+/ });
  await expectCardHover(page, page.locator('main li.group:has(a[href^="/funding/"])').first(), 'funding calendar row');
  await visit(page, '/cpv', { title: /.+/, h1: /.+/ });
  await expectCardHover(page, page.locator('main a[href^="/tenders?cpv="]').first(), 'CPV code row');
});

test('source card (/data, not a link itself): hovering it changes no text; its link underlines on its own hover', async ({ page }) => {
  await visit(page, '/data', { title: /.+/, h1: /.+/ });
  const card = page.locator('main article:has(a[target="_blank"])').first();
  await card.scrollIntoViewIfNeeded();
  await card.hover({ position: { x: 12, y: 12 } });
  expect((await readCard(card)).underlined).toEqual([]);
  await expectOwnLinkHover(page, card, card.locator('a[target="_blank"]').first(), 'source link');
});

test('a text link in running text still underlines on hover (and at rest), a link is never inside a link', async ({ page }) => {
  await visit(page, '/about', { title: /.+/, h1: /.+/ });
  const link = page.locator('main p > a:not([class*="flex"]):not([class*="block"])').first();
  await link.scrollIntoViewIfNeeded();
  expect(await link.evaluate((e) => getComputedStyle(e).textDecorationLine)).toContain('underline');
  await link.hover();
  expect(await link.evaluate((e) => getComputedStyle(e).textDecorationLine)).toContain('underline');
  for (const path of ['/', '/tenders', '/funding', '/calendar', '/data']) {
    await visit(page, path, { title: /.+/, h1: /.+/ });
    await expect(page.locator('a a'), path).toHaveCount(0);
  }
});
