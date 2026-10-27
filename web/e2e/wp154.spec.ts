import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-154 (docs/verification/features/wp154-selfcheck.md): company signals. Three tabs of facts from public records, each row linked
 * to the company page and its source record; the "not investment advice" line; the service on the first screen; the paid part
 * (the rest of the list and the CSV) not offered while it is switched off, as in the demo data.
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const firstScreen = (page: Page) => page.setViewportSize(isMobile(page) ? { width: 375, height: 812 } : { width: 1440, height: 900 });
const top = (page: Page, sel: string) => page.locator(sel).first().evaluate((el) => el.getBoundingClientRect().top);

test('growing: rows with both counts and their sources, the first one on the first screen, no paid part offered', async ({ page }) => {
  await firstScreen(page);
  await visit(page, '/signals', { title: /Company signals/, h1: 'Company signals',
    text: ['Facts from public records, not investment advice.', 'Growing in defence', 'New markets', 'New EU defence funding'] });
  const rows = page.locator('[data-signal-list="growing"] [data-signal-row]');
  await expect(rows).toHaveCount(3);
  await expect(rows.first().locator('[data-counts]')).toHaveText('9 awarded procurements in the last 12 months, 4 in the 12 before');
  await expect(rows.first()).toContainText('Contract values: EUR 4,000,000 (3) against EUR 500,000 (1)');
  await expect(rows.nth(1)).toContainText('No contract values in one currency in both periods.');
  await expect(rows.first().getByRole('link', { name: 'Demo Airframes GmbH' })).toHaveAttribute('href', '/suppliers/1-demo-airframes-gmbh');
  await expect(rows.first().getByRole('link', { name: '101-2026' })).toHaveAttribute('href', /ted\.europa\.eu/);
  expect(await top(page, '[data-signal-row]')).toBeLessThan(page.viewportSize()!.height);
  // the paid part is off in the demo (as by default): no CSV, no sign-in prompt, just the count
  await expect(page.getByText('Download CSV')).toHaveCount(0);
  await expect(page.locator('[data-full-state="closed"]')).toHaveText('All 3 companies.');
  await expect(page.locator('[data-attribution]')).toContainText('© European Union');
});

test('new markets and new funding: the market and the first notice; the first participation and the projects', async ({ page }) => {
  await visit(page, '/signals?kind=markets', { title: /New markets/, h1: 'Company signals' });
  const m = page.locator('[data-signal-list="markets"] [data-signal-row]').first();
  await expect(m.locator('[data-counts]')).toContainText('First win with a buyer in Lithuania on 2 Sep 2026');
  await expect(m.getByRole('link', { name: '111-2026' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Signals' }).locator('[aria-current="page"]')).toHaveText('New markets');

  await visit(page, '/signals?kind=funding', { title: /New EU defence funding/, h1: 'Company signals', text: ['First EU defence project'] });
  const f = page.locator('[data-signal-list="funding"] [data-signal-row]');
  await expect(f).toHaveCount(2);
  await expect(f.first().getByRole('link', { name: 'Demo Sensors S.L.' })).toHaveAttribute('href', /^\/organisations\/5-/);
  await expect(f.first().getByRole('link', { name: 'DEMOSENSE' })).toHaveAttribute('href', /^\/projects\/201-/);
  await expect(f.nth(1)).toContainText('2 projects of the 2025 calls, 3 earlier');
  // the funding tab filters by programme, not by CPV code
  await expect(page.getByLabel('Programme')).toHaveCount(1);
  await expect(page.getByLabel('CPV code or its start')).toHaveCount(0);
});

test('filters: a company country narrows, a word that is no country is said so', async ({ page }) => {
  await visit(page, '/signals?country=Germany', { title: /Company signals/, h1: 'Company signals' });
  await expect(page.locator('[data-signal-row]')).toHaveCount(1);
  await visit(page, '/signals?country=Atlantis', { title: /Company signals/, h1: 'Company signals', text: ['Not a country'] });
  await visit(page, '/signals?kind=funding&programme=EDIDP', { title: /Company signals/, h1: 'Company signals', text: ['No company matches'] });
});

for (const path of ['/signals', '/signals?kind=markets', '/signals?kind=funding']) {
  test(`${path} has no horizontal scroll at 320 px`, async ({ page }) => {
    test.skip(!isMobile(page), 'a phone check');
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto(path, { waitUntil: 'load' });
    const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    expect(scroll, `${path}: ${scroll} px in ${client} px`).toBeLessThanOrEqual(client);
  });
}

// Screenshots for the self-check, light and dark, when E2E_SHOTS_DIR is set (not part of a normal run)
for (const scheme of ['light', 'dark'] as const) {
  test(`screenshots (${scheme})`, async ({ page }, info) => {
    test.skip(!process.env.E2E_SHOTS_DIR, 'set E2E_SHOTS_DIR to write them');
    await page.emulateMedia({ colorScheme: scheme });
    await firstScreen(page);
    for (const kind of ['growing', 'markets', 'funding']) {
      await page.goto(`/signals${kind === 'growing' ? '' : `?kind=${kind}`}`, { waitUntil: 'load' });
      await page.screenshot({ path: `${process.env.E2E_SHOTS_DIR}/${info.project.name}-${scheme}-${kind}.png`, fullPage: true });
    }
  });
}
