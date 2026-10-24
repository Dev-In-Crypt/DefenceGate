import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-100 (persona round of 23 October 2026, section E: mobile, feeds, exports; p02, p04, p07, p09). What this proves on the demo build:
 * a tender page puts its deadline and the link to the original on a phone's first screen; a buyer page lists its open tenders before
 * its profile; a feed and a calendar are named after their search and the feed is paged; the tenders CSV is in the list's order, has a
 * value kind on every valued row, reads a publication-date range and a cursor and states its cap; a supplier's contracts and the market
 * tables download as CSV with the source, licence and attribution columns; the calendar says neither "above" nor 1449.
 */

const TENDER = '/tenders/1-framework-agreement-machined-aluminium-housings';
const isMobile = (w: number | undefined) => (w ?? 1280) < 768;

test('a tender page on a phone: the deadline and "View original" are on the first screen', async ({ page }) => {
  await visit(page, TENDER, { title: /DefenceGate/, h1: /.+/ });
  const vw = page.viewportSize();
  const first = page.locator('[data-phone-first]');
  if (!isMobile(vw?.width)) {
    await expect(first).toBeHidden();
    return;
  }
  const deadline = first.locator('[data-deadline]');
  await expect(deadline).toBeVisible();
  const box = await deadline.boundingBox();
  expect(box!.y + box!.height, 'the deadline ends inside the first screen').toBeLessThanOrEqual(vw!.height);
  const original = first.getByRole('link', { name: /View original/ });
  await expect(original).toBeVisible();
  const o = await original.boundingBox();
  expect(o!.y + o!.height, 'and the link to the original').toBeLessThanOrEqual(vw!.height);
});

test('a buyer page lists its open tenders before its profile tables', async ({ page }) => {
  await visit(page, '/buyers/1-demo-armaments-agency', { title: /DefenceGate/, h1: /.+/ });
  const open = await page.locator('#open-tenders').boundingBox();
  const profile = page.locator('#buyer-profile');
  if (await profile.count()) expect(open!.y).toBeLessThan((await profile.boundingBox())!.y);
});

test('the change feed is named after its search, paged, and says how many there are', async ({ request }) => {
  const plain = await (await request.get('/changes.atom')).text();
  expect(plain).toContain('<title>DefenceGate: what changed</title>');
  const res = await request.get('/changes.atom?q=radar&country=DE,PL');
  expect(res.status()).toBe(200);
  expect(await res.text()).toContain('<title>DefenceGate: radar, DE+PL</title>');
  // a page past the last one is a 404 that says how many there are, never an empty feed
  const far = await request.get('/changes.atom?page=40');
  expect(far.status()).toBe(404);
  expect(await far.text()).toMatch(/^This feed has \d+ pages?\.$/);
});

test('the calendar file is named after its search', async ({ request }) => {
  const body = await (await request.get('/calendar.ics?kind=tenders&country=DE,PL&q=radar')).text();
  expect(body).toContain('X-WR-CALNAME:DefenceGate tender deadlines: radar\\, DE+PL');
});

test('the tenders CSV: the list order, a value kind on every valued row, a publication range, a cursor, and its cap said', async ({ request }) => {
  const res = await request.get('/tenders/export.csv', { timeout: 45_000 });
  expect(res.status()).toBe(200);
  expect(res.headers()['x-row-cap-note']).toMatch(/^At most 2,000 rows a file/);
  const lines = (await res.text()).replace(/^﻿/, '').trim().split(/\r?\n/);
  const header = lines[0].split(',');
  const cells = (l: string) => l.match(/("([^"]|"")*"|[^,]*)(,|$)/g)!.map((c) => c.replace(/,$/, '').replace(/^"|"$/g, ''));
  const rows = lines.slice(1).map(cells);
  const [value, kind, scope, deadline] = ['value', 'value_kind', 'scope', 'deadline_utc'].map((c) => header.indexOf(c));
  for (const r of rows) if (r[value]) expect(r[kind], `row ${r[0]} has a value and a kind`).not.toBe('');
  // the list's default: military goods and works first, each part soonest deadline first
  const scopes = rows.map((r) => r[scope]);
  expect(scopes.indexOf('supply') === -1 || scopes.lastIndexOf('core') < scopes.indexOf('supply')).toBe(true);
  const coreDeadlines = rows.filter((r) => r[scope] === 'core' && r[deadline]).map((r) => Date.parse(r[deadline]));
  expect([...coreDeadlines].sort((a, b) => a - b)).toEqual(coreDeadlines);

  const bad = await request.get('/tenders/export.csv?publishedFrom=2025-13-40');
  expect(bad.status()).toBe(400);
  const ranged = await request.get('/tenders/export.csv?status=all&publishedFrom=2099-01-01');
  expect(ranged.status()).toBe(200);
  expect((await ranged.text()).replace(/^﻿/, '').trim().split(/\r?\n/)).toHaveLength(1);
  const part = await request.get('/tenders/export.csv?cursor=2');
  expect(part.status()).toBe(200);
  expect((await part.text()).trim().split(/\r?\n/).length).toBe(lines.length - 2);
});

test('a supplier page downloads every contract as CSV, with source, licence and attribution', async ({ page, request }) => {
  await visit(page, '/suppliers/1-demo-airframes-gmbh', { title: /Demo Airframes/i, h1: 'Demo Airframes GmbH' });
  const link = page.locator('[data-supplier-csv]');
  await expect(link).toHaveAttribute('href', '/suppliers/1-demo-airframes-gmbh/contracts.csv');
  const res = await request.get('/suppliers/1-demo-airframes-gmbh/contracts.csv');
  expect(res.status()).toBe(200);
  expect(res.headers()['content-type']).toContain('text/csv');
  const body = (await res.text()).replace(/^﻿/, '');
  // WP-112 (p07): the company number after the name
  expect(body.split(/\r?\n/)[0]).toBe('supplier,company_number,notice_id,title,buyer,buyer_country,published,cpv,value,currency,value_kind,in_contract_sum,winners_in_notice,framework_notice_id,source_name,source_url,licence,attribution,page_url,result_truncated');
  expect(body).toContain('Commission Decision 2011/833/EU');
  expect((await request.get('/suppliers/999-nobody/contracts.csv')).status()).toBe(404);
});

test('the market page downloads its tables as CSV, for the same filters', async ({ page, request }) => {
  await visit(page, '/market?cpv=35', { title: /Market/i, h1: 'Market overview' });
  await expect(page.locator('[data-market-csv]')).toHaveAttribute('href', '/market/export.csv?cpv=35');
  const res = await request.get('/market/export.csv?cpv=35');
  expect(res.status()).toBe(200);
  const lines = (await res.text()).replace(/^﻿/, '').trim().split(/\r?\n/);
  expect(lines[0]).toBe('table,key,label,notices,ted,national_sources,partial_month,period,buyer_country,cpv,scope,unit,as_of_utc,source_name,licence,attribution,page_url');
  for (const table of ['month', 'country', 'cpv_group', 'source']) expect(lines.some((l) => l.startsWith(`${table},`)), table).toBe(true);
});

test('the calendar: one number format, and no "deadlines above" over a list that comes below', async ({ page }) => {
  await visit(page, '/calendar', { title: /calendar/i, h1: 'Deadline calendar' });
  await expect(page.locator('#feed-heading + p')).not.toContainText('above');
  await expect(page.locator('#results-heading')).not.toHaveText(/\d{4} upcoming/);
});
