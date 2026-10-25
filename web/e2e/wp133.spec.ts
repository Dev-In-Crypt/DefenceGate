import { expect, test, type APIRequestContext } from '@playwright/test';

/**
 * WP-133 (docs/verification/round6/wp133-selfcheck.md). The API answers an old id of a merged organisation with its head
 * under the head's slug (backend/tests/integration/test_wp133.py); this spec checks the web half: a buyer, supplier or
 * organisation page asked under a slug that is not the one the API gives answers a permanent redirect (308) to it, and the
 * page under its own slug is served as it is. The buyer page says which count it shows.
 */

async function slugFrom(request: APIRequestContext, file: string, kind: string): Promise<string> {
  const xml = await (await request.get(`/sitemaps/${file}`)).text();
  const m = new RegExp(`<loc>[^<]*/${kind}/(\\d+-[^<]+)</loc>`).exec(xml);
  expect(m, `${kind} in ${file}`).not.toBeNull();
  return m![1];
}

for (const [kind, file] of [['buyers', 'pages.xml'], ['suppliers', 'suppliers.xml'], ['organisations', 'pages.xml']] as const) {
  test(`an old /${kind} address redirects permanently to the current one; the current one is served`, async ({ request }) => {
    const slug = await slugFrom(request, file, kind);
    const id = slug.split('-')[0];
    const old = await request.get(`/${kind}/${id}-an-old-name`, { maxRedirects: 0 });
    expect(old.status()).toBe(308);
    expect(old.headers().location).toBe(`/${kind}/${slug}`);
    expect((await request.get(`/${kind}/${slug}`, { maxRedirects: 0 })).status()).toBe(200);
  });
}

test('the buyer page says its tender count shows a national copy of a TED notice once', async ({ page, request }) => {
  await page.goto(`/buyers/${await slugFrom(request, 'pages.xml', 'buyers')}`);
  await expect(page.locator('[data-count-basis]')).toHaveText(
    'A national notice that is a copy of a TED notice is counted once, so the count can be lower than the notices we hold.');
});
