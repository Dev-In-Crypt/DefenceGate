import { expect, test } from '@playwright/test';
import { pace, visit } from './helpers';

/**
 * The funding section after the persona walk-through of 16 October 2026 (ux-funding). Read-only; the same file runs
 * against a local build with the demo data and against a real site, so it asks for shapes, not for particular calls.
 */

const heading = (page: import('@playwright/test').Page) => page.locator('#results-heading');

// WP-43 (verification 3): the first page of calls is ordinary HTML in the first response. A loading file made the server send a
// skeleton in place and the list as a hidden block that only a script swaps in, so a visitor without scripts saw "Loading".
test('the first page of calls is in the HTML the server sends, before any hidden block', async ({ request }) => {
  const html = await (await request.get('/funding?status=all')).text();
  const hidden = html.indexOf('<div hidden id="S:');
  const visible = hidden === -1 ? html : html.slice(0, hidden);
  expect(visible).toMatch(/<h2[^>]*>\s*<a [^>]*href="\/funding\/\d+-[^"]*"[^>]*>[^<]+<\/a>/);
  expect(visible).toMatch(/Showing 1/);
  expect(html).not.toContain('Loading funding calls');
});

test('with scripts off the list, its filters and the pager still work as links', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto('/funding?status=all');
  await expect(page.locator('a[href^="/funding/"]:not([href*="export"])').first()).toBeVisible();
  await expect(heading(page)).toContainText(/Showing 1/);
  await context.close();
});

test('search: a hyphen and a space are the same search', async ({ page }) => {
  await visit(page, '/funding?status=all&q=counter-drone', { title: /funding/i, h1: /funding/i });
  const hyphen = (await heading(page).textContent())?.trim();
  await visit(page, '/funding?status=all&q=counter%20drone', { title: /funding/i, h1: /funding/i });
  expect((await heading(page).textContent())?.trim()).toBe(hyphen);
});

test('search: a synonym is searched and the page says so', async ({ page }) => {
  await visit(page, '/funding?status=all&q=drone', { title: /funding/i, h1: /funding/i });
  await expect(page.getByText(/Also searched: .*unmanned/)).toBeVisible();
});

test('an empty list names the search word and offers a looser search with its count', async ({ page }) => {
  await visit(page, '/funding?q=zzzxx-nothing', { title: /funding/i, h1: /funding/i, text: ['No calls match'] });
  await expect(page.getByText(/Nothing matches the search .zzzxx-nothing./)).toBeVisible();
  const way = page.getByRole('link', { name: /calls? match(es)? without the search .zzzxx-nothing./ });
  await expect(way).toBeVisible();
  await Promise.all([page.waitForURL((u) => !u.searchParams.has('q')), way.click()]);
  await expect(heading(page)).toContainText(/Showing 1/);
  await pace(page);
});

test('a closed list starts with the newest deadline', async ({ page }) => {
  await visit(page, '/funding?status=closed', { title: /funding/i, h1: /funding/i });
  await expect(page.getByLabel('Sort')).toHaveValue('deadline-desc');
});

test('a call page says who pays, who can apply, the terms and where the official text is', async ({ page }) => {
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i });
  const href = await page.locator('a[href^="/funding/"]:not([href*="export"])').first().getAttribute('href');
  expect(href, 'a call link on /funding').toMatch(/^\/funding\/\d+/);
  await visit(page, href!, { title: /DefenceGate/, h1: /.+/ });
  await expect(page.getByRole('heading', { name: 'Who can apply', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Terms', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Eligibility', exact: true })).toHaveCount(0);
  await expect(page.getByText('Funder', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Programme', { exact: true }).first()).toBeVisible();
  // The way to the official text: a link, or the plain statement that the source gives none.
  await expect(page.getByRole('link', { name: /official call text|View original/ }).or(page.getByText(/source gives no link/)).first()).toBeVisible();
});

test('the calendar offers a subscription and the file carries openings as events of their own', async ({ page, request }) => {
  await visit(page, '/calendar?kind=funding', { title: /calendar/i, h1: 'Deadline calendar' });
  const subscribe = page.getByRole('link', { name: /subscribe in your calendar app/i });
  await expect(subscribe).toHaveAttribute('href', /^webcal:\/\/.+\/calendar\.ics\?kind=funding$/);
  test.skip(test.info().project.name !== 'desktop', 'one run is enough: the file does not depend on the viewport');
  const res = await request.get('/calendar.ics?kind=funding');
  expect(res.status()).toBe(200);
  const body = (await res.text()).replace(/\r\n /g, '');
  // Every event has its own UID; an opening is `...-opens@...`, never the same UID as the call's deadline.
  const uids = [...body.matchAll(/^UID:(.+)\r?$/gm)].map((m) => m[1]);
  expect(new Set(uids).size).toBe(uids.length);
  expect(body).not.toMatch(/[A-Z0-9._%+-]+@(?!defencegatehub)[A-Z0-9-]+\.[A-Z]{2,}/i);
});

test('the glossary explains the funding terms', async ({ page }) => {
  await visit(page, '/glossary', { title: /glossary/i, h1: 'Glossary' });
  for (const id of ['edf', 'edip', 'horizon-europe', 'horizon-cluster-3', 'digital-europe', 'dual-use', 'call-status', 'date-only-deadline']) {
    await expect(page.locator(`#${id}`), id).toHaveCount(1);
  }
  await expect(page.locator('#dual-use')).toContainText('the label is ours');
});

test('/changes lists new funding calls apart from the notices, when there are any', async ({ page }) => {
  await visit(page, '/changes', { title: /what changed/i, h1: 'What changed' });
  const section = page.locator('#funding-heading');
  if ((await section.count()) > 0) {
    await expect(section).toContainText('Funding calls');
    await expect(page.locator('a[href^="/funding/"]').first()).toBeVisible();
  }
});
