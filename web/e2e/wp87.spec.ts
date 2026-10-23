import { expect, test } from '@playwright/test';
import { openAbout, visit } from './helpers';

/** Below the `lg` breakpoint the filters sit behind a "Filters" button; open it so the text is on screen. */
async function openFilters(page: import('@playwright/test').Page) {
  const button = page.getByRole('button', { name: /^(Show|Hide) filters/ });
  if (await button.isVisible() && (await button.getAttribute('aria-expanded')) !== 'true') await button.click();
}

/**
 * WP-87 (UX audit of 22 October 2026, section 2: correctness and trust), on the demo build (lib/mock): the calendar, its feed and
 * the change feed take the tender list's filters and refuse what they do not read; a filtered list links them with its filters;
 * the default lists lead with core defence and defence calls; a buyer's years add up and its amendment share waits; a unit price is
 * in no sum. The API side is proved against Postgres (backend/tests/integration/test_wp87.py).
 */

const CALENDAR = { title: /deadline calendar/i, h1: 'Deadline calendar' } as const;

test('the calendar reads the list’s filters, says its counts beside the list’s, and names what it does not read', async ({ page }) => {
  await visit(page, '/calendar?kind=tenders&cpv=44', CALENDAR);
  const titles = await page.locator('main a[href^="/tenders/"]').allInnerTexts();
  expect(titles.length).toBeGreaterThan(0);
  for (const t of titles) expect(t).not.toMatch(/Laboratory|Cleaning|Fuel|Road transport/);
  await expect(page.locator('[data-calendar-counts]')).toContainText(/Tenders: \d+ deadlines?/);
  await expect(page.locator('[data-calendar-counts] a')).toHaveAttribute('href', /^\/tenders\?cpv=44&from=\d{4}-\d{2}-\d{2}$/);
  // the feed of this calendar carries the filter, and the form keeps it
  await expect(page.locator('a[download][href^="/calendar.ics"]')).toHaveAttribute('href', '/calendar.ics?kind=tenders&cpv=44');
  await expect(page.locator('form[action="/calendar"] input[type="hidden"][name="cpv"]')).toHaveValue('44');
  await visit(page, '/calendar?cpvv=44', CALENDAR);
  await expect(page.getByText('Ignored filter: cpvv (not a filter of this page)')).toBeVisible();
  await visit(page, '/calendar?cpv=44', CALENDAR);
  await expect(page.getByText('Funding calls are not listed: the CPV code applies to tenders only.')).toBeVisible();
});

test('calendar.ics holds every event of its filters and refuses a parameter it does not read', async ({ request }) => {
  const all = await (await request.get('/calendar.ics')).text();
  const some = await request.get('/calendar.ics?kind=tenders&cpv=44');
  expect(some.status()).toBe(200);
  const body = await some.text();
  const n = (body.match(/BEGIN:VEVENT/g) ?? []).length;
  expect(n).toBeGreaterThan(0);
  expect(n).toBeLessThan((all.match(/BEGIN:VEVENT/g) ?? []).length);
  expect(some.headers()['x-dg-events']).toBe(`${n} of ${n}`);
  expect(body).not.toMatch(/Laboratory|Cleaning services/);
  const bad = await request.get('/calendar.ics?cpvv=44');
  expect(bad.status()).toBe(422);
  expect(await bad.text()).toContain('The calendar feed reads:');
});

test('the change list and its feed read the list’s filters and refuse the unknown', async ({ page, request }) => {
  await visit(page, '/changes?cpv=44', { title: /what changed/i, h1: 'What changed' });
  await expect(page.getByLabel('CPV code')).toHaveValue('44');
  await expect(page.locator('a[href^="/changes.atom"]').first()).toHaveAttribute('href', '/changes.atom?cpv=44');
  await visit(page, '/changes?foo=1', { title: /what changed/i, h1: 'What changed' });
  await expect(page.getByText('Ignored filter: foo (not a filter of this page)')).toBeVisible();
  expect((await request.get('/changes.atom?foo=1')).status()).toBe(422);
  const feed = await (await request.get('/changes.atom?cpv=44')).text();
  expect(feed).toContain('/changes.atom?cpv=44');
});

