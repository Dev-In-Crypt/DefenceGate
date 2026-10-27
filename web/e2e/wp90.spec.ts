import { mkdirSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-90 (UX audit of 22 October 2026, section 5: the analyst path), on the demo build (lib/mock, NEXT_PUBLIC_DG_NOW 12 October 2026).
 * Persona Jonas, a German defence-electronics analyst who reads TED daily: he subscribes to a search (calendar and feed with exactly its
 * filters, the ceilings said), searches by product-code names, narrows by product group, main code, excluded code, page size and a
 * deadline preset; a tender page states its subject and its documents and links its copy in another source; a buyer page names its top
 * suppliers and filters its tenders by CPV; a supplier page says it is the open segment; /changes narrows by kind of change and lists the
 * week so far; a call's key facts carry its deadline. Screenshots go to WP90_SHOTS when it is set (the self-check).
 */

const SHOTS = process.env.WP90_SHOTS;
const TENDERS = { title: /tenders/i, h1: 'Tenders' } as const;

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: `${SHOTS}/${name}-${page.viewportSize()!.width}.png`, fullPage: false });
}

async function openFilters(page: Page) {
  const button = page.getByRole('button', { name: /^(Show|Hide) filters/ });
  if (await button.isVisible() && (await button.getAttribute('aria-expanded')) !== 'true') await button.click();
}

test('subscribe to this search: the calendar and the feed hold the list’s notices, and say their ceilings', async ({ page, request }) => {
  await visit(page, '/tenders?cpv=44&country=PL', TENDERS);
  const box = page.locator('[data-subscribe]');
  await expect(box).toHaveCount(1);
  expect(await box.evaluate((d) => (d as HTMLDetailsElement).open)).toBe(false);
  await box.locator('summary').click();
  await expect(box.locator('summary')).toHaveText('Subscribe to this search');
  const ics = '/calendar.ics?kind=tenders&country=PL&cpv=44';
  await expect(box.locator('[data-subscribe-ics]')).toHaveAttribute('href', ics);
  await expect(box.locator('[data-subscribe-webcal]')).toHaveAttribute('href', `webcal://ci.example.test${ics}`);
  await expect(box.locator('[data-subscribe-atom]')).toHaveAttribute('href', '/changes.atom?country=PL&cpv=44&status=open');
  await expect(box.locator('[data-subscribe-cap]')).toContainText('At most 3,000 tenders');
  await shot(page, 'tenders-subscribe');
  const titles = await page.locator('main article h2, main article h3').allInnerTexts();
  expect(titles.length).toBeGreaterThan(0);
  // the calendar file: one event per listed tender with a deadline, nothing else
  const file = await (await request.get(ics)).text();
  const summaries = [...file.replace(/\r\n /g, '').matchAll(/^SUMMARY:Deadline: (.*)$/gm)].map((m) => m[1].replace(/\\,/g, ',').replace(/\r$/, ''));
  expect(summaries.length).toBe(titles.length);
  for (const s of summaries) expect(titles.some((t) => t.startsWith(s.replace(/…$/, ''))), s).toBe(true);
  // the feed: every entry is a notice of the search
  const feed = await request.get('/changes.atom?country=PL&cpv=44&status=open');
  expect(feed.status()).toBe(200);
  const body = await feed.text();
  for (const m of body.matchAll(/<title type="text">([^<]*)<\/title>/g)) {
    if (/^DefenceGate/.test(m[1])) continue;
    expect(m[1]).not.toMatch(/Laboratory|Cleaning|Fuel|Road transport|housings/);
  }
});

test('a closed search has no calendar, and says why', async ({ page }) => {
  await visit(page, '/tenders?status=closed', TENDERS);
  const box = page.locator('[data-subscribe]');
  await box.locator('summary').click();
  await expect(box.locator('[data-subscribe-webcal]')).toHaveCount(0);
  await expect(box.locator('[data-subscribe-cap]')).toHaveText('A calendar holds open tenders only: choose the status Open or All for one.');
  await expect(box.locator('[data-subscribe-atom]')).toHaveAttribute('href', '/changes.atom?status=closed');
});

