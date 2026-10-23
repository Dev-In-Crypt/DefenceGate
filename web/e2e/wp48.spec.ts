import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-48 (docs/verification/product/wp48-selfcheck.md): the branded select, the record pages centred with a card around the index,
 * the deadline block with room around it, the home hero balanced. Checks read computed styles and boxes, not copy. CI runs them;
 * they were not run on the laptop (Playwright does not run on the build server).
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const CALL = '/funding/1-edf-2026-additive-manufacturing-spare-parts';
const TENDER = '/tenders/1-framework-agreement-machined-aluminium-housings';

const CHANGES = { title: /what changed/i, h1: 'What changed' };

test('a select opens a listbox of our own: brand font and colours, 44 px rows, a scroll box, no layout shift', async ({ page }) => {
  test.skip(isMobile(page), 'a touch screen keeps the system picker (select.tsx)');
  await visit(page, '/changes', CHANGES);
  const combo = page.getByRole('combobox', { name: 'Buyer country' });
  await expect(combo).toBeVisible();
  const before = await page.evaluate(() => ({ h: document.documentElement.scrollHeight, w: document.documentElement.scrollWidth }));
  const boxBefore = await combo.boundingBox();
  await combo.click();
  const list = page.getByRole('listbox', { name: 'Buyer country' });
  await expect(list).toBeVisible();
  await expect(combo).toHaveAttribute('aria-expanded', 'true');
  expect(await list.getByRole('option').count(), 'every country is an option').toBeGreaterThan(20);
  const m = await list.evaluate((el) => {
    const row = el.querySelector('[role=option]')!.getBoundingClientRect();
    const probe = document.createElement('i'); document.body.append(probe);
    probe.style.color = 'var(--surface)'; const surface = getComputedStyle(probe).color;
    probe.style.color = 'var(--ink)'; const ink = getComputedStyle(probe).color; probe.remove();
    const cs = getComputedStyle(el);
    return { row: row.height, height: el.getBoundingClientRect().height, scrolls: el.scrollHeight > el.clientHeight, font: cs.fontFamily, bodyFont: getComputedStyle(document.body).fontFamily, bg: cs.backgroundColor, color: cs.color, surface, ink };
  });
  expect(m.row, 'a row is a 44 px target').toBeGreaterThanOrEqual(44);
  expect(m.height, 'the menu has a maximum height').toBeLessThanOrEqual(360);
  expect(m.scrolls, 'a long list scrolls inside the menu').toBe(true);
  expect(m.font, 'the font of the page, not the system menu font').toBe(m.bodyFont);
  expect(m.bg).toBe(m.surface);
  expect(m.color).toBe(m.ink);
  expect(await page.evaluate(() => ({ h: document.documentElement.scrollHeight, w: document.documentElement.scrollWidth })), 'opening the menu moves nothing').toEqual(before);
  expect(await combo.boundingBox()).toEqual(boxBefore);
  await page.keyboard.press('Escape');
  await expect(list).toHaveCount(0);
  await expect(combo).toBeFocused();
});

test('the opened list follows the dark theme: our surface and our ink, not a white box', async ({ page }) => {
  test.skip(isMobile(page), 'a touch screen keeps the system picker (select.tsx)');
  await visit(page, '/changes', CHANGES);
  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; });
  await page.getByRole('combobox', { name: 'Buyer country' }).click();
  const m = await page.getByRole('listbox', { name: 'Buyer country' }).evaluate((el) => {
    const probe = document.createElement('i'); document.body.append(probe);
    probe.style.color = 'var(--surface)'; const surface = getComputedStyle(probe).color;
    probe.style.color = 'var(--ink)'; const ink = getComputedStyle(probe).color; probe.remove();
    const cs = getComputedStyle(el);
    return { bg: cs.backgroundColor, color: cs.color, surface, ink };
  });
  expect(m.bg).toBe(m.surface);
  expect(m.color).toBe(m.ink);
  expect(m.bg, 'not white').not.toBe('rgb(255, 255, 255)');
});

