import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-79 (docs/verification/product/wp79-selfcheck.md): accounts with an e-mail address and a password instead of the sign-in link.
 * Without an API (CI) accounts are closed: every account page says so and shows no form. Against the fake account API
 * (e2e/support/fake-accounts.mjs, E2E_FAKE_ACCOUNTS=1, the site behind e2e/support/https-proxy.mjs and
 * E2E_BASE_URL=https://localhost:3443) the forms are filled and sent and the cookies checked.
 */

test.describe('accounts closed (no API)', () => {
  test.skip(!!process.env.E2E_FAKE_ACCOUNTS, 'runs against a site without an account API');

  for (const [path, h1] of [['/signin', 'Sign in'], ['/register', 'Create an account'], ['/signup', 'Create an account'], ['/reset', 'Forgot your password']] as const) {
    test(`${path} says sign-in is not open and shows no password field`, async ({ page }) => {
      await visit(page, path, { title: new RegExp(h1, 'i'), h1, text: ['Sign-in is not open yet'] });
      await expect(page.locator('input[type="password"]')).toHaveCount(0);
      await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/);
    });
  }

  for (const [path, h1] of [['/auth/verify', 'Confirm your address'], ['/auth/reset', 'Set a new password'], ['/signin/code', 'Enter your code']] as const) {
    test(`${path} without its token or ticket says the link is no longer valid`, async ({ page }) => {
      await visit(page, path, { title: /./, h1, text: ['This link is no longer valid'] });
      await expect(page.locator('main form')).toHaveCount(0);     // main: the site header has a search form since WP-86
    });
  }

  // WP-123 moved this test: the 1.7 text is a draft for the owner (docs/legal/drafts/privacy-v1.7-draft.md), not published, and
  // accounts stay closed until it is (backend accounts_problem). Was: the page lists __Host-dg_mfa and Argon2id and says 1.7.
  test('the privacy notice keeps its published version until the owner approves the draft for password accounts', async ({ page }) => {
    await visit(page, '/privacy', { title: /privacy/i, h1: /privacy/i, text: ['Version 1.6', '__Host-dg_session'] });
    await expect(page.locator('main')).not.toContainText('Version 1.7');
    await expect(page.locator('main')).not.toContainText('Argon2id');
  });
});