test('product groups, main code only, excluded codes, page size, deadline presets, the country list open', async ({ page }) => {
  await visit(page, '/tenders', TENDERS);
  await openFilters(page);
  const form = page.getByRole('search', { name: 'Filter tenders' });
  // WP-149: one line under the field, what is searched one click away beside it (it was a 9-line hint)
  await expect(form.getByText('Every word must match, in any order.')).toBeVisible();
  await form.getByText('What is searched').click();
  await expect(form.getByText(/English names of the notice’s product codes/)).toBeVisible();
  const country = form.locator('details', { hasText: 'Buyer country' });
  expect(await country.evaluate((d) => (d as HTMLDetailsElement).open)).toBe(true);
  await expect(form.getByLabel('Main product code only')).toBeVisible();
  await expect(form.getByLabel('Leave out product codes')).toBeVisible();
  await form.locator('[data-cpv-presets] a', { hasText: 'Radar and sonar' }).click();
  await expect(page).toHaveURL(/\/tenders\?cpv=35722%2C35723%2C38115%2C38113$/);
  await openFilters(page);
  await expect(page.locator('[data-cpv-presets] a[aria-current="true"]')).toHaveText('Radar and sonar');
  await expect(page.getByLabel('CPV code', { exact: true })).toHaveValue('35722, 35723, 38115, 38113');
  await shot(page, 'tenders-presets');
  const seven = page.locator('[data-deadline-presets] a', { hasText: 'Next 7 days' });
  await expect(seven).toHaveAttribute('href', /from=2026-10-12&to=2026-10-19/);
  // main code only: the housings notice lists 35800000 second, so it is in the group and out of "main only"
  await visit(page, '/tenders?cpv=358', TENDERS);
  await expect(page.locator('main article', { hasText: 'machined aluminium housings' })).toHaveCount(1);
  await visit(page, '/tenders?cpv=358&cpvMain=true', TENDERS);
  await expect(page.locator('main article')).toHaveCount(0);
  await visit(page, '/tenders?notCpv=443', TENDERS);
  await expect(page.locator('main article', { hasText: 'machined aluminium housings' })).toHaveCount(0);
  // 25 a page
  await visit(page, '/tenders?status=all&scope=all&size=25', TENDERS);
  const cards = await page.locator('main article').count();
  expect(cards).toBeGreaterThan(10);
  await expect(page.getByText(/^Showing 1–\d+ of \d+ tenders/)).toBeVisible();
  await visit(page, '/tenders?size=100', TENDERS);
  await expect(page.getByText('Ignored filter: size=100 (use 10, 25, 50)')).toBeVisible();
});

test('the search finds a notice by the English name of its product code', async ({ page }) => {
  await visit(page, '/tenders?q=individual&status=all&scope=all', TENDERS);
  await expect(page.locator('main article')).toHaveCount(1);
  await expect(page.locator('main article')).toContainText('machined aluminium housings');
});

test('a tender page: the subject, the documents, the copy in another source, our corrections folded away', async ({ page }) => {
  await visit(page, '/tenders/1-framework-agreement-machined-aluminium-housings', { title: /machined aluminium/i, h1: /machined aluminium/i });
  await expect(page.locator('[data-subject]')).toHaveText(/^Subject, as the notice states it: Framework agreement for the supply/);
  await expect(page.getByRole('link', { name: /Procurement documents/ }).first()).toHaveAttribute('href', 'https://www.example.org/demo-documents/561204-2026');
  await shot(page, 'tender-subject');
  await visit(page, '/tenders/2-workshop-consumables-supply', { title: /workshop consumables/i, h1: /workshop consumables/i });
  const copy = page.locator('[data-same-notice-page]');
  await expect(copy).toHaveAttribute('href', '/tenders/3');
  await copy.click();
  await expect(page).toHaveURL(/\/tenders\/3-dostawa/);
  await visit(page, '/tenders/11-fuel-supply-framework', { title: /fuel supply/i, h1: /fuel supply/i });
  const fold = page.locator('[data-corrections] details');
  await expect(fold.locator('summary')).toContainText('2 corrections by DefenceGate, not changes by the publisher');
  expect(await fold.evaluate((d) => (d as HTMLDetailsElement).open)).toBe(false);
  await expect(page.getByText('Corrected by DefenceGate on').first()).toBeHidden();
  await fold.locator('summary').click();
  await expect(page.getByText('Corrected by DefenceGate on').first()).toBeVisible();
  await shot(page, 'tender-corrections');
});