test('a select works from the keyboard: open, type to find, Enter, and the form still carries the value', async ({ page }) => {
  test.skip(isMobile(page), 'a touch screen keeps the system picker (select.tsx)');
  await visit(page, '/changes', CHANGES);
  const combo = page.getByRole('combobox', { name: 'Buyer country' });
  await combo.focus();
  await page.keyboard.press('ArrowDown');
  const list = page.getByRole('listbox', { name: 'Buyer country' });
  await expect(list).toBeVisible();
  for (const key of ['p', 'o', 'l']) await page.keyboard.press(key);
  await expect(list.locator('[data-active]')).toContainText('Poland');
  await page.keyboard.press('Enter');
  await expect(list).toHaveCount(0);
  await expect(combo).toHaveAttribute('data-value', 'PL');
  await expect(combo).toBeFocused();
  await expect(page.getByLabel('Buyer country')).toHaveValue('PL');
  await page.keyboard.press('End');
  await expect(list.locator('[data-active]')).toHaveAttribute('data-value', /.+/);
  await page.keyboard.press('Escape');
  await expect(combo).toHaveAttribute('data-value', 'PL');
  await Promise.all([page.waitForURL(/country=PL/), page.getByRole('button', { name: 'Apply' }).click()]);
  await expect(page.getByLabel('Buyer country')).toHaveValue('PL');
});

test('a choice reaches the form, and the control is a 44 px target on every screen', async ({ page }) => {
  await visit(page, '/changes', CHANGES);
  const native = page.getByLabel('Buyer country');
  const control = page.getByRole('combobox', { name: 'Buyer country' });
  await expect(control).toBeVisible();
  if (isMobile(page)) {
    // A touch screen keeps the system picker: the control is the native select.
    await native.selectOption('PL');
  } else {
    await control.click();
    await page.getByRole('listbox', { name: 'Buyer country' }).locator('[role=option][data-value="PL"]').click();
    await expect(control).toHaveAttribute('data-value', 'PL');
  }
  await expect(native).toHaveValue('PL');
  const h = await control.evaluate((el) => el.closest('div')!.getBoundingClientRect().height);
  expect(h, 'the box of the control').toBeGreaterThanOrEqual(44);
});

