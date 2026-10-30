import { readFileSync } from 'node:fs';
import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { visit, watchErrors } from './helpers';

/**
 * WP-156 against the fake API (e2e/support/fake-api.mjs), with the plans on sale: the two exports of the owner's plan split. The supplier
 * map links its CSV (Team and Consultant); a Consultant gets the file, anyone else is sent back to the list. The eligibility pack (Pro and
 * up) is a cabinet page and a menu entry for an account that has it; built in the browser from the saved profile, it lists the open calls
 * the profile fits with their rules and quotes, prints without the account menu and downloads as CSV. Tagged @fake-api. With
 * WP156_SHOTS=<dir> each state is also saved as a screenshot, in the light and the dark theme.
 */
const S = { pro: 'a'.repeat(43), none: 'b'.repeat(43), consultant: 'c'.repeat(43) } as const;

async function signIn(context: BrowserContext, baseURL: string | undefined, session: string) {
  const host = new URL(baseURL ?? 'http://127.0.0.1').hostname;
  await context.addCookies([{ name: '__Host-dg_session', value: session, domain: host, path: '/', secure: true, httpOnly: true, sameSite: 'Lax' }]);
}

async function shot(page: Page, name: string) {
  const dir = process.env.WP156_SHOTS;
  if (!dir) return;
  const w = page.viewportSize()?.width ?? 1280;
  for (const scheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.screenshot({ path: `${dir}/${name}-${w}-${scheme}.png`, fullPage: true });
  }
  await page.emulateMedia({ colorScheme: 'light' });
}

/** No horizontal scroll at 320 px; a 1440 px shot; then the project's own width again. */
async function widths(page: Page, name: string) {
  const own = page.viewportSize()!;
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: own.height });
    const o = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    expect(o[0], `${name}: horizontal scroll at ${width} px`).toBeLessThanOrEqual(o[1]);
    if (width === 1440) await shot(page, name);
  }
  await page.setViewportSize(own);
}

/** A cabinet page: as `visit` checks a page, but the account's own e-mail address is on it (the menu shows it). */
async function openApp(page: Page, path: string) {
  const errors = watchErrors(page);
  const response = await page.goto(path, { waitUntil: 'load' });
  expect(response?.status()).toBe(200);
  await expect(page).toHaveTitle(/Eligibility pack/);
  await expect(page.locator('h1').first()).toContainText('Eligibility pack');
  const o = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(o[0], 'horizontal scroll').toBeLessThanOrEqual(o[1]);
  expect(errors).toEqual([]);
}

const PROFILE = { version: 2, step: 6, updatedAt: '2026-10-17T10:00:00.000Z', name: '', management: 'same', managementCountry: '', uaOccupied: '',
  regime: 'dual_use', componentPct: '10', restricted: 'no', statuses: {}, classified: 'no', exportIntent: 'none', country: 'ES', control: 'no' };

async function withProfile(page: Page, sizeClass: 'small' | 'large') {
  await page.addInitScript((value) => window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)), { ...PROFILE, sizeClass });
  // Horizon calls have no programme rules; the profile's programme verdict is answered empty, as the API would for them
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ json: { assessments: [], roadmap: [] } }));
}