test('a buyer page names its top suppliers and filters its tenders by CPV', async ({ page }) => {
  await visit(page, '/buyers/1-demo-armaments-agency', { title: /Demo Armaments Agency/i, h1: 'Demo Armaments Agency' });
  const top = page.locator('[data-top-suppliers]');
  await expect(top.getByRole('heading', { name: 'Top suppliers of this buyer' })).toBeVisible();
  const rows = top.locator('tbody tr');
  expect(await rows.count()).toBeGreaterThan(1);
  await expect(rows.first().locator('a')).toHaveAttribute('href', /^\/suppliers\/\d+-/);
  await expect(top.locator('[data-attribution]')).toContainText('natural persons are never named');
  await shot(page, 'buyer-top-suppliers');
  await page.getByLabel(/This buyer's tenders under a CPV code/).fill('445');
  await page.locator('[data-buyer-cpv]').getByRole('button', { name: 'Show' }).click();
  await expect(page).toHaveURL(/\/buyers\/1-demo-armaments-agency\?cpv=445$/);
  await expect(page.getByRole('status').filter({ hasText: 'under 445' })).toContainText(/[1-9]\d* open and \d+ earlier/);
  await expect(page.locator('main article', { hasText: 'workshop consumables' })).toHaveCount(1);
  await expect(page.locator('main article', { hasText: 'Warehouse racking' })).toHaveCount(0);
});

test('a supplier page says in one line that it is the open segment', async ({ page }) => {
  await visit(page, '/suppliers/1-demo-airframes-gmbh', { title: /Demo Airframes/i, h1: 'Demo Airframes GmbH' });
  await expect(page.locator('[data-open-segment]')).toHaveText('Open segment only: TED award notices of the last three years; the company’s real volume is larger.');
  await expect(page.locator('[data-open-segment]')).toBeVisible();
});

test('/changes by kind of change, and the week so far', async ({ page }) => {
  await visit(page, '/changes?kind=deadline', { title: /what changed/i, h1: 'What changed' });
  await expect(page.getByText('Only the amendments that moved a deadline are listed.')).toBeVisible();
  const entries = page.locator('main li article, main li > div').filter({ hasText: /changed from|added/ });
  expect(await page.locator('#entries ~ * li, section[aria-labelledby="entries"] li').count()).toBeGreaterThan(0);
  for (const t of await entries.allInnerTexts()) expect(t).toMatch(/Deadline/);
  await expect(page.getByLabel('Kind of change')).toBeVisible();
  await shot(page, 'changes-kind');
  await visit(page, '/changes?week=2026-W42', { title: /what changed/i, h1: 'What changed' });
  await expect(page.locator('#window')).toHaveText('This week so far: 12 to 12 October 2026');
  expect((await page.request.get('/changes?week=2026-W43')).status(), 'a week to come is not there').toBe(404);
  await visit(page, '/digest', { title: /weekly digest/i, h1: 'Weekly digest' });
  await expect(page.locator('[data-week-so-far]').first()).toHaveAttribute('href', '/changes?week=2026-W42');
});

test('a funding call states its deadline in the key facts', async ({ page }) => {
  await visit(page, '/funding/1-edf-2026-additive-manufacturing-spare-parts', { title: /additive manufacturing/i, h1: /additive manufacturing/i });
  await expect(page.locator('[data-key-deadline]')).toHaveText(/\d{4}/);
});
