import { expect, test, type Page } from '@playwright/test';
import { openAbout, visit } from './helpers';

/**
 * WP-52b, the web side of the tender data fixes (docs/verification/product/wp52b-selfcheck.md). Against the demo data of a local
 * build (the build CI makes: DG_USE_MOCK=1, NEXT_PUBLIC_DG_NOW=2026-10-12T08:00:00Z). What the demo data cannot show (a total that
 * stopped at its cap, 593 deadlines in a month, a feed of 2,311 changes) is in lib/wp52b.check.ts, and in e2e/wp52b-api.spec.ts against
 * a fake API (E2E_FAKE_API=1).
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const html = async (page: Page, path: string) => (await page.request.get(path)).text();

test('T8: Planned is a status of its own, and Closed no longer lists a planned notice', async ({ page }) => {
  await visit(page, '/tenders?status=planned', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.locator('#results-heading')).toContainText(/Showing 1–\d+ of \d+ tenders/);
  const card = page.locator('article', { hasText: 'Prior information: vehicle spare parts framework for 2027' });
  await expect(card).toBeVisible();
  // A planned notice has no countdown and is not "Closed".
  await expect(card.getByText('Planned', { exact: true }).first()).toBeVisible();
  await expect(card).not.toContainText(/\bClosed\b/);
  // The status filter offers it.
  const filters = page.getByRole('button', { name: /^(Show|Hide) filters/ });
  if (isMobile(page) && (await filters.getAttribute('aria-expanded')) !== 'true') await filters.click();
  await expect(page.getByRole('radio', { name: 'Planned' })).toBeChecked();
  // ... and the other lists do not hold it.
  for (const status of ['closed', 'open']) {
    expect(await html(page, `/tenders?status=${status}`), status).not.toContain('Prior information: vehicle spare parts framework for 2027');
  }
  expect(await html(page, '/tenders?status=all&q=spare+parts')).toContain('Prior information: vehicle spare parts framework for 2027');
});

test('T13: the list and the scope counts say when they were worked out', async ({ page }) => {
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.getByText(/Counts as of \d\d:\d\d UTC/).first()).toBeAttached();
  // The scope note names the time too, and no scope count is printed as "NaN" or "undefined".
  const body = await html(page, '/tenders');
  expect(body).toMatch(/Counts as of \d\d:\d\d UTC, for the other filters as they are now\./);
  expect(body).not.toMatch(/\(NaN\)|\(undefined\)/);
});

test('T17: a card names a code by its own title, never by the title of its division', async ({ page }) => {
  // The demo notice for warehouse racking has CPV 39150000, which is not in the 366-code selection; division 39 is "Furniture, furnishings, ...".
  await visit(page, '/tenders?q=Warehouse+racking', { title: /tenders/i, h1: 'Tenders' });
  const card = page.locator('article', { hasText: 'Warehouse racking' }).first();
  await expect(card).toContainText('CPV 39150000');
  await expect(card).not.toContainText('Furniture');
  // A code of the selection keeps its name (34300000 on the spare-parts notice).
  await visit(page, '/tenders?status=planned', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.locator('article', { hasText: 'vehicle spare parts' }).first()).toContainText('Parts and accessories for vehicles and their engines');
  // The detail page says what the code is within, which is true.
  await page.goto('/tenders/13-warehouse-racking-supply-and-installation');
  await expect(page.getByText('Within:').first()).toBeVisible();
});

test('T11: the source stamp is labelled for what it is', async ({ page }) => {
  // Three versions: the source changed the notice.
  await visit(page, '/tenders/1-framework-agreement-machined-aluminium-housings', { title: /DefenceGate/, h1: /.+/ });
  // (The page also lists related notices as cards; the label of the notice itself is the one in its source panel.)
  const stamp = (label: string) => page.locator('dt', { hasText: label });
  await expect(stamp('Last change seen at the source')).toHaveCount(1);
  await expect(stamp('First seen by us')).toHaveCount(0);
  // One version: no change seen, the stamp is when we first collected it.
  await visit(page, '/tenders/2-workshop-consumables-supply', { title: /DefenceGate/, h1: /.+/ });
  await expect(stamp('First seen by us')).toHaveCount(1);
  await expect(stamp('Last change seen at the source')).toHaveCount(0);
  // The list cards say the same.
  const list = await html(page, '/tenders?q=Supply+of+workshop+consumables');
  expect(list).toContain('First seen by us');
  expect(list).not.toContain('Last change seen at the source');
});

test('T9: the calendar holds the tenders, a month is paged, and nothing is wider than the window', async ({ page, request }) => {
  await visit(page, '/calendar?view=month&month=2026-11', { title: /calendar/i, h1: 'Deadline calendar' });
  await expect(page.locator('#results-heading')).toContainText(/\d+ deadlines? in November 2026/);
  // The demo tenders with a November deadline are in it (4, 9, 12, 18, 26 and 30 November).
  await expect(page.getByRole('link', { name: 'Supply of workshop consumables' }).first()).toBeAttached();
  await expect(page.getByRole('link', { name: 'Road transport services framework' }).first()).toBeAttached();
  // A page past the last is the last, not an empty list or an error.
  const past = await request.get('/calendar?view=month&month=2026-11&page=99', { maxRedirects: 0 });
  expect([200, 307, 308]).toContain(past.status());
  // The size budget: the list and a month are paged by 50 entries, so the page stays small whatever the number of deadlines.
  for (const path of ['/calendar', '/calendar?view=month&month=2026-11']) {
    const size = Buffer.byteLength(await html(page, path));
    expect(size, `${path} is ${size} bytes`).toBeLessThan(600_000);
  }
  await visit(page, '/calendar?kind=tenders', { title: /calendar/i, h1: 'Deadline calendar' });
});

test('T10: "the list has the rest" of a digest week leads to a list that exists', async ({ page }) => {
  // /changes reads a week of the digest and one kind of change in it (the demo data holds week 41).
  await visit(page, '/changes?week=2026-W41&kind=new', { title: /what changed/i, h1: 'What changed', text: [/Week 41: 5 to 11 October 2026/] });
  await expect(page.getByRole('link', { name: 'Show the last 14 days' })).toHaveAttribute('href', '/changes');
  await expect(page.getByRole('link', { name: 'the weekly digest of this week' })).toHaveAttribute('href', '/digest/2026-W41');
  // Only new notices: no "Amended" tag in the entries.
  expect(await page.locator('section[aria-labelledby="entries"] article').count()).toBeGreaterThan(0);
  await expect(page.locator('section[aria-labelledby="entries"] article').filter({ hasText: /^Amended/ })).toHaveCount(0);
  // The form keeps the week and the kind when a country is applied.
  expect(await html(page, '/changes?week=2026-W41&kind=new')).toMatch(/<input type="hidden" name="week" value="2026-W41"\/>/);
  // A week that has not ended, or is outside the archive, is a 404; a week that is not one is ignored.
  for (const week of ['2026-W50', '2026-W30']) expect((await page.request.get(`/changes?week=${week}`)).status(), week).toBe(404);
  expect((await page.request.get('/changes?week=2026-W99')).status()).toBe(200);
  // The feed is always the last 14 days, whatever the address says.
  const plain = await html(page, '/changes.atom');
  const asked = await html(page, '/changes.atom?week=2026-W41&kind=new');
  expect(asked).toBe(plain);
});

test('T16 / T18: a monthly source is not stale after three days, and a partial run says why', async ({ page }) => {
  await visit(page, '/data', { title: /source status/i, h1: 'Source status' });
  const edip = page.locator('article', { has: page.getByRole('heading', { name: 'EDIP work programme' }) });
  await expect(edip).toContainText(/Collected monthly, last ran \d+ days ago/);
  await expect(edip).not.toContainText('Stale');
  // Partial with the minimum met: the card says why.
  // WP-88: the card is titled by the platform's name (its attribution keeps the code)
  const placsp = page.locator('article', { has: page.getByRole('heading', { name: 'Plataforma de Contratación (Spain)' }) });
  await expect(placsp).toContainText('Why the last run is partial:');
  await expect(placsp).toContainText('Met expected minimum');
  await expect(placsp.getByText('Partial', { exact: true })).toBeVisible();
  // The rule for "late" is the API's, named for each rhythm (WP-88: in the collapsed What the statuses mean).
  await openAbout(page);
  await expect(page.getByText(/a run is late for a daily source after 3 days, a monthly source after 40 days/)).toBeVisible();
});

test('T14: a buyer page lists the open tenders its "Open now" counts', async ({ page }) => {
  // Demo buyer 4 has two open core notices and one open supply notice; "Open now" counts core, so the list must too.
  await visit(page, '/buyers/4-demo-defence-materiel-organisation', { title: /DefenceGate|Demo/, h1: /.+/ });
  const openNow = Number((await page.locator('dt', { hasText: 'Open now' }).locator('xpath=following-sibling::dd[1]').innerText()).replace(/\D/g, ''));
  expect(openNow).toBeGreaterThan(0);
  const listed = page.locator('section[aria-labelledby="open-tenders"] article');
  await expect(listed).toHaveCount(openNow);
  // The planned notice of a buyer is in "Tenders in archive", so it has a section (demo buyer 3).
  await visit(page, '/buyers/3-demo-logistics-and-support-command', { title: /DefenceGate|Demo/, h1: /.+/ });
  await expect(page.getByRole('heading', { name: 'Planned tenders' })).toBeVisible();
  const total = Number((await page.locator('dt', { hasText: 'Tenders in archive' }).locator('xpath=following-sibling::dd[1]').innerText()).replace(/\D/g, ''));
  const open = await page.locator('section[aria-labelledby="open-tenders"] article').count();
  const planned = await page.locator('section[aria-labelledby="planned-tenders"] article').count();
  const earlier = await page.locator('section[aria-labelledby="earlier-tenders"] article').count();
  expect(open + planned + earlier, 'open + planned + earlier = tenders in archive (one page)').toBe(total);
});