test('a filtered tender list links its calendar and its change feed with its filters', async ({ page }) => {
  await visit(page, '/tenders?cpv=44&country=PL', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.getByRole('link', { name: 'Deadline calendar of this search' }).first())
    .toHaveAttribute('href', '/calendar?kind=tenders&country=PL&cpv=44');
  await expect(page.getByRole('link', { name: 'Changes of this search (Atom feed)' }).first())
    .toHaveAttribute('href', '/changes.atom?country=PL&cpv=44');
});

test('the default tender list leads with military goods and works, and the plain deadline order is a choice', async ({ page }) => {
  const order = async (path: string) => {
    await visit(page, path, { title: /tenders/i, h1: 'Tenders' });
    return page.locator('main article h2, main article h3').allInnerTexts();
  };
  const first = [...await order('/tenders'), ...await order('/tenders?page=2')];
  const supply = first.findIndex((t) => /Laboratory|Cleaning services/.test(t));
  expect(supply).toBeGreaterThan(0);
  expect(first.slice(supply).every((t) => /Laboratory|Cleaning services/.test(t)), first.join(' | ')).toBe(true);
  await openFilters(page);
  await expect(page.getByLabel(/^All defence/)).toBeChecked();
  const plain = await order('/tenders?sort=deadline-asc');
  expect(plain.findIndex((t) => /Cleaning services/.test(t))).toBeLessThan(first.findIndex((t) => /Cleaning services/.test(t)));
});

test('the funding list lists the defence calls first and heads the dual-use ones', async ({ page }) => {
  await visit(page, '/funding?status=all', { title: /funding/i, h1: /Funding/ });
  const heading = page.locator('[data-dual-use-heading]');
  if (await heading.count() === 0) {
    // the first page holds defence calls only: the dual-use ones come later
    await visit(page, '/funding?status=all&page=2', { title: /funding/i, h1: /Funding/ });
  }
  await expect(page.locator('[data-dual-use-heading]')).toHaveCount(1);
  await expect(page.locator('[data-dual-use-heading] h3')).toHaveText('Dual-use calls');
  await expect(page.locator('[data-dual-use-heading] a')).toHaveAttribute('href', /regime=defence/);
});

