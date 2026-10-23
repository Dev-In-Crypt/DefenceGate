import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-56, content structure without wording changes (docs/verification/product/wp56-selfcheck.md): the pointer to "Can you apply?"
 * is true (T20a), a long source text is whole behind a disclosure (T20b, C6), a repeated row is one row, /regulation says its intro once,
 * the footer groups are the header's, the requirement pages show human names, and the title and description limits hold (C4, C5).
 * The calls are the demo calls of lib/mock/calls.ts: 13 is national, 7 is a Horizon call whose rules were not read, 8 has long source texts.
 */

const isMobile = (w: number | undefined) => (w ?? 1280) < 700;

test('T20a: a national call does not point to a section it does not have', async ({ page }) => {
  await visit(page, '/funding/13', { title: /DefenceGate/, h1: /.+/ });
  const block = page.locator('section[aria-labelledby="rules-that-apply"]');
  await expect(block).toContainText('Its conditions are in the official call text.');
  await expect(block).not.toContainText('Can you apply?');
  await expect(page.locator('#can-you-apply-')).toHaveCount(0);
});

test('T20a: where the "Can you apply?" panel exists the pointer is a link to it', async ({ page }) => {
  await visit(page, '/funding/7', { title: /DefenceGate/, h1: /.+/ });
  const link = page.locator('section[aria-labelledby="rules-that-apply"]').getByRole('link', { name: /Can you apply/ });
  await expect(link).toHaveAttribute('href', '#can-you-apply-');
  await expect(page.locator('#can-you-apply-')).toHaveCount(1);
});

test('F-15: the dates of the terms are written like every other date', async ({ page }) => {
  await visit(page, '/funding/7', { title: /DefenceGate/, h1: /.+/ });
  const terms = page.locator('section[aria-labelledby="terms"]');
  await expect(terms).toContainText('15 Dec 2026');
  await expect(terms).toContainText('4 Jan 2027 to 11 Jan 2027');
  await expect(terms).not.toContainText('2026-12-15');
});

test('T20b and C6: a long source text is whole behind "Show full text", the same sentence is one row', async ({ page }) => {
  await visit(page, '/funding/8', { title: /DefenceGate/, h1: /.+/ });
  const who = page.locator('section[aria-labelledby="who-can-apply"]');
  // two rows with the same sentence are one row; the long list is not cut
  await expect(who.locator('dt')).toHaveText(['Eligible countries', 'Other eligibility conditions and applicants']);
  await expect(who.getByText('Described in section 6 of the call document.')).toHaveCount(1);
  const more = who.locator('summary', { hasText: /^Show full text, [\d,]+ characters$/ });
  await expect(more).toHaveCount(1);
  await expect(who.getByText('Country119.')).toBeHidden();
  await more.click();
  await expect(who.getByText(/Country119\./)).toBeVisible();
  // the conditions as published: the start is on the page, the whole is one tap away
  const conditions = page.locator('#conditions');
  await expect(conditions.getByText(/^Condition 0 of the call text/).first()).toBeVisible();
  await expect(conditions.getByText('Condition 79 of the call text is published by the source.')).toBeHidden();
  await conditions.locator('summary', { hasText: /Show full text, [\d,]+ characters/ }).click();
  await expect(conditions.getByText(/Condition 79 of the call text is published by the source\./)).toBeVisible();
  // the index at the top reaches it
  await expect(page.locator('a[href="#conditions"]').first()).toBeAttached();
});

test('C5: /regulation says its intro once', async ({ page }) => {
  await visit(page, '/regulation', { title: /regulatory tracker/i, h1: 'Regulatory tracker' });
  await expect(page.locator('#main').getByText('copied word for word')).toHaveCount(1);
});

