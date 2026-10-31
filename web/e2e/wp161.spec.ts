import { createHmac } from 'node:crypto';
import { expect, test, type Page } from '@playwright/test';

/**
 * WP-161 (docs/verification/features/wp161-selfcheck.md): launch day's main path, as a new customer walks it, against the fake account
 * API (e2e/support/fake-accounts.mjs, the "launch" customer): sign up -> confirm -> sign in -> Free -> a plan through a signed billing
 * event forwarded by the site's webhook route (an unsigned or forged one changes nothing) -> Team: the workspace and an invitation ->
 * the supplier-map CSV, refused before the plan and served after it. The rules themselves are tested against the real API
 * (backend/tests/integration/test_wp161.py and the files of each package); the whole stack with every switch on was walked by the
 * rehearsal (the self-check). Also: the public pages that must not break on launch day (imprint with no provider details, the stop
 * page of an alert mail).
 */

const PASSWORD = 'a long enough passphrase';
const SECRET = 'whsec_fake_launch_only';                     // the fake's; never a real secret

const noSideScroll = async (page: Page) => {
  const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  expect(scroll).toBeLessThanOrEqual(client);
};

test.describe('launch-day pages that need no account (default build)', () => {
  test.skip(!!process.env.E2E_FAKE_ACCOUNTS || !!process.env.E2E_REAL_ACCOUNTS, 'runs against the default build');

  test('the imprint with no provider details shows no empty label and no placeholder', async ({ page }) => {
    await page.goto('/imprint');
    await expect(page.locator('h1')).toHaveText('Imprint');
    await expect(page.getByText('not published yet')).toBeVisible();
    await expect(page.locator('main')).not.toContainText(/to be provided|text pending|\[|\]/);
    await expect(page.locator('main dt')).toHaveCount(0);
    await noSideScroll(page);
  });

  test('the stop page of an alert mail asks before it stops, and an incomplete link says so', async ({ page }) => {
    await page.goto(`/unsubscribe?kind=alerts&token=${'b'.repeat(64)}`);
    await expect(page.locator('h1')).toHaveText('Stop the e-mail alerts');
    await expect(page.getByRole('button', { name: 'Stop the alerts' })).toBeVisible();
    await page.goto('/unsubscribe?kind=alerts&token=short');
    await expect(page.locator('[data-unsubscribe-invalid]')).toContainText('alert mail');
    await expect(page.getByRole('button', { name: 'Stop the alerts' })).toHaveCount(0);
    await noSideScroll(page);
  });

  test('no horizontal scroll at 320 px on the imprint and the stop page, in both themes (screenshots at 1440 for the self-check)', async ({ page }, info) => {
    for (const scheme of ['light', 'dark'] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      for (const [name, path] of [['imprint', '/imprint'], ['stop-alerts', `/unsubscribe?kind=alerts&token=${'b'.repeat(64)}`]]) {
        await page.setViewportSize({ width: 320, height: 800 });
        await page.goto(path);
        await noSideScroll(page);
        if (process.env.E2E_SHOTS && info.project.name === 'desktop') {
          await page.setViewportSize({ width: 1440, height: 900 });
          await page.screenshot({ path: `${process.env.E2E_SHOTS}/${name}-1440-${scheme}.png`, fullPage: true });
        }
      }
    }
  });
});

test.describe('launch day, the main path, against the fake account API', () => {
  test.skip(!process.env.E2E_FAKE_ACCOUNTS, 'needs E2E_FAKE_ACCOUNTS=1 and a site started with DG_API_URL pointing at e2e/support/fake-accounts.mjs');
  test.use({ ignoreHTTPSErrors: true });

  test('sign up -> confirm -> sign in -> plan by a signed event -> team invitation -> supplier-map CSV', async ({ page }, info) => {
    const email = `launch-${info.project.name}-${Date.now()}@example.test`;
    // sign up and confirm
    await page.goto('/signup?plan=team&billing=yearly');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill(email);
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
    await page.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Create account' }).click();
    await expect(page.getByRole('heading', { name: 'Check your mail' })).toBeVisible();
    await page.goto(`/auth/verify?token=${'k'.repeat(43)}`);
    await page.getByRole('button', { name: 'Confirm my address' }).click();
    await expect(page.getByRole('heading', { name: 'Your address is confirmed' })).toBeVisible();
    // sign in: Free
    await page.goto('/signin');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill(email);
    await page.getByLabel('Password', { exact: true }).fill('right password here');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForURL(/\/app$/);
    await page.goto('/app/billing');
    await expect(page.locator('[data-current-plan]')).toContainText('Your plan is Free.');
    // a Free account is told saved searches are a plan's (the page said to go and save one)
    await page.goto('/app/searches');
    await expect(page.getByText('Saved searches and their e-mail alerts are part of the Pro, Team and Consultant plans.')).toBeVisible();
    await expect(page.getByText('choose Save this search')).toHaveCount(0);
    // the supplier-map CSV is refused before the plan: back to the page
    const before = await page.request.get('/suppliers/export.csv?country=DE', { maxRedirects: 0 });
    expect(before.status()).toBe(303);

    // the plan: Creem's event through the site's webhook route; unsigned and forged ones change nothing
    const event = JSON.stringify({ id: `evt_${Date.now()}`, eventType: 'checkout.completed', created_at: Date.now(),
      object: { metadata: { email, plan: 'team' } } });
    const post = (signature?: string) => page.request.post('/api/billing/webhook', { data: event,
      headers: { 'content-type': 'application/json', ...(signature ? { 'creem-signature': signature } : {}) } });
    expect((await post()).status()).toBe(401);
    expect((await post(createHmac('sha256', 'whsec_somebody_else').update(event).digest('hex'))).status()).toBe(401);
    await page.goto('/app/billing');
    await expect(page.locator('[data-current-plan]')).toContainText('Your plan is Free.');
    expect((await post(createHmac('sha256', SECRET).update(event).digest('hex'))).status()).toBe(200);
    await page.goto('/app/billing');
    await expect(page.locator('[data-current-plan]')).toContainText('Team');
    await expect(page.locator('[data-status="active"]')).toBeVisible();
    await page.goto('/app/searches');
    await expect(page.getByText(/No saved searches yet\..*Save this search/)).toBeVisible();

    // Team: the workspace and an invitation
    await page.goto('/app/team');
    await page.getByRole('button', { name: 'Make the workspace' }).click();
    await expect(page.locator('[data-member]').first()).toContainText('Owner');
    const colleague = `colleague-${info.project.name}-${Date.now()}@example.test`;
    await page.getByLabel('Their e-mail address').fill(colleague);
    await page.getByRole('button', { name: 'Send invitation' }).click();
    await expect(page.getByText('Invitation sent.')).toBeVisible();
    await expect(page.locator('[data-invite]', { hasText: colleague })).toBeVisible();
    await noSideScroll(page);
    if (process.env.E2E_SHOTS) await page.screenshot({ path: `${process.env.E2E_SHOTS}/launch-team-${info.project.name}.png`, fullPage: true });

    // the export: served now, private
    const csv = await page.request.get('/suppliers/export.csv?country=DE', { maxRedirects: 0 });
    expect(csv.status()).toBe(200);
    expect(csv.headers()['content-type']).toContain('text/csv');
    expect(csv.headers()['cache-control']).toBe('private, no-store');
    expect(csv.headers()['content-disposition']).toMatch(/^attachment; filename="defencegate-suppliers-/);
  });
});