test.describe('against the fake account API', () => {
  test.skip(!process.env.E2E_FAKE_ACCOUNTS, 'needs E2E_FAKE_ACCOUNTS=1 and a site started with DG_API_URL=http://127.0.0.1:4011');
  // The `__Host-` cookies need https: the run goes through e2e/support/https-proxy.mjs with a throwaway certificate.
  test.use({ ignoreHTTPSErrors: true });

  test('registration: a short password is refused with the reason and the address kept; a good one says "check your mail"', async ({ page }) => {
    await page.goto('/register');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill('new@example.test');
    await page.getByLabel('Password', { exact: true }).fill('too short');
    await page.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Create account' }).click();
    await expect(page.getByText('Choose another password: use at least 12 characters.')).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'E-mail address' })).toHaveValue('new@example.test');
    await expect(page.getByLabel('Password', { exact: true })).toHaveValue('');                       // never handed back
    await page.getByLabel('Password', { exact: true }).fill('a long enough passphrase');
    await page.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Create account' }).click();
    await expect(page.getByRole('heading', { name: 'Check your mail' })).toBeVisible();
  });

  test('registration without the tick is refused', async ({ page }) => {
    await page.goto('/register');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill('new@example.test');
    await page.getByLabel('Password', { exact: true }).fill('a long enough passphrase');
    await page.getByRole('button', { name: 'Create account' }).click();
    await expect(page.getByText('Tick the box to accept the terms of use and the privacy notice.')).toBeVisible();
  });

  test('sign-in: a wrong password says so; the right one sets an HttpOnly, Secure, SameSite=Lax session cookie', async ({ page, context }) => {
    await page.goto('/signin');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill('ann@example.test');
    await page.getByLabel('Password', { exact: true }).fill('not the password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByText('The e-mail address or the password is wrong.')).toBeVisible();
    await page.getByLabel('Password', { exact: true }).fill('right password here');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForURL(/\/app$/);
    const cookie = (await context.cookies()).find((c) => c.name === '__Host-dg_session');
    expect(cookie, 'the session cookie').toBeTruthy();
    expect([cookie!.httpOnly, cookie!.secure, cookie!.sameSite, cookie!.path]).toEqual([true, true, 'Lax', '/']);
  });

  test('two-step sign-in: the password leads to the code page, a wrong code is refused, the right one signs in', async ({ page, context }) => {
    await page.goto('/signin');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill('totp@example.test');
    await page.getByLabel('Password', { exact: true }).fill('right password here');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForURL(/\/signin\/code$/);
    const ticket = (await context.cookies()).find((c) => c.name === '__Host-dg_mfa');
    expect([ticket?.httpOnly, ticket?.secure, ticket?.sameSite]).toEqual([true, true, 'Lax']);
    expect((await context.cookies()).some((c) => c.name === '__Host-dg_session')).toBe(false);
    await page.getByLabel('Code').fill('000000');
    await page.getByRole('button', { name: 'Continue' }).click();
    await expect(page.getByText('That code is not valid.')).toBeVisible();
    await page.getByLabel('Code').fill('123456');
    await page.getByRole('button', { name: 'Continue' }).click();
    await page.waitForURL(/\/app$/);
    const names = (await context.cookies()).map((c) => c.name);
    expect(names).toContain('__Host-dg_session');
    expect(names).not.toContain('__Host-dg_mfa');
  });

  test('reset: the request answers "check your mail"; the link sets a new password once the policy is met', async ({ page }) => {
    await page.goto('/reset');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill('anyone@example.test');
    await page.getByRole('button', { name: 'Send the link' }).click();
    await expect(page.getByRole('heading', { name: 'Check your mail' })).toBeVisible();
    await page.goto(`/auth/reset?token=${'k'.repeat(43)}`);
    await page.getByLabel('New password').fill('short');
    await page.getByRole('button', { name: 'Set the new password' }).click();
    await expect(page.getByText('Choose another password: use at least 12 characters.')).toBeVisible();
    await page.getByLabel('New password').fill('a long enough passphrase');
    await page.getByRole('button', { name: 'Set the new password' }).click();
    await expect(page.getByRole('heading', { name: 'Your new password is set' })).toBeVisible();
    await page.goto(`/auth/reset?token=${'x'.repeat(43)}`);
    await page.getByLabel('New password').fill('a long enough passphrase');
    await page.getByRole('button', { name: 'Set the new password' }).click();
    await expect(page.getByRole('heading', { name: 'This link is no longer valid' })).toBeVisible();
  });

  test('settings: change the password, and set up two-step sign-in with a first code and recovery codes shown once', async ({ page }) => {
    await page.goto('/signin');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill('ann@example.test');
    await page.getByLabel('Password', { exact: true }).fill('right password here');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForURL(/\/app$/);
    await page.goto('/app/settings');
    await page.getByLabel('Current password').fill('not it');
    await page.getByLabel('New password').fill('a long enough passphrase');
    await page.getByRole('button', { name: 'Change password' }).click();
    await expect(page.getByText('The current password is wrong. Nothing was changed.')).toBeVisible();
    await page.getByLabel('Current password').fill('right password here');
    await page.getByLabel('New password').fill('a long enough passphrase');
    await page.getByRole('button', { name: 'Change password' }).click();
    await expect(page.getByText('Your password is changed. Every other browser was signed out.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign out everywhere' })).toBeVisible();

    await page.getByLabel('Your password').fill('right password here');
    await page.getByRole('button', { name: 'Set up two-step sign-in' }).click();
    await expect(page.getByLabel('Key')).toHaveText('JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP');
    await page.getByLabel('2. The six-digit code the app shows').fill('000000');
    await page.getByRole('button', { name: 'Turn on two-step sign-in' }).click();
    await expect(page.getByText('That code is not valid.', { exact: false })).toBeVisible();
    await expect(page.getByLabel('Key')).toBeVisible();                              // the key stays for another try
    await page.getByLabel('2. The six-digit code the app shows').fill('123456');
    await page.getByRole('button', { name: 'Turn on two-step sign-in' }).click();
    await expect(page.getByText('Two-step sign-in is on.')).toBeVisible();
    await expect(page.getByRole('listitem').filter({ hasText: /^abcde-/ })).toHaveCount(10);
  });

  test('confirmation: opening the link does nothing until the button is pressed', async ({ page }) => {
    await page.goto(`/auth/verify?token=${'k'.repeat(43)}`);
    await expect(page.getByRole('button', { name: 'Confirm my address' })).toBeVisible();
    await page.getByRole('button', { name: 'Confirm my address' }).click();
    await expect(page.getByRole('heading', { name: 'Your address is confirmed' })).toBeVisible();
  });
});
