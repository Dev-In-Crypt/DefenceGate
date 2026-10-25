import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-52b against a fake API with the audit's numbers (e2e/support/fake-api.mjs): 593 deadlines in November, a closed list of 287,634 that
 * stops at position 10,000, a search that cannot be counted, a feed of 2,311 changes (3,100 for Poland), a digest week of 873 notices.
 * Skipped unless E2E_FAKE_API=1 (the site must be started with DG_API_URL pointing at the fake; see the file's header).
 */
test.skip(!process.env.E2E_FAKE_API, 'needs the fake API: E2E_FAKE_API=1 and a site started with DG_API_URL=http://127.0.0.1:4010');

const text = async (page: Page, path: string) => (await page.request.get(path)).text();

test('T9: November shows its 593 deadlines, twelve pages of at most 50, and the page stays small', async ({ page }) => {
  await visit(page, '/calendar?view=month&month=2026-11', { title: /calendar/i, h1: 'Deadline calendar' });
  await expect(page.locator('#results-heading')).toContainText('593 deadlines in November 2026');
  const cards = await page.locator('section[aria-labelledby="results-heading"] li').count();
  expect(cards, 'entries on the first page').toBe(50);
  await expect(page.getByText('Showing 1–50 of 593 deadlines in this month.')).toBeVisible();
  await visit(page, '/calendar?view=month&month=2026-11&page=12', { title: /calendar/i, h1: 'Deadline calendar' });
  await expect(page.getByText('Showing 551–593 of 593 deadlines in this month.')).toBeVisible();
  // A page past the last is the last.
  const past = await page.request.get('/calendar?view=month&month=2026-11&page=60');
  expect(past.status()).toBe(200);
  expect(past.url()).toMatch(/page=12(&|$)/);
  for (const path of ['/calendar', '/calendar?view=month&month=2026-11', '/calendar?view=month&month=2026-12']) {
    const size = Buffer.byteLength(await text(page, path));
    // 50 entries a page (WP-63): about 194 KB for the list and 276 KB for a month here, against 306 and 390 KB at 100.
    expect(size, `${path} is ${size} bytes`).toBeLessThan(300_000);
  }
  // The whole calendar: 1,449 deadlines, paged.
  await visit(page, '/calendar', { title: /calendar/i, h1: 'Deadline calendar' });
  // WP-100: one number format on the page (1,449, as beside it)
  await expect(page.locator('#results-heading')).toContainText('1,449 upcoming deadlines');
});

test('T3: a closed list of 287,634 stops at position 10,000 and says so; a search that cannot be counted reads "at least"', async ({ page }) => {
  await visit(page, '/tenders?status=closed', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.locator('#results-heading')).toHaveText('Showing 1–10 of 287,634 tenders');
  await expect(page.getByText(/Counts as of 07:55 UTC/).first()).toBeAttached();
  // The last page it can show.
  const last = await visit(page, '/tenders?status=closed&page=1000', { title: /tenders/i, h1: 'Tenders' });
  expect(last.status()).toBe(200);
  await expect(page.locator('#results-heading')).toHaveText('Showing 9,991–10,000 of 287,634 tenders');
  await expect(page.getByText(/The list shows the first 10,000 tenders of this search\. Narrow it with the filters/)).toBeVisible();
  // The pager never offers a page the list does not serve.
  await expect(page.locator('nav[aria-label="Pagination"] a[aria-label="Page 28764"]')).toHaveCount(0);
  await expect(page.locator('nav[aria-label="Pagination"]')).toBeVisible();
  // Past it is the last page, not an error (the site clamps the page number; the API would 503 past 10,000).
  const past = await page.request.get('/tenders?status=closed&page=5000');
  expect(past.status()).toBe(200);
  // A count that stopped is "at least".
  await visit(page, '/tenders?status=closed&q=Bundeswehr', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.locator('#results-heading')).toHaveText('Showing 1–10 of at least 10,000 tenders');
  // Planned is offered where the API supports it.
  await visit(page, '/tenders?status=planned', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.locator('#results-heading')).toHaveText('Showing 1–10 of 6,280 tenders');
});

test('T13: the scope counts add up with the overlap, and say when they were counted', async ({ page }) => {
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  const body = await text(page, '/tenders');
  expect(body).toContain('(1,522)');
  expect(body).toContain('(294)');
  expect(body).toContain('(1,274)');
  expect(body).toContain('Counts as of 07:55 UTC, for the other filters as they are now.');
  // WP-121: the labels' words (was "Core and supplies add up to 46 more than the first count: 46 supply notices are the national copy of a core notice")
  expect(body).toContain('Military goods and works and Other purchases by armed forces add up to 46 more than All defence: 46 notices are in both (the national copy of a notice of military goods and works)');
});

test('T10: the Atom feed holds the whole window, and says so when a cap cuts it', async ({ request }) => {
  const feed = await (await request.get('/changes.atom')).text();
  expect((feed.match(/<entry>/g) ?? []).length).toBe(2311);
  expect(feed).not.toContain('This feed holds the newest');
  expect(new Set([...feed.matchAll(/<id>(.*?)<\/id>/g)].map((m) => m[1])).size, 'ids are unique').toBe(2312);
  const poland = await (await request.get('/changes.atom?country=PL')).text();
  expect((poland.match(/<entry>/g) ?? []).length).toBe(2400);
  expect(poland).toContain('This feed holds the newest 2,400 of the 3,100 changes; the page lists them all.');
  // A digest week or a kind in the address is not a feed.
  expect(await (await request.get('/changes.atom?week=2026-W42&kind=new')).text()).toBe(feed);
});

test('T10: the digest lists identical notices once with their number, and its "has the rest" link works', async ({ page }) => {
  await visit(page, '/digest/2026-W42', { title: /weekly digest/i, h1: 'Weekly digest' });
  const section = page.locator('#tenders-new');
  await expect(section.getByText('×13').first()).toBeVisible();
  await expect(section.locator('article')).toHaveCount(30);
  // 30 rows stand for 49 notices of 873.
  await expect(section.getByText('Showing the first 49 of 873.')).toBeVisible();
  const rest = section.getByRole('link', { name: 'list of changes of this week' });
  await expect(rest).toHaveAttribute('href', '/changes?week=2026-W42&kind=new');
  await rest.click();
  await expect(page).toHaveURL(/\/changes\?week=2026-W42&kind=new/);
  await expect(page.locator('section[aria-labelledby="entries"] h2').first()).toHaveText('Showing 1–25 of 873 changes');
  await expect(page.getByText(/Week 42: 12 to 18 October 2026/).first()).toBeVisible();
  await page.goto('/changes?week=2026-W42&kind=amended');
  await expect(page.locator('section[aria-labelledby="entries"] h2').first()).toHaveText('Showing 1–25 of 79 changes');
});

test('T16 / T18 / T11: sources by their rhythm, a partial run with its reason, and the stamp of a notice', async ({ page }) => {
  // /data is built once with the demo data and refreshed after 60 s: wait for the fake's numbers.
  await expect.poll(async () => (await text(page, '/data')).includes('A daily source that missed its runs'), { timeout: 150_000, intervals: [5_000] }).toBe(true);
  await visit(page, '/data', { title: /source status/i, h1: 'Source status' });
  const card = (name: string) => page.locator('article', { has: page.getByRole('heading', { name }) });
  await expect(card('CORDIS')).toContainText('Collected monthly, last ran 4 days ago');
  await expect(card('CORDIS')).not.toContainText('Stale');
  await expect(card('A daily source that missed its runs')).toContainText('Stale: last ran 5 days ago');
  await expect(card('European Defence Fund: project factsheets')).toContainText('Why the last run is partial: 1 factsheets could not be read');
  await expect(card('Plataforma de Contratación del Sector Público')).toContainText('Met expected minimum');
  // A notice with a change seen, and one without.
  await visit(page, '/tenders/301-notice-301', { title: /DefenceGate/, h1: /.+/ });
  await expect(page.getByText('Last change seen at the source').first()).toBeVisible();
  await visit(page, '/tenders/302-notice-302', { title: /DefenceGate/, h1: /.+/ });
  await expect(page.getByText('First seen by us').first()).toBeVisible();
});
