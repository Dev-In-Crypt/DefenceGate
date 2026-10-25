import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-123 (docs/verification/accounts/wp123-selfcheck.md): accounts with an e-mail address and a password, end to end.
 *
 * Without an API (CI) accounts are closed: /signup says so, shows no password field, and still repeats the plan picked on the
 * pricing page. With E2E_REAL_ACCOUNTS=1 the site runs against the REAL account API (backend/tests/e2e_api.py, a throwaway
 * Postgres, mail into the development catcher directory E2E_MAIL_DIR, no provider, no network) behind
 * e2e/support/https-proxy.mjs (E2E_BASE_URL=https://localhost:3443; the `__Host-` cookies need https):
 * register (with a plan) -> confirm (link from the catcher) -> sign in -> reset -> change -> delete, and a cross-site form post.
 */

test.describe('accounts closed (no API)', () => {
  test.skip(!!process.env.E2E_REAL_ACCOUNTS || !!process.env.E2E_FAKE_ACCOUNTS, 'runs against a site without an account API');

  test('/signup from the pricing page says sign-in opens soon, repeats the plan and shows no password field', async ({ page }) => {
    await visit(page, '/signup?plan=pro&billing=monthly', {
      title: /Create an account/i, h1: 'Create an account', text: ['Sign-in is not open yet', 'Sign-in opens soon', 'You chose Pro, monthly. Payment opens soon.'],
    });
    await expect(page.locator('input[type="password"]')).toHaveCount(0);
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/);
  });

  test('an unknown plan in the address is ignored, and /register goes to /signup with the plan', async ({ page }) => {
    await visit(page, '/signup?plan=platinum&billing=monthly', { title: /Create an account/i, h1: 'Create an account', text: ['Sign-in opens soon'] });
    await expect(page.locator('[data-plan-choice]')).toHaveCount(0);
    await page.goto('/register?plan=team&billing=yearly');
    await expect(page).toHaveURL(/\/signup\?plan=team&billing=yearly$/);
    await expect(page.locator('main')).toContainText('You chose Team, yearly. Payment opens soon.');
  });
});

/* ---- the real flow ---- */

const MAIL_DIR = process.env.E2E_MAIL_DIR ?? '';
const PASSWORDS = ['lantern orbit cobalt river', 'meadow quartz signal harbour', 'violet anchor tundra pilot'];

/** The text/plain part of an .eml file, decoded (quoted-printable or base64 or as is). */
function plainText(raw: string): string {
  const part = raw.split(/\r?\n--[^\r\n]+\r?\n/).find((p) => /content-type:\s*text\/plain/i.test(p)) ?? raw;
  const [head, ...rest] = part.split(/\r?\n\r?\n/);
  const body = rest.join('\n\n').replace(/\r?\n--[^\r\n]+--\s*$/, '');
  if (/content-transfer-encoding:\s*base64/i.test(head)) return Buffer.from(body.replace(/\s+/g, ''), 'base64').toString('utf8');
  if (/content-transfer-encoding:\s*quoted-printable/i.test(head)) {
    return Buffer.from(body.replace(/=\r?\n/g, '').replace(/=([0-9A-F]{2})/gi, (_, h) => String.fromCharCode(parseInt(h, 16))), 'latin1').toString('utf8');
  }
  return body;
}

interface Mail { raw: string; subject: string; text: string }

/** The newest mail to `to` with this subject, waiting for it to land in the catcher. */
async function mailTo(page: Page, to: string, subject: string): Promise<Mail> {
  for (let i = 0; i < 50; i += 1) {
    const found = readdirSync(MAIL_DIR).filter((f) => f.endsWith('.eml')).sort().reverse()
      .map((f) => readFileSync(join(MAIL_DIR, f), 'utf8'))
      .find((raw) => new RegExp(`^To: ${to.replace(/[.+]/g, '\\$&')}$`, 'mi').test(raw) && new RegExp(`^Subject: ${subject}$`, 'mi').test(raw));
    if (found) return { raw: found, subject, text: plainText(found) };
    await page.waitForTimeout(200);
  }
  throw new Error(`no mail "${subject}" to ${to}`);
}

