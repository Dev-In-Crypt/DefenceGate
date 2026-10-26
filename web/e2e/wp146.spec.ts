import { expect, test, type Page } from '@playwright/test';

/**
 * WP-146 (docs/verification/round6/wp146-selfcheck.md): a filter changed before the page's scripts have run is applied once they
 * have. The page's script chunks are held back until the change is made, so it is certain to land before hydration, as it does on
 * a slow phone (wp49 "a radio applies at once" lost its click that way at 375 px). Against the demo data (the build CI makes).
 */

const CHUNKS = '**/_next/static/chunks/**';
/** The page's filter form (the header has a search box of its own). */
const FORM = 'main form[role="search"]';
const param = (page: Page, key: string) => new URL(page.url()).searchParams.get(key);

/** Open `path` with its scripts held back; returns the function that lets them run and waits until the filter form is hydrated. */
async function openBeforeHydration(page: Page, path: string) {
  let release!: () => void;
  const gate = new Promise<void>((r) => { release = r; });
  await page.route(CHUNKS, async (route) => { await gate; await route.continue(); });
  await page.goto(path, { waitUntil: 'domcontentloaded' });
  return async () => {
    release();
    await page.unroute(CHUNKS);
    // (waitForFunction evaluates a string, which the site's CSP refuses)
    await expect.poll(() => page.evaluate((sel) => {
      const form = document.querySelector(sel);
      return !!form && Object.keys(form).some((k) => k.startsWith('__reactFiber'));
    }, FORM)).toBe(true);
  };
}

/** Change one control the way a tap does, before hydration; true when React had not reached it yet. */
const change = (page: Page, selector: string, value?: string) =>
  page.evaluate(([sel, v]) => {
    const el = document.querySelector(sel) as HTMLInputElement | HTMLSelectElement;
    const early = !Object.keys(el).some((k) => k.startsWith('__reactFiber'));
    if (v === undefined) (el as HTMLInputElement).click();
    else { el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); }
    return early;
  }, [`${FORM} ${selector}`, value] as const);

const CASES = [
  { what: 'tenders, a radio', path: '/tenders', sel: 'input[name="status"][value="closed"]', key: 'status', want: 'closed' },
  { what: 'tenders, a checkbox', path: '/tenders', sel: 'input[name="country"][value="PL"]', key: 'country', want: 'PL' },
  { what: 'tenders, a select', path: '/tenders', sel: 'select[name="currency"]', value: 'PLN', key: 'currency', want: 'PLN' },
  { what: 'funding, a radio', path: '/funding', sel: 'input[name="status"][value="closed"]', key: 'status', want: 'closed' },
  { what: 'buyers, a checkbox', path: '/buyers', sel: 'input[name="hasOpen"]', key: 'hasOpen', want: 'true' },
  { what: 'suppliers, a text box that was left', path: '/suppliers', sel: 'input[name="country"]', value: 'DE', key: 'country', want: 'DE' },
];

for (const c of CASES) {
  test(`${c.what} changed before hydration is applied after it`, async ({ page }) => {
    const hydrate = await openBeforeHydration(page, c.path);
    expect(await change(page, c.sel, c.value), 'the change landed before hydration').toBe(true);
    await hydrate();
    await expect.poll(() => param(page, c.key), { timeout: 3000 }).toBe(c.want);
  });
}

test('with nothing changed before hydration, hydrating asks for nothing', async ({ page }) => {
  for (const path of ['/tenders', '/funding', '/buyers', '/suppliers']) {
    const hydrate = await openBeforeHydration(page, path);
    const length = await page.evaluate(() => history.length);
    await hydrate();
    await page.waitForTimeout(600);   // longer than the checkbox wait
    expect(new URL(page.url()).search, path).toBe('');
    expect(await page.evaluate(() => history.length), `${path}: no history entry`).toBe(length);
  }
});

test('a text box the visitor is still typing in is not applied by hydration, only when it is left', async ({ page }) => {
  const hydrate = await openBeforeHydration(page, '/suppliers');
  await page.locator(`${FORM} input[name="q"]`).pressSequentially('thal');
  await hydrate();
  await page.waitForTimeout(600);
  expect(param(page, 'q'), 'still typing').toBeNull();
  await page.locator(`${FORM} input[name="q"]`).blur();
  await expect.poll(() => param(page, 'q'), { timeout: 3000 }).toBe('thal');
});
