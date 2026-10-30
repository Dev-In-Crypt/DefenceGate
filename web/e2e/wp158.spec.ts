import { expect, test, type Page } from '@playwright/test';

/**
 * WP-158 (docs/verification/features/wp158-selfcheck.md): the association page of the account area and the stop link of the
 * association's digest mail. The licence, the plan it gives, the digest job and the token are tested against the API:
 * backend/tests/integration/test_associations_wp158.py.
 */

const shots = process.env.WP158_SHOTS;

async function noSideScroll(page: Page, label: string) {
  const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  expect(scroll, label).toBeLessThanOrEqual(client);
}

test.describe('the stop link and the gate (no API needed)', () => {
  test.skip(!!process.env.E2E_FAKE_ACCOUNTS, 'the public part runs against the default build');

  test('/unsubscribe without a whole token says so, changes nothing and is not indexed', async ({ page }) => {
    await page.goto('/unsubscribe?token=abc');
    await expect(page.locator('h1')).toHaveText('Stop the weekly digest');
    await expect(page.locator('[data-unsubscribe-invalid]')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Stop the digest' })).toHaveCount(0);
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/);
  });

  test('/unsubscribe has no horizontal scroll at 320 px, in both themes', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 800 });
    for (const scheme of ['light', 'dark'] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto(`/unsubscribe?token=${'a'.repeat(64)}`);
      await noSideScroll(page, scheme);
    }
  });

  test('/app/association is behind sign-in', async ({ page }) => {
    await page.goto('/app/association');
    await expect(page).toHaveURL(/\/signin\?next=%2Fapp%2Fassociation$/);
  });
});

test.describe('the association, against the fake account API', () => {
  test.skip(!process.env.E2E_FAKE_ACCOUNTS, 'needs E2E_FAKE_ACCOUNTS=1 and a site started with DG_API_URL pointing at e2e/support/fake-accounts.mjs');
  test.use({ ignoreHTTPSErrors: true });

  test.beforeEach(async ({ page }) => {
    await page.goto('/signin');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill('ann@example.test');
    await page.getByLabel('Password', { exact: true }).fill('right password here');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForURL(/\/app$/);
  });

  test('the admin sees the plan, the seats counted, and saves the digest choice', async ({ page }, info) => {
    if ((page.viewportSize()?.width ?? 1280) < 1024) await page.getByText('Menu', { exact: true }).click();
    await page.getByRole('link', { name: 'Association' }).click();
    await expect(page.locator('h1')).toHaveText('Cluster Example');
    await expect(page.locator('[data-association-plan]')).toContainText('Team features, as the association\'s admin');
    await expect(page.locator('[data-association-seats]')).toContainText('12 of 50 seats are used');

    const form = page.locator('[data-association-digest]');
    await form.getByLabel('Send me the digest').selectOption('on');
    await form.getByLabel('Country').selectOption('ES');
    await form.getByLabel('CPV codes').fill('35, 3441');
    await form.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Saved.' })).toBeVisible();
    await expect(form.getByLabel('Country')).toHaveValue('ES');
    await expect(form.getByLabel('CPV codes')).toHaveValue('35, 3441');

    await form.getByLabel('CPV codes').fill('vehicles');
    await form.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'One of the values was not accepted' })).toBeVisible();
    await noSideScroll(page, 'association');

    if (shots) {
      for (const scheme of ['light', 'dark'] as const) {
        await page.emulateMedia({ colorScheme: scheme });
        await page.goto('/app/association');
        await page.screenshot({ path: `${shots}/association-${info.project.name}-${scheme}.png`, fullPage: true });
      }
    }
  });

  test('the stop link asks before it stops, then says it is done', async ({ page }, info) => {
    await page.goto(`/unsubscribe?token=${'a'.repeat(64)}`);
    if (shots) await page.screenshot({ path: `${shots}/unsubscribe-${info.project.name}.png`, fullPage: true });
    await page.getByRole('button', { name: 'Stop the digest' }).click();
    await expect(page).toHaveURL(/\/unsubscribe\?done=1$/);
    await expect(page.locator('[data-unsubscribed]')).toContainText('not sent to you any more');
    await page.goto('/app/association');
    await expect(page.locator('[data-association-digest]').getByLabel('Send me the digest')).toHaveValue('off');
  });
});