const linkIn = (mail: Mail, path: string) => {
  const m = mail.text.match(new RegExp(`https://[^\\s/]+${path}\\?token=[A-Za-z0-9_-]{43}`));
  if (!m) throw new Error(`no ${path} link in "${mail.subject}"`);
  return new URL(m[0]).pathname + new URL(m[0]).search;           // the same path on the proxy the test drives
};

async function signIn(page: Page, email: string, password: string) {
  await page.goto('/signin');
  await page.getByRole('textbox', { name: 'E-mail address' }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

const session = async (context: BrowserContext) => (await context.cookies()).find((c) => c.name === '__Host-dg_session');

test.describe('against the real account API', () => {
  test.skip(!process.env.E2E_REAL_ACCOUNTS || !MAIL_DIR, 'needs E2E_REAL_ACCOUNTS=1, E2E_MAIL_DIR and the stack of backend/tests/e2e_api.py');
  test.use({ ignoreHTTPSErrors: true });

  test('register with a plan -> confirm -> sign in -> reset -> change -> delete', async ({ page, context }, info) => {
    test.setTimeout(180_000);
    const email = `e2e-${info.project.name}-${Date.now()}@example.test`;
    const [first, second, third] = PASSWORDS;

    // register, from the pricing page's button
    await page.goto('/signup?plan=pro&billing=monthly');
    await expect(page.locator('[data-plan-choice]')).toHaveText('You chose Pro, monthly. Payment opens soon.');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill(email);
    await page.getByLabel('Password', { exact: true }).fill(first);
    await page.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Create account' }).click();
    await expect(page.getByRole('heading', { name: 'Check your mail' })).toBeVisible();
    await expect(page.getByRole('status')).toContainText('You chose Pro, monthly. Payment opens soon.');

    // not confirmed yet: the right password is not enough
    await signIn(page, email, first);
    await expect(page.getByText('Confirm your e-mail address first')).toBeVisible();

    // confirm, from the mail in the catcher: text and HTML, from DefenceGate, no image
    const confirm = await mailTo(page, email, 'Confirm your DefenceGate account');
    expect(confirm.raw).toMatch(/^From: DefenceGate <[^>]+>$/m);
    expect(confirm.raw).toMatch(/Content-Type: text\/html/i);
    expect(confirm.raw).not.toMatch(/<img/i);
    const verifyPath = linkIn(confirm, '/auth/verify');
    await page.goto(verifyPath);
    await page.getByRole('button', { name: 'Confirm my address' }).click();
    await expect(page.getByRole('heading', { name: 'Your address is confirmed' })).toBeVisible();
    await expect(page.locator('[data-plan-choice]')).toHaveText('You chose Pro, monthly. Payment opens soon.');
    await page.goto(verifyPath);                                                     // a link works once
    await page.getByRole('button', { name: 'Confirm my address' }).click();
    await expect(page.getByRole('heading', { name: 'This link is no longer valid' })).toBeVisible();

    // sign in: the session cookie with its flags
    await signIn(page, email, 'not the password at all');
    await expect(page.getByText('The e-mail address or the password is wrong.')).toBeVisible();
    await signIn(page, email, first);
    await page.waitForURL(/\/app(\/welcome)?$/);
    const cookie = await session(context);
    expect([cookie?.httpOnly, cookie?.secure, cookie?.sameSite, cookie?.path]).toEqual([true, true, 'Lax', '/']);
    await page.goto('/app/settings');
    await expect(page.locator('section[aria-labelledby="plan"] [data-plan-choice]')).toContainText('Your plan is Free. You chose Pro, monthly. Payment opens soon.');

    // reset: the link signs every browser out and sets the new password
    await page.goto('/reset');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill(email);
    await page.getByRole('button', { name: 'Send the link' }).click();
    await expect(page.getByRole('heading', { name: 'Check your mail' })).toBeVisible();
    const resetPath = linkIn(await mailTo(page, email, 'Set a new DefenceGate password'), '/auth/reset');
    await page.goto(resetPath);
    await page.getByLabel('New password').fill(second);
    await page.getByRole('button', { name: 'Set the new password' }).click();
    await expect(page.getByRole('heading', { name: 'Your new password is set' })).toBeVisible();
    await mailTo(page, email, 'Your DefenceGate password was changed');
    await page.goto('/app/settings');
    await page.waitForURL(/\/signin/);                                               // the old session is gone
    await signIn(page, email, first);
    await expect(page.getByText('The e-mail address or the password is wrong.')).toBeVisible();
    await signIn(page, email, second);
    await page.waitForURL(/\/app(\/welcome)?$/);

    // change in settings: the current password is required
    await page.goto('/app/settings');
    await page.getByLabel('Current password').fill(first);
    await page.getByLabel('New password').fill(third);
    await page.getByRole('button', { name: 'Change password' }).click();
    await expect(page.getByText('The current password is wrong. Nothing was changed.')).toBeVisible();
    await page.getByLabel('Current password').fill(second);
    await page.getByLabel('New password').fill(third);
    await page.getByRole('button', { name: 'Change password' }).click();
    await expect(page.getByText('Your password is changed. Every other browser was signed out.')).toBeVisible();

    // delete: what goes is listed; the address and the password are both needed
    await expect(page.locator('[data-deletes] li')).toHaveCount(4);
    await page.getByLabel('Type your e-mail address to confirm').fill(email);
    await page.getByLabel('Account password').fill(second);
    await page.getByRole('button', { name: 'Delete my account' }).click();
    await expect(page.getByText('The current password is wrong. Nothing was changed.')).toBeVisible();
    await page.getByLabel('Type your e-mail address to confirm').fill(email);
    await page.getByLabel('Account password').fill(third);
    await page.getByRole('button', { name: 'Delete my account' }).click();
    await page.waitForURL((u) => u.pathname === '/');
    expect(await session(context)).toBeUndefined();
    await signIn(page, email, third);
    await expect(page.getByText('The e-mail address or the password is wrong.')).toBeVisible();
  });

  test('a sign-in posted from another site is refused (CSRF): no session cookie', async ({ page, context }, info) => {
    const email = `e2e-csrf-${info.project.name}-${Date.now()}@example.test`;
    // an account to aim at: registered and confirmed through the catcher
    await page.goto('/signup');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill(email);
    await page.getByLabel('Password', { exact: true }).fill(PASSWORDS[0]);
    await page.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Create account' }).click();
    await expect(page.getByRole('heading', { name: 'Check your mail' })).toBeVisible();
    await page.goto(linkIn(await mailTo(page, email, 'Confirm your DefenceGate account'), '/auth/verify'));
    await page.getByRole('button', { name: 'Confirm my address' }).click();
    await expect(page.getByRole('heading', { name: 'Your address is confirmed' })).toBeVisible();

    // the same form post, but as a browser sends it from a foreign page: another Origin
    await page.route('**/signin', async (route) => {
      const req = route.request();
      if (req.method() !== 'POST') return route.continue();
      await route.continue({ headers: { ...req.headers(), origin: 'https://evil.example' } });
    });
    await page.goto('/signin');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill(email);
    await page.getByLabel('Password', { exact: true }).fill(PASSWORDS[0]);
    const posted = page.waitForResponse((r) => r.request().method() === 'POST' && new URL(r.url()).pathname === '/signin');
    await page.getByRole('button', { name: 'Sign in' }).click();
    expect((await posted).status()).toBeGreaterThanOrEqual(400);
    expect(await session(context)).toBeUndefined();
    await page.unroute('**/signin');
    // and the same post from this site works
    await signIn(page, email, PASSWORDS[0]);
    await page.waitForURL(/\/app(\/welcome)?$/);
    expect(await session(context)).toBeTruthy();
  });
});
