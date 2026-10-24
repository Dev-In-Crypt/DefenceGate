import { expect, test } from '@playwright/test';

/**
 * WP-114 (coverage audit of 24 October 2026): the sitemap is an index of files (the pages, the suppliers, every core tender
 * by id range); the machine outputs answer conditional requests with 304; a feed page past the end is a 404, not a 502; a
 * CSV export refuses a parameter it does not read, as the feeds do. Requests only (no page is rendered in a browser).
 */
test.skip(({ isMobile }) => isMobile, 'requests only: once is enough');

test('the sitemap is an index of the pages, the suppliers and the tenders', async ({ request }) => {
  const index = await request.get('/sitemap.xml');
  expect(index.status()).toBe(200);
  const xml = await index.text();
  expect(xml).toContain('<sitemapindex');
  for (const f of ['pages.xml', 'suppliers.xml', 'tenders-0.xml']) expect(xml).toContain(`/sitemaps/${f}</loc>`);
  expect(await (await request.get('/sitemaps/pages.xml')).text()).toContain('/check</loc>');
  expect(await (await request.get('/sitemaps/suppliers.xml')).text()).toMatch(/\/suppliers\/1-demo-airframes-gmbh<\/loc>/);
  expect(await (await request.get('/sitemaps/tenders-0.xml')).text()).toMatch(/\/tenders\/\d+-[a-z0-9-]+<\/loc>/);
  expect((await request.get('/sitemaps/tenders-99.xml')).status()).toBe(404);
  expect((await request.get('/sitemaps/other.xml')).status()).toBe(404);
});

test('the sitemap, the calendar file and the CSV answer a conditional request with 304', async ({ request }) => {
  for (const path of ['/sitemap.xml', '/sitemaps/pages.xml', '/calendar.ics', '/tenders/export.csv?country=FR']) {
    const first = await request.get(path);
    expect(first.status(), path).toBe(200);
    const etag = first.headers().etag;
    expect(etag, path).toBeTruthy();
    const again = await request.get(path, { headers: { 'if-none-match': etag } });
    expect(again.status(), path).toBe(304);
    expect((await again.body()).length, path).toBe(0);
  }
});

test('the data page names a data check in alert and since when', async ({ request }) => {
  const html = await (await request.get('/data')).text();
  expect(html).toContain('Data checks in alert');
  expect(html).toContain('Spanish data check in alert');
  expect(html).toContain('In alert since');
});

test('a change feed page past the end is a 404; a CSV with an unknown parameter is a 422', async ({ request }) => {
  expect((await request.get('/changes.atom?page=999')).status()).toBe(404);
  const csv = await request.get('/tenders/export.csv?country=FR&bogus=1');
  expect(csv.status()).toBe(422);
  expect(await csv.text()).toContain('bogus');
  expect((await request.get('/funding/export.csv?bogus=1')).status()).toBe(422);
});
