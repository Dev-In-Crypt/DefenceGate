import { expect, test } from '@playwright/test';

/**
 * WP-120 (speed and caching, round-6 system audit of 25 October 2026): the change feed answers its own Last-Modified with
 * 304 (it sent 200 and the whole feed), the calendar file and the funding feed answer a revalidation from a kept build with
 * the same caching, and the buyer page's full open and planned lists are an address of their own, not indexed. Requests only.
 */
test.skip(({ isMobile }) => isMobile, 'requests only: once is enough');

test('the change feed and the digest feed answer their own Last-Modified with 304', async ({ request }) => {
  for (const path of ['/changes.atom', '/digest.atom']) {
    const first = await request.get(path);
    expect(first.status(), path).toBe(200);
    const lastModified = first.headers()['last-modified'];
    expect(lastModified, path).toBeTruthy();
    const again = await request.get(path, { headers: { 'if-modified-since': lastModified } });
    expect(again.status(), path).toBe(304);
    expect((await again.body()).length, path).toBe(0);
  }
});

test('the calendar file and the funding feed revalidate with 304 and keep their caching', async ({ request }) => {
  for (const path of ['/calendar.ics', '/funding.atom']) {
    const first = await request.get(path);
    expect(first.status(), path).toBe(200);
    const again = await request.get(path, { headers: { 'if-none-match': first.headers().etag } });
    expect(again.status(), path).toBe(304);
    expect(again.headers()['cache-control'], path).toBe('public, max-age=3600');
    expect(again.headers().etag, path).toBe(first.headers().etag);
  }
});

test('the buyer page with all its open and planned tenders is not indexed', async ({ request }) => {
  const all = await request.get('/buyers/4-demo-defence-materiel-organisation?all=1');
  expect(all.status()).toBe(200);
  expect(await all.text()).toMatch(/<meta name="robots" content="noindex/);
  const page = await request.get('/buyers/4-demo-defence-materiel-organisation');
  expect(await page.text()).not.toMatch(/<meta name="robots" content="noindex/);
});
