import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-59 (docs/verification/product/wp59-selfcheck.md): fixes from the content re-audit. The footer from 1024 px (NEW-9), the
 * regulatory tracker names rules by their title (NEW-2), the PIC page (NEW-6, NEW-7), the calendar feed the pages promise (NEW-1).
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;

test('NEW-9: from 1024 px no footer link wraps and nothing in the footer overlaps', async ({ page }) => {
  test.skip(isMobile(page), 'the widths are set here; the phone layout is the two-column one');
  for (const width of [1024, 1180, 1279, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await visit(page, '/terms', { title: /terms of use/i, h1: 'Terms of use' });
    const boxes = await page.locator('footer').evaluate((f) => [f.querySelector('a[href="/"]')!, ...f.querySelectorAll('nav a')].map((a) => {
      const b = a.getBoundingClientRect();
      return { label: a.textContent ?? '', left: b.left, right: b.right, top: b.top, bottom: b.bottom, height: b.height };
    }));
    expect(boxes.filter((b) => b.label !== 'DefenceGate' && b.height > 36).map((b) => b.label), `${width}: labels on two lines`).toEqual([]);
    const overlaps: string[] = [];
    for (const [i, a] of boxes.entries()) for (const b of boxes.slice(i + 1)) {
      if (a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5) overlaps.push(`${a.label} x ${b.label}`);
    }
    expect(overlaps, `${width}: overlapping footer items`).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}: no horizontal scroll`).toBe(true);
  }
});

test('NEW-2: the regulatory tracker names a rule of the readiness check by its title, not its code', async ({ page }) => {
  await visit(page, '/regulation', { title: /regulatory tracker/i, h1: 'Regulatory tracker' });
  const main = page.locator('#main');
  await expect(main).toContainText('rule “Components from outside the Union and associated countries: at most 35 % of component cost”');
  expect(await main.innerText()).not.toMatch(/\b[A-Z]{2,}-[A-Z]{2,}-\d+\b/);
});

test('NEW-6, NEW-7: the PIC page quotes from inside a sentence with an ellipsis and does not contradict its one issuer', async ({ page }) => {
  await visit(page, '/requirements/pic', { title: /PIC/, h1: /PIC/ });
  const main = page.locator('#main');
  await expect(main).toContainText('…register the organisation');
  await expect(main).toContainText('(the same body for every country).');
  await expect(main).not.toContainText('not been collected for the countries not listed');
  await expect(main).not.toContainText('For a country that is not listed');
});

test('data pages NEW-5: a national call falls under "a national programme"', async ({ page }) => {
  await visit(page, '/funding/13-pl-2026-dual-use-innovation-smes', { title: /DefenceGate/, h1: /.+/ });
  await expect(page.locator('#main')).toContainText('This call falls under a national programme.');
});

test('NEW-1: the alerts page links to the calendar feed, which is on /calendar and answers', async ({ page, request }) => {
  await visit(page, '/alerts', { title: /alerts/i, h1: 'Alerts and saved searches' });
  await page.locator('#main').getByRole('link', { name: 'Calendar feed', exact: true }).click();
  await expect(page).toHaveURL(/\/calendar#feed-heading$/);
  await expect(page.getByRole('heading', { name: 'Calendar feed' })).toBeVisible();
  const ics = await request.get('/calendar.ics');
  expect(ics.status()).toBe(200);
  expect(ics.headers()['content-type']).toContain('text/calendar');
});