test('C5: every group of the footer is a group of the header, with the same names and addresses', async ({ page }) => {
  test.skip(isMobile(page.viewportSize()?.width), 'the desktop header has the sub menus in the page');
  await visit(page, '/about', { title: /About/i, h1: 'About' });
  // WP-86: a small menu names its group in `data-group`; the Tenders menu (Tenders, Market overview) stands in the footer's
  // Directory with the other lists, every other group under its own name.
  const groups = await page.locator('header nav[aria-label="Main"] div[id^="sub-"]').evaluateAll((els) =>
    els.map((e) => ({ title: e.getAttribute('data-group') ?? '', links: [...e.querySelectorAll('a')].map((a) => ({ label: a.textContent?.trim() ?? '', href: a.getAttribute('href') })) })));
  expect(groups.length).toBeGreaterThanOrEqual(3);
  for (const g of groups) {
    const title = g.title === 'Tenders' ? 'Directory' : g.title;
    const nav = page.locator(`footer nav[aria-label="${title}"]`);
    await expect(nav, `the footer has the group ${title}`).toHaveCount(1);
    for (const l of g.links) await expect(nav.locator(`a[href="${l.href}"]`).filter({ hasText: new RegExp(`^${l.label}$`) }), `${title}: ${l.label}`).toHaveCount(1);
  }
  // and every top-level link of the header is in the footer under the same label
  const top = await page.locator('header nav[aria-label="Main"] a').evaluateAll((els) => els.map((a) => ({ label: a.textContent?.trim() ?? '', href: a.getAttribute('href') })));
  for (const t of top) await expect(page.locator(`footer a[href="${t.href}"]`).filter({ hasText: new RegExp(`^${t.label}$`) }), t.label).toHaveCount(1);
});

test('T24: ?programme=edf is the same filter as ?programme=EDF, and the budget sort says which currency leads', async ({ page }) => {
  const total = async (path: string) => {
    await visit(page, path, { title: /funding/i, h1: /funding/i });
    return (await page.locator('#results-heading').innerText()).trim();
  };
  const upper = await total('/funding?status=all&programme=EDF');
  const lower = await total('/funding?status=all&programme=edf');
  const none = await total('/funding?status=all');
  expect(lower).toBe(upper);
  expect(none).not.toBe(upper);
  await visit(page, '/funding?status=all&sort=budget-desc', { title: /funding/i, h1: /funding/i });
  await expect(page.getByRole('button', { name: /Sort/ }).or(page.getByLabel('Sort')).first()).toContainText('Budget, largest first (EUR first)');
});

test('M-9, M-10, M-11: the requirement pages show human names and one grouped list', async ({ page }) => {
  await visit(page, '/requirements/ncage', { title: /NCAGE code/, h1: 'NCAGE code' });
  const main = page.locator('#main');
  await expect(main).not.toContainText('technical appendix');
  await expect(main).not.toContainText('REQ-');
  const issuers = main.locator('section[aria-labelledby="s-who-issues-it"] ul > li');
  expect(await issuers.count(), 'three single rows and two groups, not fifty').toBeLessThanOrEqual(6);
  await expect(main.getByText(/: 31 countries$/)).toBeVisible();
  await expect(main.getByText(/: 19 countries$/)).toBeVisible();
  await expect(main.getByText('UNVERIFIED: for NATO countries')).toHaveCount(1);
  await visit(page, '/requirements/iso9001', { title: /ISO 9001/, h1: /ISO 9001/ });
  await expect(page.locator('#main')).not.toContainText('REQ-');
  await expect(page.locator('#main').getByRole('link', { name: /AQAP 2110/ }).first()).toBeVisible();
  await visit(page, '/requirements/export', { title: /export/i, h1: /.+/ });
  await expect(page.locator('#main')).not.toContainText('You said');
  await expect(page.locator('#main')).not.toContainText('technical appendix');
});

test('C5: a title fits 60 characters with the site name and a description 160', async ({ page }) => {
  for (const path of ['/requirements', '/requirements/edip-elig', '/requirements/aqap2110', '/readiness', '/regulation', '/data/sovereignty', '/alerts']) {
    await page.goto(path);
    expect((await page.title()).length, `${path} title`).toBeLessThanOrEqual(60);
    const description = await page.locator('meta[name="description"]').getAttribute('content');
    expect((description ?? '').length, `${path} description`).toBeLessThanOrEqual(160);
  }
});