test('a call page: the blocks are centred, the index is a card with an inset, the deadline has room', async ({ page }) => {
  test.skip(isMobile(page), 'the widths are desktop widths; the phone has its own test below');
  for (const width of [1280, 1333, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await visit(page, CALL, { title: /DefenceGate/, h1: /.+/ });
    const m = await page.evaluate(() => {
      const r = (el: Element | null) => { const b = el!.getBoundingClientRect(); return { left: b.left, right: b.right, top: b.top, bottom: b.bottom }; };
      const bar = document.querySelector('header > div')!;
      const nav = document.querySelector('.d-nav nav')!;
      const side = document.querySelector('.d-side > div')!;
      const badge = side.querySelector('[data-deadline]')!;
      return { vw: document.documentElement.clientWidth, bar: r(bar), nav: r(nav), link: r(nav.querySelector('a')), side: r(side), badge: r(badge), next: r(badge.nextElementSibling) };
    });
    expect(Math.abs(m.nav.left - (m.vw - m.side.right)), `${width}: the first and the last card are the same distance from the window edges`).toBeLessThanOrEqual(1);
    expect(Math.abs(m.nav.left - m.bar.left), `${width}: the cards start where the header bar starts`).toBeLessThanOrEqual(1);
    expect(Math.abs(m.side.right - m.bar.right), `${width}: the cards end where the header bar ends`).toBeLessThanOrEqual(1);
    expect(m.link.left - m.nav.left, `${width}: the index has an inset`).toBeGreaterThanOrEqual(16);
    expect(m.badge.top - m.side.top, `${width}: the deadline block is 16 px or more from the top of its card`).toBeGreaterThanOrEqual(16);
    expect(m.next.top - m.badge.bottom, `${width}: and from what follows it`).toBeGreaterThanOrEqual(16);
  }
});

test('a call and a tender page on a phone: the deadline block has 16 px of card around it', async ({ page }) => {
  test.skip(!isMobile(page), 'the phone layout');
  for (const path of [CALL, TENDER]) {
    await visit(page, path, { title: /DefenceGate/, h1: /.+/ });
    const m = await page.evaluate(() => {
      const badge = document.querySelector('.d-top [data-deadline]')!.getBoundingClientRect();
      const card = document.querySelector('.d-top')!.getBoundingClientRect();
      return { top: badge.top - card.top, bottom: card.bottom - badge.bottom, left: badge.left - card.left, right: card.right - badge.right };
    });
    for (const [side, px] of Object.entries(m)) expect(px, `${path}: ${side}`).toBeGreaterThanOrEqual(16);
  }
});

// WP-62: the facts of a list card are compact inset cells 4 px apart (the hairline rows of WP-48 are gone); a tinted deadline is one of
// them, so it keeps 4 px to the next cell and never touches it.
test('a tinted deadline in a list card is its own fact cell, 4 px from the next one', async ({ page }) => {
  await visit(page, '/funding', { title: /.+/, h1: /.+/ });
  const gaps = await page.evaluate(() => {
    const out: number[] = [];
    for (const tint of Array.from(document.querySelectorAll('article dl > div.bg-soon-bg'))) {
      const next = tint.nextElementSibling;
      if (!next) continue;
      const a = tint.getBoundingClientRect(); const b = next.getBoundingClientRect();
      out.push(b.top >= a.bottom - 1 ? b.top - a.bottom : b.left - a.right);
    }
    return out;
  });
  expect(gaps.length, 'the demo list has a tinted deadline').toBeGreaterThan(0);
  for (const g of gaps) expect(Math.round(g), 'space between the tinted cell and the next fact').toBe(4);
});

test('the profile funding tab does not scroll the page sideways (a hidden table header was 396 px wide at 375)', async ({ page }) => {
  await visit(page, '/organisations/101-alpha-systems-gmbh?tab=funding', { title: /Alpha Systems/i, h1: /Alpha Systems/i });
  const w = await page.evaluate(() => ({ s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth }));
  expect(w.s).toBeLessThanOrEqual(w.c);
});

test('home: the links stand under the lead in the left column and the two columns are as tall as each other', async ({ page }) => {
  test.skip(isMobile(page), 'one column on a phone');
  await visit(page, '/', { title: /DefenceGate/, h1: /tenders and funding/i });
  const m = await page.evaluate(() => {
    const hero = document.querySelector('section[aria-labelledby="hero"]')!;
    const left = hero.children[0].getBoundingClientRect();
    const figures = hero.querySelector('dl[aria-label="Live data"]')!.getBoundingClientRect();
    const lead = hero.children[0].querySelector('p')!.getBoundingClientRect();
    // WP-86: the text links became the three task buttons; "Find a tender" stands first
    const all = Array.from(hero.querySelectorAll('a')).find((a) => a.textContent === 'Find a tender')!.getBoundingClientRect();
    const free = Array.from(hero.querySelectorAll('p')).find((p) => p.textContent === 'Free to browse. No account needed.')!.getBoundingClientRect();
    return { left, figures, lead, all, free };
  });
  expect(m.all.top, 'the links are under the lead').toBeGreaterThanOrEqual(m.lead.bottom);
  expect(m.all.right, 'and in the left column').toBeLessThanOrEqual(m.figures.left);
  expect(m.free.bottom, 'the note is in the left column too').toBeLessThanOrEqual(m.left.bottom + 1);
  expect(Math.abs(m.left.height - m.figures.height), 'the copy and the figures are about as tall').toBeLessThanOrEqual(40);
});
