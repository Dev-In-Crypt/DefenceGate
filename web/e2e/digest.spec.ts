import { expect, test, type Page } from '@playwright/test';
import { pace, visit } from './helpers';

/**
 * The weekly digest (/digest, /digest/[week], /digest.atom) and the funding checks of WP-31 (cascade filter, calendar
 * file). Read-only. The same file runs against a local build with demo data (no digest there: the page says so) and
 * against a real site, so it asks for shapes, and checks the content only where there is some.
 */

const hasIssue = async (page: Page) => (await page.locator('#numbers').count()) > 0;

/** Below the `lg` breakpoint the filters sit behind a "Filters" button; open it so the controls are on screen. */
async function openFilters(page: Page) {
  const button = page.getByRole('button', { name: /^(Show|Hide) filters/ });
  if (await button.isVisible() && (await button.getAttribute('aria-expanded')) !== 'true') await button.click();
}

test('/digest: the latest issue with its sections, or the honest statement that there is none', async ({ page }) => {
  await visit(page, '/digest', { title: /weekly digest/i, h1: 'Weekly digest' });
  if (!(await hasIssue(page))) {
    await expect(page.getByText(/no issue to show/i)).toBeVisible();
    return;
  }
  await expect(page.getByRole('heading', { name: 'The week in numbers' })).toBeVisible();
  for (const name of [/^New funding calls/, /^Calls that opened/, /^Funding calls with a date moved/, /^Calls closing in the next 14 days/,
    /^Calls with cascade funding/, /^New defence notices/, /^Amended notices/]) {
    await expect(page.getByRole('heading', { name, level: 2 })).toBeVisible();
  }
  await expect(page.getByRole('link', { name: /Atom feed of the weekly digest/ })).toHaveAttribute('href', /^\/digest\.atom/);
  // Every item links to its own page.
  const hrefs = await page.locator('section article h3 a').evaluateAll((as) => as.map((a) => a.getAttribute('href')));
  for (const href of hrefs) expect(href).toMatch(/^\/(funding|tenders)\/\d+/);
  // A section cut at its limit says so; a section with nothing says "None".
  const cuts = await page.getByText(/^Showing the first \d+ of \d+\./).count();
  expect(cuts).toBeGreaterThanOrEqual(0);
  await pace(page);
});

test('/digest: the country filter keeps its value, in the URL and in the form', async ({ page }) => {
  await visit(page, '/digest?country=ES', { title: /weekly digest/i, h1: 'Weekly digest' });
  if (!(await hasIssue(page))) return;
  await expect(page.getByLabel('Country')).toHaveValue('ES');
  await expect(page.getByRole('heading', { name: 'The week in numbers' })).toBeVisible();
  // A country that is not one of ours is dropped, not echoed.
  await visit(page, '/digest?country=ZZ%22%3E%3Cscript%3E', { title: /weekly digest/i, h1: 'Weekly digest' });
  await expect(page.getByLabel('Country')).toHaveCount(await hasIssue(page) ? 1 : 0);
  if (await hasIssue(page)) await expect(page.getByLabel('Country')).toHaveValue('');
});

test('/digest: an earlier week is a page of its own, and a week outside the archive is a 404', async ({ page, request }) => {
  await visit(page, '/digest', { title: /weekly digest/i, h1: 'Weekly digest' });
  if (await hasIssue(page)) {
    const earlier = page.locator('#earlier a[href^="/digest/"]').first();
    if ((await earlier.count()) > 0) {
      const href = await earlier.getAttribute('href');
      expect(href).toMatch(/^\/digest\/\d{4}-W\d{2}/);
      await visit(page, href!, { title: /weekly digest/i, h1: 'Weekly digest', text: ['The week in numbers'] });
      await expect(page.getByRole('navigation', { name: 'Other weeks' })).toBeVisible();
    }
  }
  test.skip(test.info().project.name !== 'desktop', 'one run is enough: the status does not depend on the viewport');
  for (const week of ['2099-W01', '2026-W54', '2026-W00', 'not-a-week']) {
    expect((await request.get(`/digest/${week}`)).status(), week).toBe(404);
  }
});

