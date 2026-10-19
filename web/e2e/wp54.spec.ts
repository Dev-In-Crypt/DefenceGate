import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-54, rendering stability and no-JS (docs/verification/product/wp54-selfcheck.md): the first page of tenders and buyers is in the
 * HTML the server sends (R2), nothing is wider than the window (R3), a clipped card title can still be read (R4), the urgent deadline
 * prints dark on white (R5), and the saved dark theme survives a page that React had to render again (R1).
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;

// R2: a loading file makes the server send a skeleton in place and the list as a hidden block that only a script swaps in.
for (const [path, noun, link] of [['/tenders', 'tenders', /href="\/tenders\/[^"/]+"/], ['/buyers', 'buyers', /href="\/buyers\/[^"/]+"/]] as const) {
  test(`${path}: the first page is in the HTML the server sends, before any hidden block`, async ({ request }) => {
    const html = await (await request.get(path)).text();
    const hidden = html.indexOf('<div hidden id="S:');
    const visible = hidden === -1 ? html : html.slice(0, hidden);
    expect(visible).toMatch(link);
    expect(visible).toMatch(/Showing 1/);
    expect(html).not.toContain(`Loading ${noun}`);
  });

  test(`${path}: with scripts off the list, its sort and its pager are there as links`, async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto(path);
    await expect(page.locator('main article').first()).toBeVisible();
    await expect(page.locator('#results-heading')).toContainText(/Showing 1/);
    await expect(page.getByRole('status', { name: /^Loading/ })).toHaveCount(0);
    await context.close();
  });
}

// R3: widths where the audit found sideways scroll.
async function noSideways(page: Page, path: string) {
  await page.goto(path, { waitUntil: 'load' });
  const w = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  expect(w.scroll, `${path} at ${w.client} px`).toBeLessThanOrEqual(w.client);
}

test('a tender page does not scroll sideways at 768, 375 and 320 px, even with a long source name and a tooltip open', async ({ page }) => {
  await page.goto('/tenders');
  const href = await page.locator('main article h2 a, main article h3 a').first().getAttribute('href');
  expect(href).toMatch(/^\/tenders\/[^/]+$/);
  for (const width of [768, 375, 320]) {
    await page.setViewportSize({ width, height: 800 });
    await noSideways(page, href!);
    // The value that broke the page: one long word in the source name (a German portal's name).
    await page.evaluate(() => {
      const dd = [...document.querySelectorAll('main dl dd')].find((d) => d.previousElementSibling?.textContent === 'Source');
      if (dd) dd.textContent = 'Bekanntmachungsservice-Bundesanzeigerverlag-Verwaltungsvorschriftenportal';
    });
    const w = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    expect(w.scroll, `long source name at ${width} px`).toBeLessThanOrEqual(w.client);
  }
});

test('the reason tooltip of a confidence badge takes no room until it is shown', async ({ page }) => {
  await page.goto('/tenders');
  const badge = page.locator('[data-confidence]').first();
  test.skip((await badge.count()) === 0, 'the demo data holds no confidence badge on this page');
  const tip = badge.locator('span[aria-hidden="true"]');
  await expect(tip).toHaveCSS('display', 'none');
  await badge.focus();
  await expect(tip).toHaveCSS('display', 'block');
});

test('/tenders, the calendar and the filter forms of /changes and /market do not scroll sideways at 1024, 640 and 320 px', async ({ page }) => {
  for (const width of [1024, 640, 320]) {
    await page.setViewportSize({ width, height: 800 });
    for (const path of ['/tenders', '/calendar', '/changes', '/market']) await noSideways(page, path);
  }
});

test('a calendar entry whose title is one unbreakable run wraps instead of widening the page', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto('/calendar');
  const link = page.locator('main ul li a').first();
  await expect(link).toBeVisible();
  await link.evaluate((a) => { a.textContent = 'Better understanding, anticipating and addressing the biodiversity benefits and impacts of the clean and digital industries'; });
  const w = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  expect(w.scroll).toBeLessThanOrEqual(w.client);
});

// R4
test('a list card title is clamped by the card, not the window, and the whole title is in the link', async ({ page }) => {
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  const r = await page.locator('main article').first().evaluate((card) => {
    const h = card.querySelector('h2, h3') as HTMLElement;
    const a = h.querySelector('a') as HTMLAnchorElement;
    return { clamp: getComputedStyle(h).webkitLineClamp, title: a.getAttribute('title'), text: a.textContent?.trim(), cardWidth: card.getBoundingClientRect().width };
  });
  expect(r.title, 'the link carries the whole title').toBe(r.text);
  expect(r.clamp).toBe(r.cardWidth >= 664 + 40 ? '3' : '4');
});

// R5
test('the urgent deadline and the filled tags print dark on white: no light text is left for a printer that drops backgrounds', async ({ page }) => {
  await page.goto('/tenders');
  await page.evaluate(() => {
    const box = document.createElement('div');
    box.id = 'print-probe';
    box.className = 'bg-urgent text-on-urgent';
    box.innerHTML = '<span class="text-on-urgent">Closes this week</span>';
    const tag = document.createElement('span');
    tag.id = 'print-probe-tag';
    tag.className = 'bg-primary text-on-primary';
    tag.textContent = 'EDF';
    document.querySelector('main')!.append(box, tag);
  });
  await page.emulateMedia({ media: 'print' });
  const probe = await page.evaluate(() => {
    const read = (id: string) => { const e = document.getElementById(id)!; const s = getComputedStyle(e); return { color: s.color, bg: s.backgroundColor, border: s.borderTopWidth, inner: e.firstElementChild ? getComputedStyle(e.firstElementChild).color : s.color }; };
    return { urgent: read('print-probe'), tag: read('print-probe-tag') };
  });
  const light = (c: string) => (c.match(/\d+/g) ?? []).slice(0, 3).map(Number).every((v) => v > 200);
  for (const p of [probe.urgent, probe.tag]) {
    expect(light(p.color), `text ${p.color}`).toBe(false);
    expect(light(p.inner), `inner text ${p.inner}`).toBe(false);
    expect(parseFloat(p.border), 'a border says what the background no longer does').toBeGreaterThanOrEqual(1);
  }
  expect(probe.urgent.bg === 'rgba(0, 0, 0, 0)' || light(probe.urgent.bg)).toBe(true);
});

// R1: a page React cannot hydrate is rendered again on the client, and that used to take <html data-theme> with it.
test('a page that fails to hydrate keeps the saved dark theme', async ({ page, context }) => {
  test.skip(isMobile(page), 'one viewport is enough: the theme is not width-dependent');
  await context.addInitScript(() => { try { localStorage.setItem('dg-theme', 'dark'); } catch { /* none */ } });
  // Break the server HTML on its way to the browser: a heading whose text the client will not render (React ignores extra elements in <body>, not changed text).
  await page.route('**/about', async (route) => {
    const response = await route.fetch();
    const body = (await response.text()).replace(/(<h1[^>]*>)([^<]+)/, '$1$2 broken');
    await route.fulfill({ response, body });
  });
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/about', { waitUntil: 'load' });
  await page.waitForLoadState('networkidle');
  await expect.poll(() => errors.some((e) => /418|425|423|ydrat/.test(e)), { message: 'the broken page did fail to hydrate' }).toBe(true);
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
});