test('the supplier map links its CSV; a Consultant gets the file, anyone else goes back to the list', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  const list = { title: /supplier map/i, h1: 'Companies' };
  await visit(page, '/suppliers?country=DE', list);
  const link = page.locator('[data-supplier-csv] a[href^="/suppliers/export.csv"]');
  await expect(link).toHaveAttribute('href', '/suppliers/export.csv?country=DE');
  await expect(page.locator('[data-supplier-csv]')).toContainText('part of the Team and Consultant plans');
  await shot(page, 'suppliers-csv-link');
  await widths(page, 'suppliers-csv-link');
  // anonymous and Pro: back to the same list
  for (const session of [null, S.pro]) {
    if (session) await signIn(context, baseURL, session);
    await link.click();
    await expect(page).toHaveURL(/\/suppliers\?country=DE$/);
  }
  await signIn(context, baseURL, S.consultant);
  await visit(page, '/suppliers?country=DE', list);
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('[data-supplier-csv] a[href^="/suppliers/export.csv"]').click()]);
  expect(download.suggestedFilename()).toBe('defencegate-suppliers-2026-10-12.csv');
  const bytes = readFileSync((await download.path())!);
  expect([...bytes.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
  const text = bytes.toString('utf8');
  const lines = text.slice(1).split('\r\n');
  expect(lines[0]).toBe('company,country,contracts_won,first_year,last_year,cpv_divisions,contract_values,page,source');
  expect(lines[1]).toMatch(/^Fake Map GmbH,DE,3,2024,2026,35,EUR 1250000 over 2,https?:\/\/[^,]+\/suppliers\/156001-fake-map-gmbh,"?Source: TED, © European Union\./);
  expect(lines[2]).toMatch(/^'=Fake Formula AG,/);                       // a name a spreadsheet would read as a formula is defused
  expect(lines[3]).toContain('# Not the whole result: this file holds the first 2 of 6,200 matching rows (limit 5,000)');
});

test('the eligibility pack: a menu entry and the list for Pro, the plan for an account without it', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  await withProfile(page, 'small');
  await signIn(context, baseURL, S.none);
  await openApp(page, '/app/eligibility');
  await expect(page.locator('[data-pack-plan]')).toContainText('Pro, Team and Consultant');
  await expect(page.locator('nav a[href="/app/eligibility"]')).toHaveCount(0);
  await shot(page, 'pack-no-plan');

  await signIn(context, baseURL, S.pro);
  await openApp(page, '/app/eligibility');
  await expect(page.locator('nav a[href="/app/eligibility"]').first()).toBeAttached();
  const calls = page.locator('[data-pack-call]');
  await expect(calls).toHaveCount(2);
  await expect(calls.nth(0)).toContainText('Border sensing pilot');
  await expect(calls.nth(1)).toContainText('Only SMEs may apply.');
  await expect(page.locator('[data-pack-summary]')).toContainText('2 of 3 open calls fit your saved profile');
  await expect(page.locator('[data-pack-summary]')).toContainText('1 has no rule read');
  await shot(page, 'pack-pro');
  await widths(page, 'pack-pro');

  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('[data-pack-csv]').click()]);
  expect(download.suggestedFilename()).toBe('defencegate-eligibility-2026-10-12.csv');
  const csv = readFileSync((await download.path())!, 'utf8').slice(1).split('\r\n');
  expect(csv[0]).toBe('call,programme,topic,deadline,verdict,rule,outcome,reason,quote,call_page,source_page');
  expect(csv.some((l) => l.startsWith('SME cyber resilience,Horizon Europe,HORIZON-CL3-2026-156102,2026-12-01T17:00:00Z,') && l.includes('Only SMEs may apply.'))).toBe(true);
  expect(csv.some((l) => l.includes('Unread call'))).toBe(false);

  // on paper: the pack without the account menu and without its buttons
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('aside')).toBeHidden();
  await expect(page.locator('[data-pack-print]')).toBeHidden();
  await expect(calls.nth(0)).toBeVisible();
  await page.emulateMedia({ media: 'screen' });
});

test('the eligibility pack follows the profile: a large company is not listed for the SME-only call', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  await withProfile(page, 'large');
  await signIn(context, baseURL, S.pro);
  await openApp(page, '/app/eligibility');
  await expect(page.locator('[data-pack-call]')).toHaveCount(1);
  await expect(page.locator('[data-pack-summary]')).toContainText('1 is blocked by a rule');
});

test('without a saved profile the pack says how to make one', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  await signIn(context, baseURL, S.pro);
  await openApp(page, '/app/eligibility');
  await expect(page.getByText('No answers in this browser yet')).toBeVisible();
  await expect(page.locator('[data-pack-call]')).toHaveCount(0);
});
