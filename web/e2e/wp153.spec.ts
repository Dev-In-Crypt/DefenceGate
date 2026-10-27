import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-153 (docs/verification/features/wp153-selfcheck.md): the data API page and the API keys of the account area.
 * The keys themselves (hash, scopes, the licence filter, limits) are tested against the API: backend/tests/integration/test_api_keys_wp153.py.
 */

test.describe('the /api page (no API needed)', () => {
  test.skip(!!process.env.E2E_FAKE_ACCOUNTS, 'the public part runs against the default build');

  test('/api lists the three key endpoints with their parameters, says licence on request, and is not indexed', async ({ page }) => {
    await visit(page, '/api', { title: /data api/i, h1: 'Data API', text: ['Licence on request.', 'GET /v1/opportunities'] });
    await expect(page.locator('[data-endpoint]')).toHaveCount(3);
    await expect(page.locator('[data-endpoint="/v1/opportunities/{opp_id}/versions"]')).toContainText('Archive');
    await expect(page.locator('[data-endpoint="/v1/opportunities"] dt')).toContainText(['country', 'cpv', 'source']);
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/);
    expect(await page.locator('main').innerText()).not.toMatch(/€|EUR \d|per year:/);     // no prices on the page
  });

  test('/api has no horizontal scroll at 320 px, in both themes', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 800 });
    for (const scheme of ['light', 'dark'] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto('/api');
      const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
      expect(scroll, scheme).toBeLessThanOrEqual(client);
    }
  });

  test('/app/keys is behind sign-in', async ({ page }) => {
    await page.goto('/app/keys');
    await expect(page).toHaveURL(/\/signin\?next=%2Fapp%2Fkeys$/);
  });
});

test.describe('API keys, against the fake account API', () => {
  test.skip(!process.env.E2E_FAKE_ACCOUNTS, 'needs E2E_FAKE_ACCOUNTS=1 and a site started with DG_API_URL pointing at e2e/support/fake-accounts.mjs');
  test.use({ ignoreHTTPSErrors: true });

  test.beforeEach(async ({ page }) => {
    await page.goto('/signin');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill('ann@example.test');
    await page.getByLabel('Password', { exact: true }).fill('right password here');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForURL(/\/app$/);
  });

  test('K: a key is made with the password, shown once, listed by its prefix and revoked with the password', async ({ page }, info) => {
    const name = `Script ${info.project.name} ${Date.now()}`;
    if ((page.viewportSize()?.width ?? 1280) < 1024) await page.getByText('Menu', { exact: true }).click();
    await page.getByRole('link', { name: 'API keys' }).click();
    await expect(page.locator('h1')).toContainText('API keys');

    const form = page.locator('form').filter({ has: page.getByRole('button', { name: 'Make a key' }) });
    await form.getByLabel('Name').fill(name);
    await form.getByLabel('Your password').fill('not the password');
    await form.getByRole('button', { name: 'Make a key' }).click();
    await expect(form.getByRole('alert')).toContainText('The password is wrong');
    await expect(form.getByLabel('Name')).toHaveValue(name);                        // the name typed is kept, the password not

    await form.getByLabel('Your password').fill('right password here');
    await page.getByRole('button', { name: 'Make a key' }).click();
    const shown = page.getByLabel('Your new key');
    await expect(shown).toHaveText(/^dgk_[0-9a-f]{12}_[A-Za-z0-9_-]{43}$/);
    const key = await shown.innerText();
    const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    expect(scroll).toBeLessThanOrEqual(client);

    await page.getByRole('link', { name: 'Done' }).click();
    await expect(page.locator('main')).not.toContainText(key);                     // never shown again
    await expect(form.getByLabel('Name')).toHaveValue('');                          // the form is back, empty
    const row = page.locator('[data-key]', { hasText: name });
    await expect(row).toContainText(`dgk_${key.slice(4, 16)}_`);
    await expect(row).toContainText('never used');

    await row.getByLabel('Your password').fill('right password here');
    await row.getByRole('button', { name: 'Revoke this key' }).click();
    await expect(page.getByText('The key is revoked.')).toBeVisible();
    await expect(page.locator('[data-key]', { hasText: name })).toContainText('Revoked');
  });
});
