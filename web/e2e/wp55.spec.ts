import { expect, test, type Browser, type Page } from '@playwright/test';

/**
 * WP-55, design-system fixes (docs/verification/product/wp55-selfcheck.md): the first visit follows the system's colour scheme and a
 * saved choice wins over it, the browser-bar colour follows the theme, form-field borders reach 3:1, a link in running text is
 * underlined, the logo is visible in the dark theme, mono text takes a weight DM Mono has, quotations are upright, and the
 * Source card sets its sentences in the body font. Read-only; the same file runs on desktop and at 375 px.
 */

const lum = (rgb: string) => {
  const c = (rgb.match(/[\d.]+/g) ?? ['0', '0', '0']).slice(0, 3).map((v) => Number(v) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const ratio = (a: string, b: string) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

async function open(browser: Browser, scheme: 'light' | 'dark', saved: string | null, path = '/about') {
  const context = await browser.newContext({ colorScheme: scheme });
  if (saved) await context.addInitScript((s) => { try { localStorage.setItem('dg-theme', s); } catch { /* none */ } }, saved);
  const page = await context.newPage();
  await page.goto(path, { waitUntil: 'load' });
  return { page, context };
}
const themeOf = (page: Page) => page.evaluate(() => ({
  theme: document.documentElement.dataset.theme ?? 'light',
  metas: [...document.querySelectorAll('meta[name="theme-color"]')].map((m) => m.getAttribute('content')),
}));

test('first visit: the system scheme decides, a saved choice wins, and the browser-bar colour follows', async ({ browser }) => {
  for (const [scheme, saved, want, color] of [
    ['light', null, 'light', '#F4F1EA'], ['dark', null, 'dark', '#0F1D17'],
    ['dark', 'light', 'light', '#F4F1EA'], ['light', 'dark', 'dark', '#0F1D17'],
  ] as const) {
    const { page, context } = await open(browser, scheme, saved);
    const got = await themeOf(page);
    expect(got.theme, `system ${scheme}, saved ${saved}`).toBe(want);
    expect(got.metas.length).toBeGreaterThan(0);
    for (const c of got.metas) expect(c, `theme-color, system ${scheme}, saved ${saved}`).toBe(color);
    await context.close();
  }
});

test('the theme toggle keeps the choice and moves the theme-color meta with it', async ({ browser }) => {
  const { page, context } = await open(browser, 'dark', null);
  expect((await themeOf(page)).theme).toBe('dark');
  await page.getByRole('button', { name: /switch to light theme/i }).first().click();
  const light = await themeOf(page);
  expect(light.theme).toBe('light');
  for (const c of light.metas) expect(c).toBe('#F4F1EA');
  await page.reload({ waitUntil: 'load' });
  expect((await themeOf(page)).theme, 'a saved light choice beats the dark system on the next visit').toBe('light');
  await context.close();
});

test('form-field borders reach 3:1 and the placeholder 4.5:1, light and dark', async ({ browser }) => {
  for (const saved of ['light', 'dark']) {
    const { page, context } = await open(browser, 'light', saved, '/tenders');
    const m = await page.evaluate(() => {
      const box = document.querySelector('main input[type="search"], main input[type="text"]')!.closest('div,span') as HTMLElement;
      const input = box.querySelector('input') as HTMLInputElement;
      const bg = (el: Element | null): string => { for (let e = el; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor; if (c !== 'rgba(0, 0, 0, 0)') return c; } return 'rgb(255, 255, 255)'; };
      const cs = getComputedStyle(box);
      return { border: cs.borderTopColor, width: cs.borderTopWidth, inside: bg(box), outside: bg(box.parentElement), placeholder: getComputedStyle(input, '::placeholder').color };
    });
    expect(parseFloat(m.width)).toBeGreaterThan(0);
    expect(ratio(m.border, m.inside), `${saved}: border on the field`).toBeGreaterThanOrEqual(3);
    expect(ratio(m.border, m.outside), `${saved}: border on what is around the field`).toBeGreaterThanOrEqual(3);
    expect(ratio(m.placeholder, m.inside), `${saved}: placeholder`).toBeGreaterThanOrEqual(4.5);
    await context.close();
  }
});

test('a link in running text is underlined', async ({ page }) => {
  await page.goto('/about', { waitUntil: 'load' });
  const bad = await page.evaluate(() => [...document.querySelectorAll('main p > a, main li > a')]
    .filter((a) => { const cs = getComputedStyle(a); return cs.display === 'inline' && !/underline/.test(cs.textDecorationLine) && !/no-underline/.test(a.className); })
    .map((a) => a.textContent));
  expect(bad, 'links without an underline in running text').toEqual([]);
  const some = await page.locator('main p > a').count();
  expect(some, 'the page has links in text to check').toBeGreaterThan(0);
});

test('the logo mark is visible on the dark header', async ({ browser }) => {
  const { page, context } = await open(browser, 'light', 'dark', '/');
  const m = await page.evaluate(() => {
    const logo = document.querySelector('header a[aria-label="DefenceGate home"]')!;
    const header = logo.closest('header')!.firstElementChild as HTMLElement;
    return { disc: getComputedStyle(logo.querySelector('svg circle')!).fill, gate: getComputedStyle(logo.querySelector('span span')!).color, bg: getComputedStyle(header).backgroundColor };
  });
  expect(ratio(m.disc, m.bg), 'logo disc on the dark header').toBeGreaterThanOrEqual(3);
  expect(m.gate.replace(/\s/g, '')).toBe('rgb(240,154,98)'); // #F09A62, the brand book's "Gate" on dark
  await context.close();
});

test('mono text takes a weight DM Mono has, quotations are upright, the Source card sets sentences in the body font', async ({ page }) => {
  await page.goto('/tenders/1-framework-agreement-machined-aluminium-housings', { waitUntil: 'load' });
  const m = await page.evaluate(() => {
    const bold: string[] = [];
    for (const el of document.body.querySelectorAll('*')) {
      const cs = getComputedStyle(el);
      const direct = [...el.childNodes].some((n) => n.nodeType === 3 && (n.nodeValue ?? '').trim());
      if (direct && cs.fontFamily.toLowerCase().includes('mono') && parseInt(cs.fontWeight) >= 600) bold.push(el.tagName + '.' + el.className);
    }
    const sourceDl = [...document.querySelectorAll('dl')].find((d) => /Licence/.test(d.textContent ?? ''));
    const licence = sourceDl && [...sourceDl.querySelectorAll('dt')].find((t) => t.textContent === 'Licence')?.nextElementSibling;
    return { bold, italic: [...document.querySelectorAll('q, em, i')].filter((e) => getComputedStyle(e).fontStyle !== 'normal').length, licenceFont: licence ? getComputedStyle(licence).fontFamily : null };
  });
  expect(m.bold, 'mono elements asking for a weight above 500').toEqual([]);
  expect(m.italic).toBe(0);
  expect(m.licenceFont, 'licence line in the Source card').not.toBeNull();
  expect(m.licenceFont!.toLowerCase()).not.toContain('mono');
});

test('a facts grid inside a card has no rule above its first row; the label link of a fact is a 32 px target', async ({ page }) => {
  await page.goto('/funding/1-edf-2026-additive-manufacturing-spare-parts', { waitUntil: 'load' });
  const m = await page.evaluate(() => {
    const grids = [...document.querySelectorAll('dl.facts-grid')].filter((d) => parseFloat(getComputedStyle(d).borderBottomWidth) === 0);
    const out = grids.map((d) => {
      const cells = [...d.children] as HTMLElement[];
      const top = cells[0].getBoundingClientRect().top;
      const row = cells.filter((c) => Math.abs(c.getBoundingClientRect().top - top) < 2);
      return { clipped: getComputedStyle(d).clipPath !== 'none', borders: row.map((c) => getComputedStyle(c).borderTopWidth), contentTops: row.map((c) => Math.round(c.querySelector('dt')!.getBoundingClientRect().top)) };
    });
    const link = document.querySelector('dl.facts-grid dt > a');
    return { out, link: link ? Math.round(link.getBoundingClientRect().height) : null };
  });
  expect(m.out.length).toBeGreaterThan(0);
  for (const g of m.out) {
    expect(g.clipped, 'the top pixel of an in-card grid is clipped').toBe(true);
    expect(new Set(g.contentTops).size, 'the cells of the first row start at the same height').toBe(1);
  }
  if (m.link !== null) expect(m.link).toBeGreaterThanOrEqual(32);
});
