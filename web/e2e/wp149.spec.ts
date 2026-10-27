import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-149 (design pass, phase 1, docs/verification/round6/wp149-selfcheck.md): on the home page, /tenders and /readiness the first
 * screen holds the title, one line and the service itself; explanations sit one click away, in one small line beside the action.
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const top = (page: Page, sel: string) => page.locator(sel).first().evaluate((el) => el.getBoundingClientRect().top);

test('home: the search takes the whole width of the hero, with its label 8 px above it, on the first screen', async ({ page }) => {
  await page.setViewportSize(isMobile(page) ? { width: 375, height: 812 } : { width: 1440, height: 900 });
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  const m = await page.evaluate(() => {
    const hero = document.querySelector('section[aria-labelledby="hero"]')!.getBoundingClientRect();
    const input = document.getElementById('home-search')!;
    const box = input.parentElement!.getBoundingClientRect();
    const button = input.closest('form')!.querySelector('button[type="submit"]')!.getBoundingClientRect();
    const label = document.querySelector('label[for="home-search"]')!.getBoundingClientRect();
    return { hero: hero.width, row: Math.max(box.right, button.right) - box.left, gap: box.top - label.bottom, boxH: box.height, btnH: button.height, bottom: Math.max(box.bottom, button.bottom) };
  });
  expect(m.row, 'field and button span the hero').toBeGreaterThanOrEqual(m.hero - 1);
  expect(m.gap, 'label gap').toBeGreaterThanOrEqual(8);
  expect(m.boxH).toBeGreaterThanOrEqual(56);
  expect(m.btnH).toBeGreaterThanOrEqual(56);
  expect(m.bottom).toBeLessThanOrEqual(page.viewportSize()!.height);
});

test('readiness: title, one line and the first question on the first screen; privacy and scope are a line each, not boxes', async ({ page }) => {
  await page.setViewportSize(isMobile(page) ? { width: 375, height: 812 } : { width: 1440, height: 900 });
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check', text: ['Your answers are not stored on our server.'] });
  const { height } = page.viewportSize()!;
  // the first step's form and its heading start on the first screen; on a desktop its first field too
  expect(await top(page, 'main form[aria-label="Your company"]')).toBeLessThan(height);
  if (!isMobile(page)) expect(await top(page, 'main form[aria-label="Your company"] input')).toBeLessThan(height);
  // no framed callout above the check, and the privacy line keeps its full text one click away, closed
  await expect(page.locator('main aside')).toHaveCount(0);
  const privacy = page.locator('main [data-privacy-line]');
  await expect(privacy).toContainText('Your answers are not stored on our server.');
  const details = privacy.locator('[data-about] details');
  await expect(details).not.toHaveAttribute('open', '');
  await expect(privacy.locator('[data-what-is-sent]')).toBeHidden();
  await privacy.getByText('What is kept and what is sent').click();
  await expect(privacy.locator('[data-what-is-sent]')).toBeVisible();
  // the scope is said once, with both other routes, above the first step
  const scope = page.getByRole('navigation', { name: 'Which check' });
  await expect(scope).toContainText('For EU defence funding (EDF, EDIP and SAFE). Something else?');
  await expect(scope.getByRole('link')).toHaveCount(2);
  // the lead is one line on a desktop
  if (!isMobile(page)) {
    const lines = await page.locator('main header p.lead').evaluate((p) => Math.round(p.getBoundingClientRect().height / parseFloat(getComputedStyle(p).lineHeight)));
    expect(lines).toBe(1);
  }
});

test('tenders: the search explains itself in one line, the rest one click away; the first result starts on the first screen', async ({ page }) => {
  await page.setViewportSize(isMobile(page) ? { width: 375, height: 812 } : { width: 1440, height: 900 });
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  expect(await top(page, '#results article')).toBeLessThan(page.viewportSize()!.height);
  if (isMobile(page)) {
    // the file's tools are one row of links above the results, no card
    const csv = page.getByRole('link', { name: 'Download CSV' }).locator('visible=true').first();
    await expect(csv).toBeVisible();
    await expect(page.getByText('The public fields of this result', { exact: false }).locator('visible=true')).toHaveCount(0);
    return;
  }
  const form = page.getByRole('search', { name: 'Filter tenders' });
  await expect(form.getByText('Every word must match, in any order.')).toBeVisible();
  await expect(form.getByText(/Titles in the original language/)).toBeHidden();
  await form.getByText('What is searched').click();
  await expect(form.getByText(/Titles in the original language/)).toBeVisible();
});

for (const path of ['/', '/tenders', '/readiness']) {
  test(`${path} has no horizontal scroll at 320 px`, async ({ page }) => {
    test.skip(!isMobile(page), 'a phone check');
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto(path, { waitUntil: 'load' });
    const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    expect(scroll, `${path}: ${scroll} px in ${client} px`).toBeLessThanOrEqual(client);
  });
}
