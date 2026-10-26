import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-144 (owner's request of 26 October 2026): one buyer, several units. A body whose notices state two names or more (the demo
 * Armaments Agency: its own name and its Regional Logistics Base) has a "Unit" choice on its page, "All units" first and each
 * with its tenders; the choice travels in the address (`?unit=`), works without script (a GET form), is not indexed (canonical:
 * the plain page), and the header says which unit is shown. A body of one name has no choice.
 */

const BUYER = '/buyers/1-demo-armaments-agency';
const PAGE = { title: /Demo Armaments Agency/i, h1: 'Demo Armaments Agency' };
const UNIT = 'demo armaments agency regional logistics base';
const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;

async function chooseUnit(page: Page) {
  const select = page.locator('select[name="unit"]');
  await expect(select.locator('option')).toHaveText([
    'All units (3)', 'Demo Armaments Agency (2)', 'Demo Armaments Agency, Regional Logistics Base (1)',
  ]);
  await select.selectOption(UNIT);
  await page.getByRole('button', { name: 'Show' }).click();
  await page.waitForURL(/[?&]unit=/);
}

async function expectUnitShown(page: Page) {
  expect(new URL(page.url()).searchParams.get('unit')).toBe(UNIT);
  await expect(page.locator('[data-unit-shown]')).toHaveText('Unit: Demo Armaments Agency, Regional Logistics Base');
  await expect(page.locator('[data-buyer-narrowed]')).toContainText('Showing the tenders of Demo Armaments Agency, Regional Logistics Base: 1 open');
  const open = page.locator('section[aria-labelledby="open-tenders"] li');
  await expect(open).toHaveCount(1);
  await expect(open.first()).toContainText('Dostawa materiałów eksploatacyjnych dla warsztatów');
  await expect(page.locator('select[name="unit"]')).toHaveValue(UNIT);
  // one unit's view is not indexed, and its canonical is the plain page
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/);
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', /\/buyers\/1-demo-armaments-agency$/);
}

test('a buyer of several units: the Unit choice narrows its tenders, in the address, and the header says which', async ({ page }) => {
  await visit(page, BUYER, PAGE);
  await expect(page.locator('[data-unit-shown]')).toHaveCount(0);
  await expect(page.locator('meta[name="robots"]')).not.toHaveAttribute('content', /noindex/);
  await expect(page.getByLabel('Unit', { exact: true })).toBeVisible();
  await chooseUnit(page);
  await expectUnitShown(page);
  await page.getByRole('link', { name: 'Show all units' }).click();
  await page.waitForURL((u) => !u.searchParams.has('unit'));
  await expect(page.locator('section[aria-labelledby="open-tenders"] li')).toHaveCount(3);
});

test('the unit travels with the CPV filter and an unknown unit shows all of them', async ({ page }) => {
  await visit(page, `${BUYER}?unit=${encodeURIComponent(UNIT)}&cpv=445`, PAGE);
  await expect(page.locator('[data-buyer-narrowed]')).toContainText('the tenders of Demo Armaments Agency, Regional Logistics Base with a code under 445');
  await expect(page.locator('section[aria-labelledby="open-tenders"] li')).toHaveCount(1);
  await visit(page, `${BUYER}?unit=${encodeURIComponent('Wydział Fizyki')}`, PAGE);
  await expect(page.locator('[data-unit-shown]')).toHaveCount(0);
  await expect(page.locator('section[aria-labelledby="open-tenders"] li')).toHaveCount(3);
});

test('a buyer of one name has no Unit choice', async ({ page }) => {
  await visit(page, '/buyers/4-demo-defence-materiel-organisation', { title: /Demo Defence Materiel Organisation/i, h1: 'Demo Defence Materiel Organisation' });
  await expect(page.locator('select[name="unit"]')).toHaveCount(0);
});

test('the Unit choice is the branded select: named by its label, opened and chosen by the keyboard', async ({ page }) => {
  test.skip(isMobile(page), 'a touch screen keeps the system picker (select.tsx)');
  await visit(page, BUYER, PAGE);
  const combo = page.getByRole('combobox', { name: 'Unit' });
  await combo.focus();
  await page.keyboard.press('ArrowDown');
  const list = page.getByRole('listbox', { name: 'Unit' });
  await expect(list).toBeFocused();
  await expect(list.getByRole('option')).toHaveText(['All units (3)', 'Demo Armaments Agency (2)', 'Demo Armaments Agency, Regional Logistics Base (1)']);
  await page.keyboard.press('End');
  await page.keyboard.press('Enter');
  await expect(combo).toBeFocused();
  await expect(combo).toHaveValue(UNIT);
  await page.getByRole('button', { name: 'Show' }).click();
  await page.waitForURL(/[?&]unit=/);
  await expectUnitShown(page);
});

test.describe('without script', () => {
  test.use({ javaScriptEnabled: false });
  test('the Unit choice is a GET form', async ({ page }) => {
    await visit(page, BUYER, PAGE);
    await chooseUnit(page);
    await expectUnitShown(page);
  });
});

test.describe('in the dark theme', () => {
  test.use({ colorScheme: 'dark' });
  test('the Unit choice reads on the dark surface, and the page fits the screen', async ({ page }, info) => {
    await visit(page, `${BUYER}?unit=${encodeURIComponent(UNIT)}`, PAGE);
    const select = page.locator('select[name="unit"]');
    const [fg, bg] = await select.evaluate((el) => [getComputedStyle(el).color, getComputedStyle(el.parentElement!).backgroundColor]);
    const lum = (c: string) => { const [r, g, b] = (c.match(/\d+/g) ?? ['0', '0', '0']).slice(0, 3).map(Number); return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255; };
    expect(lum(bg)).toBeLessThan(0.3);
    expect(lum(fg)).toBeGreaterThan(0.6);
    await page.locator('form[data-buyer-cpv]').screenshot({ path: info.outputPath('unit-form-dark.png') });
  });
});
