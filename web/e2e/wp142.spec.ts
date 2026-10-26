import { expect, test } from '@playwright/test';

/**
 * WP-142, flake 1: /digest.atom answered 200 to its own ETag in the full run of 26 October 2026. With no issue to list (the demo
 * data has none) the feed's `<updated>` was the second of the request, so two requests a second apart had two bodies and two ETags.
 * The two requests here are more than a second apart on purpose: the race of the flake, made certain. /regulation.atom had the
 * same fallback.
 */
for (const path of ['/digest.atom', '/regulation.atom']) {
  test(`${path}: the ETag of a request still answers 304 a second later`, async ({ request }) => {
    test.skip(test.info().project.name !== 'desktop', 'one run is enough: the file does not depend on the viewport');
    const first = await request.get(path);
    expect(first.status()).toBe(200);
    const etag = first.headers().etag;
    expect(etag).toBeTruthy();
    await new Promise((r) => setTimeout(r, 1_100));
    const again = await request.get(path, { headers: { 'if-none-match': etag } });
    expect(again.status(), `${path} answered 200 to its own ETag a second later`).toBe(304);
    expect((await request.get(path)).headers().etag).toBe(etag);
  });
}