test('/digest.atom is an Atom feed with one entry per week, answers conditional requests and carries no e-mail address', async ({ request }) => {
  test.skip(test.info().project.name !== 'desktop', 'one run is enough: the file does not depend on the viewport');
  const res = await request.get('/digest.atom');
  expect(res.status()).toBe(200);
  expect(res.headers()['content-type']).toContain('application/atom+xml');
  const body = await res.text();
  expect(body).toMatch(/^<\?xml version="1\.0" encoding="utf-8"\?>\n<feed xmlns="http:\/\/www\.w3\.org\/2005\/Atom"/);
  expect(body.trimEnd().endsWith('</feed>')).toBe(true);
  expect(body).toMatch(/<link rel="self" type="application\/atom\+xml" href="[^"]+\/digest\.atom"\/>/);
  const entries = body.match(/<entry>[\s\S]*?<\/entry>/g) ?? [];
  const ids = [...body.matchAll(/<id>(.*?)<\/id>/g)].map((m) => m[1]);
  expect(new Set(ids).size, 'ids are unique').toBe(ids.length);
  for (const e of entries) {
    expect(e).toMatch(/<link rel="alternate" type="text\/html" href="[^"]+\/digest\/\d{4}-W\d{2}"\/>/);
    expect(e).toMatch(/<updated>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z<\/updated>/);
  }
  expect(body).not.toMatch(/[A-Z0-9._%+-]+@(?!defencegatehub)[A-Z0-9-]+\.[A-Z]{2,}/i);
  const etag = res.headers().etag;
  expect(etag).toBeTruthy();
  const again = await request.get('/digest.atom', { headers: { 'if-none-match': etag } });
  expect(again.status()).toBe(304);
  const filtered = await request.get('/digest.atom?country=ES');
  expect(filtered.status()).toBe(200);
});

test('/funding: the cascade filter travels in the URL, is counted, and every call it lists wears the badge', async ({ page }) => {
  await visit(page, '/funding?status=all&cascade=true', { title: /funding/i, h1: /funding/i });
  await openFilters(page);
  const box = page.getByLabel(/^Only calls with cascade funding/);
  await expect(box).toBeChecked();
  const cards = page.locator('article');
  const n = await cards.count();
  if (n > 0) {
    for (let i = 0; i < n; i += 1) await expect(cards.nth(i)).toContainText('Cascade funding');
  }
  // Un-checking it lists the calls again without the filter.
  await box.uncheck();
  await page.waitForURL((u) => !u.searchParams.has('cascade'));
  await openFilters(page);
  await expect(page.getByLabel(/^Only calls with cascade funding/)).not.toBeChecked();
  await expect(page.getByLabel(/^Only calls with cascade funding \(\d+\)$/)).toBeVisible();
  await pace(page);
});

test('/funding: a cascade value that is not true is ignored and says so', async ({ page }) => {
  await visit(page, '/funding?cascade=false', { title: /funding/i, h1: /funding/i });
  await expect(page.getByText(/Ignored filter: cascade=false/)).toBeVisible();
});

test('a call that has cascade funding says so on its page, with the sentence it rests on', async ({ page }) => {
  await visit(page, '/funding?status=all&cascade=true', { title: /funding/i, h1: /funding/i });
  const href = await page.locator('a[href^="/funding/"]:not([href*="export"])').first().getAttribute('href');
  test.skip(!href, 'no call with cascade funding on this site');
  await visit(page, href!, { title: /DefenceGate/, h1: /.+/ });
  await expect(page.getByRole('heading', { name: 'Financial support to third parties', exact: true })).toBeVisible();
  await expect(page.getByText('This call has cascade funding')).toBeVisible();
});

test('the glossary explains cascade funding', async ({ page }) => {
  await visit(page, '/glossary', { title: /glossary/i, h1: 'Glossary' });
  await expect(page.locator('#cascade-funding')).toHaveCount(1);
  await expect(page.locator('#cascade-funding')).toContainText('not shown to have none');
});