test('a buyer’s years add up to its total, and the amendment share waits for six months of watching', async ({ page }) => {
  await visit(page, '/buyers/1-demo-armaments-agency', { title: /Demo Armaments Agency/i, h1: 'Demo Armaments Agency' });
  await expect(page.getByText(/^Not shown yet: we have watched this buyer’s notices only since Sep 2026/)).toBeVisible();
  const card = page.getByRole('heading', { name: 'Notices per year' }).locator('xpath=..');
  const counts = (await card.locator('tbody td').allInnerTexts()).map((t) => Number(t.replace(/\D/g, '')));
  // WP-88: the method is in the collapsed How we count (owner-approved copy change)
  await openAbout(page);
  const lead = await page.getByText(/defence notices in our archive \(the “Tenders in archive” above/).innerText();
  const total = Number(/['’]s ([\d,]+) defence notices/.exec(lead)?.[1].replace(/,/g, ''));
  expect(total).toBeGreaterThan(0);
  expect(counts.reduce((a, b) => a + b, 0)).toBe(total);
  await expect(card.locator('tbody th').first()).toHaveText(/^Before \d{4}$/);
});

test('a supplier’s unit price is shown as published and left out of the sums', async ({ page }) => {
  await visit(page, '/suppliers/1-demo-airframes-gmbh', { title: /Demo Airframes/i, h1: 'Demo Airframes GmbH' });
  await expect(page.locator('td [data-value-suspect]')).toHaveText('value as published, probably a unit price');
  await page.locator('summary', { hasText: /^Contract values/ }).first().click();       // WP-89: "Contract values: EUR ...
  await expect(page.locator('[data-value-totals] [data-value-suspect]')).toHaveText(
    '1 contract states a value under 1,000 (probably a unit price, not the contract’s value) and is left out of the sums.');
});

test('the CPV divisions of the supplier map have their names', async ({ page }) => {
  await visit(page, '/suppliers', { title: /supplier map/i, h1: 'Companies' });
  const rows = await page.getByRole('table', { name: /per CPV division/ }).locator('tbody th').allInnerTexts();
  for (const r of rows) expect(r.trim(), r).toMatch(/^\d{2} \S/);
});

/** In the page: visible text whose colour is (nearly) its background's, and 12-14 px text below 4.5:1. Visually hidden text is skipped. */
const contrastFindings = () => {
  const parse = (c: string) => { const m = /rgba?\(([^)]+)\)/.exec(c); if (!m) return null; const p = m[1].split(',').map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const bgOf = (el: Element | null) => { for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0.5) return c; } return { r: 255, g: 255, b: 255, a: 1 }; };
  const lum = (c: { r: number; g: number; b: number }) => { const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const ratio = (a: { r: number; g: number; b: number }, b: { r: number; g: number; b: number }) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const hidden = (el: Element) => { const st = getComputedStyle(el); const r = el.getBoundingClientRect(); return st.visibility === 'hidden' || st.display === 'none' || r.width <= 1 || r.height <= 1 || el.closest('[hidden],[aria-hidden="true"],.sr-only') !== null; };
  const out: string[] = [];
  for (const el of document.querySelectorAll('body *')) {
    const own = [...el.childNodes].filter((n) => n.nodeType === 3 && (n.textContent ?? '').trim()).map((n) => (n.textContent ?? '').trim()).join(' ');
    if (!own || hidden(el)) continue;
    const st = getComputedStyle(el); const fg = parse(st.color); if (!fg) continue;
    const r = ratio(fg, bgOf(el)); const size = parseFloat(st.fontSize);
    if (r < 1.1 || (size <= 14 && r < 4.5)) out.push(`${el.tagName} ${r.toFixed(2)}:1 ${size}px “${own.slice(0, 40)}”`);
  }
  return out;
};

for (const scheme of ['light', 'dark'] as const) {
  test(`/tenders (${scheme}): no visible text in its background’s colour, and small helper text at 4.5:1 or more`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
    await page.evaluate((s) => document.documentElement.setAttribute('data-theme', s), scheme);
    await openFilters(page);
    expect(await page.evaluate(contrastFindings)).toEqual([]);
  });
}

test('the supplier profile’s controls are at least 24 px', async ({ page }) => {
  await visit(page, '/readiness/supplier', { title: /supplier/i, h1: /supplier/i });
  const small = await page.evaluate(() => [...document.querySelectorAll('button, input:not([type=hidden]), select, textarea, summary, [role=button], a')]
    .filter((el) => {
      const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
      // a link inside running text is exempt (WCAG 2.5.8 "inline"), as is what is visually hidden until focused
      if (r.width <= 1 || r.height <= 1 || st.visibility === 'hidden' || el.closest('.sr-only') || (el.tagName === 'A' && st.display === 'inline')) return false;
      return r.width < 24 || r.height < 24;
    })
    .map((el) => `${el.tagName} ${el.getAttribute('type') ?? ''} ${Math.round(el.getBoundingClientRect().width)}x${Math.round(el.getBoundingClientRect().height)}`));
  expect(small).toEqual([]);
});

test('the footer says its collection run is of any source, and links the source status', async ({ page }) => {
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  const link = page.locator('footer').getByRole('link', { name: 'Last collection run (any source)' });
  await expect(link).toHaveAttribute('href', '/data');
  await expect(page.locator('footer')).not.toContainText(/Last collection run \d/);
});
