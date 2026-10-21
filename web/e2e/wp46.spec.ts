import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * Page-level layout, part 2 (WP-46): the home hero, the readiness form, the placeholder pages, the networks default,
 * the footer and the header targets. The numbers are the ones measured on the build in docs/verification/product/wp46-selfcheck.md.
 * Read-only; the same file runs at desktop width (1280) and at 375 px.
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;

const box = (page: Page, selector: string) =>
  page.locator(selector).first().evaluate((el) => { const r = el.getBoundingClientRect(); return { top: r.top + window.scrollY, left: r.left, width: r.width, height: r.height }; });

test('home: the figures sit at the top of the hero, to the right of the copy, the finder runs full width under both, and the hero is not taller than 760 px', async ({ page }) => {
  test.skip(isMobile(page), 'the hero is one column on a phone');
  await visit(page, '/', { title: /DefenceGate/, h1: 'Defence and dual-use tenders and funding' });
  const hero = await box(page, 'section[aria-labelledby="hero"]');
  const h1 = await box(page, '#hero');
  const figures = await box(page, 'dl[aria-label="Live data"]');
  const form = await box(page, 'section[aria-labelledby="hero"] form[role="search"]');
  expect(hero.height, 'hero height').toBeLessThanOrEqual(760);
  expect(form.width, 'the finder spans the module (under the copy and the figures)').toBeGreaterThan(hero.width * 0.8);
  expect(form.top, 'the finder is under the figures').toBeGreaterThan(figures.top + figures.height - 1);
  expect(figures.left, 'the figures are right of the headline').toBeGreaterThan(h1.left + h1.width / 2);
  expect(figures.top - hero.top, 'the figures start at the top of the hero, not 600 px down').toBeLessThanOrEqual(60);
});

test('home: the three parts are named once, there is no block that only promises, and the funding counter is not shown twice', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Defence and dual-use tenders and funding' });
  await expect(page.getByRole('heading', { name: /1\. What is open to me\?/ })).toHaveCount(1);
  await expect(page.getByRole('heading', { name: /being prepared/i })).toHaveCount(0);
  await expect(page.getByText('Open funding calls', { exact: true })).toHaveCount(1);
});

test('/readiness: fields are at most 560 px wide, and the page says "this browser", not the name of the storage key', async ({ page }) => {
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check', text: ['Your answers stay in this browser'] });
  await expect(page.locator('main').getByText('dg.profile.v1')).toHaveCount(0);
  for (const label of ['Company name (optional)', 'Country where your company is established']) {
    const w = (await page.getByLabel(label).boundingBox())!.width;
    expect(w, `${label}: field width`).toBeLessThanOrEqual(560);
  }
});

test('/alerts has no form: the waitlist stored nothing and was removed', async ({ page }) => {
  await visit(page, '/alerts', { title: /alerts/i, h1: 'Alerts and saved searches', text: ['What works today, without an account'] });
  await expect(page.locator('main form')).toHaveCount(0);
  await expect(page.getByText(/not open yet/i).first()).toBeVisible();
});

// The rows and headings follow the copy of WP-63 (owner decision of 21 October 2026: what exists today, no planned plans).
test('/pricing is one table of what is offered, and /pack one block', async ({ page }) => {
  await visit(page, '/pricing', { title: /pricing/i, h1: 'Pricing' });
  const table = page.getByRole('table', { name: 'What is offered and what it costs' });
  await expect(table.getByRole('row')).toHaveCount(7);
  await expect(table.getByRole('row', { name: /Browsing/ })).toContainText('Free');
  await visit(page, '/pack', { title: /opportunity pack/i, h1: 'Opportunity pack', text: ['Put it together yourself', 'What it is not'] });
  await expect(page.locator('main section')).toHaveCount(1);
});

test('/imprint: the seven fields stand in two columns and every value is still a placeholder', async ({ page }) => {
  await visit(page, '/imprint', { title: /imprint/i, h1: 'Imprint' });
  await expect(page.getByText('[to be provided]')).toHaveCount(7);
  const tops = await page.locator('main dt').evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top)));
  expect(tops).toHaveLength(7);
  if (!isMobile(page)) expect(tops[0], 'the second field is beside the first').toBe(tops[1]);
});

test('/networks/ukraine-partners opens on a view that has content and says why it is not the defence view', async ({ page }) => {
  await visit(page, '/networks/ukraine-partners', { title: /Ukrainian organisations/i, h1: 'Who partners with Ukrainian organisations', text: ['What this counts'] });
  await expect(page.getByText(/No project of the European Defence Fund and its predecessors/)).toBeVisible();
  await expect(page.getByRole('link', { name: /Show only the European Defence Fund/ })).toBeVisible();
  await expect(page.getByRole('table', { name: /Coordinators with a Ukrainian participant/i }).getByRole('link', { name: /Alpha Systems/i })).toBeVisible();
});

test('the 404 page: its five links fill their rows', async ({ page }) => {
  await visit(page, '/this-page-does-not-exist-e2e', { status: 404, title: /page not found/i, h1: 'This page is not in the directory' });
  const rows = await page.locator('main ul > li').evaluateAll((els) => {
    const by = new Map<number, { w: number; left: number; right: number }[]>();
    for (const e of els) { const r = e.getBoundingClientRect(); const k = Math.round(r.top); by.set(k, [...(by.get(k) ?? []), { w: r.width, left: r.left, right: r.right }]); }
    return [...by.values()].map((row) => ({ n: row.length, span: Math.max(...row.map((c) => c.right)) - Math.min(...row.map((c) => c.left)) }));
  });
  expect(rows.length).toBeGreaterThan(0);
  for (const r of rows) expect(Math.abs(r.span - rows[0].span), 'every row has the same width').toBeLessThanOrEqual(2);
});

test('the footer is a compact card (360 px or less from lg) and keeps its links', async ({ page }) => {
  await visit(page, '/about', { title: /About/i, h1: 'About' });
  const footer = page.locator('footer');
  if (!isMobile(page)) expect((await footer.boundingBox())!.height).toBeLessThanOrEqual(360);
  for (const name of ['Imprint', 'Privacy', 'Terms', 'About', 'Source status', 'Funding calls', 'Readiness check']) {
    await expect(footer.getByRole('link', { name, exact: true })).toBeVisible();
  }
  // links are at least 32 px high (44 on a phone)
  const low = await footer.locator('a').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height).filter((h) => h < 31.5));
  expect(low, 'footer links under 32 px').toEqual([]);
});

test('the header: primary targets are at least 44 px high', async ({ page }) => {
  await visit(page, '/about', { title: /About/i, h1: 'About' });
  const targets = isMobile(page)
    ? page.getByRole('link', { name: 'DefenceGate home' }).or(page.getByRole('button', { name: /menu/i })).or(page.getByRole('button', { name: /Switch to/ }))
    : page.getByRole('navigation', { name: 'Main' }).getByRole('link').or(page.getByRole('link', { name: 'DefenceGate home' }).first());
  const heights = await targets.evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height).filter((h) => h > 0));
  expect(heights.length).toBeGreaterThan(0);
  expect(Math.min(...heights)).toBeGreaterThanOrEqual(43.5);
});
