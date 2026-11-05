import { expect, test, type BrowserContext, type Page } from '@playwright/test';

/**
 * Against the fake API (e2e/support/fake-api.mjs): opening a counted report's page never asks the API to count it, whoever sends the
 * visitor there (security review of 5 November 2026); the page's button does, with a POST. Both counted reports: the company report
 * (/suppliers/{slug}/report) and mode A of "Who to sell to" (/reports/who-to-sell-to/company/{slug}). Tagged @fake-api.
 */
const SLUG = '152001-fake-defence-gmbh';
const PRO = 'a'.repeat(43);

async function signIn(context: BrowserContext, baseURL: string | undefined) {
  const host = new URL(baseURL ?? 'http://127.0.0.1').hostname;
  await context.addCookies([{ name: '__Host-dg_session', value: PRO, domain: host, path: '/', secure: true, httpOnly: true, sameSite: 'Lax' }]);
}

/** How many times the fake API was asked for `path` (its request log: path and query). */
async function asked(page: Page, path: string): Promise<number> {
  const api = `http://127.0.0.1:${Number(new URL(page.url()).port) + 910}`;
  return ((await (await page.request.get(`${api}/_requests`)).json()) as string[]).filter((r) => r === `${path}?`).length;
}

for (const [name, url, apiPath, button, report] of [
  ['the company report', `/suppliers/${SLUG}/report`, `/v1/account/suppliers/${SLUG}/report`, 'Open the report', '[data-company-report]'],
  ['the supplier report on a company (mode A)', `/reports/who-to-sell-to/company/${SLUG}`, '/v1/account/sell-report', 'Make the report', '[data-sell-report]'],
] as const) {
  test(`${name}: a GET of the page counts nothing, the button counts once`, { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
    await signIn(context, baseURL);
    await page.goto('/calendar');
    const before = await asked(page, apiPath);
    // a visitor sent from another site: the same GET, with the headers a cross-site navigation carries
    const res = await page.request.get(url, { headers: { 'sec-fetch-site': 'cross-site', 'sec-fetch-mode': 'navigate', referer: 'https://elsewhere.example/' } });
    expect(res.status()).toBe(200);
    await page.goto(url);
    await page.reload();
    await expect(page.getByRole('button', { name: button })).toBeVisible();
    await expect(page.locator(report)).toHaveCount(0);
    expect(await asked(page, apiPath), 'opening the page asked the API to count').toBe(before);
    await page.getByRole('button', { name: button }).click();
    await expect(page.locator(report)).toBeVisible();
    expect(await asked(page, apiPath)).toBe(before + 1);
  });
}
