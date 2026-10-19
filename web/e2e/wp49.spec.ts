import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-49 (docs/verification/product/wp49-selfcheck.md): a currency alone is a filter, a filter change is one request and one
 * history entry, Back undoes it and the form follows, a call with no budget says why. Against the demo data (the build CI makes).
 * Not run on the build server (Playwright does not run there); CI runs them.
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const TENDERS = { title: /tenders/i, h1: 'Tenders' };
const FUNDING = { title: /funding/i, h1: /funding/i };

/** Tick or untick checkboxes in one tick of the event loop: what a quick visitor does inside the debounce. */
const clickAll = (page: Page, name: string, values: string[]) =>
  page.evaluate(([n, vs]) => { for (const v of vs) (document.querySelector(`input[name="${n}"][value="${v}"]`) as HTMLInputElement).click(); }, [name, values] as const);
const param = (page: Page, key: string) => new URL(page.url()).searchParams.get(key);
const historyLength = (page: Page) => page.evaluate(() => history.length);

/** Open the filter column on a phone and a fold group on any screen. */
async function openGroup(page: Page, legend: string) {
  if (isMobile(page)) {
    const toggle = page.getByRole('button', { name: /Show filters/ });
    if (await toggle.isVisible()) await toggle.click();
  }
  const summary = page.locator('summary', { hasText: legend });
  if (!(await summary.evaluate((el) => (el.parentElement as HTMLDetailsElement).open))) await summary.click();
}

/** Choose an option of one of our selects: the system picker on a touch screen, our list with a mouse. */
async function choose(page: Page, label: string, value: string) {
  if (isMobile(page)) return page.getByLabel(label).selectOption(value);
  await page.getByRole('combobox', { name: label }).click();
  await page.getByRole('listbox', { name: label }).locator(`[role=option][data-value="${value}"]`).click();
}

test('tenders: a currency alone lists the notices stated in it, counts as a filter, and Back takes it off', async ({ page }) => {
  await visit(page, '/tenders', TENDERS);
  const before = await page.locator('article').count();
  await openGroup(page, 'Estimated value');
  await choose(page, 'Value currency', 'PLN');
  await expect.poll(() => param(page, 'currency')).toBe('PLN');
  // Every card that is left states its value in PLN, and there are fewer than before.
  await expect.poll(async () => {
    const cards = await page.locator('article').allInnerTexts();
    return cards.length > 0 && cards.length < before && cards.every((t) => /PLN [\d,]/.test(t) && !/EUR [\d,]/.test(t));
  }).toBe(true);
  // The group says it holds a filter (a currency alone used to count as none).
  await expect(page.locator('summary', { hasText: 'Estimated value' })).toContainText('1');
  // Back is one step: the address, the list and the select are the ones before.
  await page.goBack();
  await expect.poll(() => param(page, 'currency')).toBeNull();
  await expect(page.getByLabel('Value currency')).toHaveValue('');
  await expect.poll(() => page.locator('article').count()).toBe(before);
});

test('tenders: EUR is a choice like any other and stays in the address', async ({ page }) => {
  await visit(page, '/tenders', TENDERS);
  await openGroup(page, 'Estimated value');
  await choose(page, 'Value currency', 'EUR');
  await expect.poll(() => param(page, 'currency')).toBe('EUR');
  await expect.poll(async () => (await page.locator('article').allInnerTexts()).every((t) => !/(PLN|SEK) [\d,]/.test(t))).toBe(true);
});

test('a run of ticks is one request and one history entry; one tick waits for the next', async ({ page }) => {
  await visit(page, '/tenders', TENDERS);
  const length = await historyLength(page);
  await clickAll(page, 'country', ['PL', 'DE']);
  await page.waitForTimeout(150);
  expect(param(page, 'country'), 'inside the debounce nothing has been asked for').toBeNull();
  await expect.poll(() => param(page, 'country')?.split(',').sort().join(',')).toBe('DE,PL');
  expect(await historyLength(page), 'two ticks, one entry').toBe(length + 1);
  expect(param(page, 'status'), 'a default (status=open) is not spelled out in the address').toBeNull();
  expect(param(page, 'scope')).toBeNull();
  // Back: the address, and the boxes with it.
  await page.goBack();
  await expect.poll(() => param(page, 'country')).toBeNull();
  await expect(page.locator('input[name="country"][value="PL"]')).not.toBeChecked();
  await expect(page.locator('input[name="country"][value="DE"]')).not.toBeChecked();
  // Forward brings them back.
  await page.goForward();
  await expect.poll(() => param(page, 'country')?.split(',').sort().join(',')).toBe('DE,PL');
  await expect(page.locator('input[name="country"][value="PL"]')).toBeChecked();
});

test('a radio applies at once, with no waiting', async ({ page }) => {
  await visit(page, '/tenders', TENDERS);
  await page.evaluate(() => (document.querySelector('input[name="status"][value="closed"]') as HTMLInputElement).click());
  await expect.poll(() => param(page, 'status'), { timeout: 3000 }).toBe('closed');
});

test('funding: a currency alone lists the calls that state a budget in it', async ({ page }) => {
  await visit(page, '/funding?status=all', FUNDING);
  await openGroup(page, 'Budget');
  await choose(page, 'Budget currency', 'SEK');
  await expect.poll(() => param(page, 'currency')).toBe('SEK');
  await expect.poll(async () => {
    const cards = await page.locator('article').allInnerTexts();
    return cards.length > 0 && cards.every((t) => /SEK [\d,]/.test(t));
  }).toBe(true);
  await expect(page.locator('summary', { hasText: 'Budget' })).toContainText('1');
});

test('a call with no budget says why on the list and on its page, and no card says "Not available" for it', async ({ page }) => {
  await visit(page, '/funding?status=all', FUNDING);
  const card = page.locator('article', { hasText: 'The source states no budget' });
  await expect(card).toHaveCount(1);
  await expect(card).not.toContainText('Not available');
  await card.getByRole('link').first().click();
  await expect(page.getByText('The source states no budget for this call.')).toBeVisible();
});

test('the pagination links and the cards do not prefetch (one request each when clicked, none before)', async ({ page }) => {
  const prefetches: string[] = [];
  page.on('request', (r) => { if (r.headers()['next-router-prefetch'] === '1' && /\/(tenders|funding|buyers)\/\d+-/.test(r.url())) prefetches.push(r.url()); });
  await visit(page, '/tenders', TENDERS);
  await page.mouse.wheel(0, 4000);
  await page.waitForTimeout(800);
  expect(prefetches, 'no card link is prefetched').toEqual([]);
});
