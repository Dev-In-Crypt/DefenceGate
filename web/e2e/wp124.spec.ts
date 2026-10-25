import { createHmac, randomBytes } from 'node:crypto';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

/**
 * WP-124 (docs/verification/accounts/wp124-selfcheck.md): payments through Creem, merchant of record, test mode, off by default.
 *
 * Without an API (CI, the default build): /app/billing is behind sign-in, and the webhook route answers 503 (no API) and 413 over
 * 64 KiB before reading anything. With E2E_REAL_BILLING=1 the site is a build with NEXT_PUBLIC_BILLING_OPEN=1 against the REAL API
 * (backend/tests/e2e_api.py with the billing settings set to test values and DGATE_CREEM_API_URL at the local stand-in of Creem,
 * backend/tests/creem_mock.py, E2E_CREEM_MOCK_URL) behind e2e/support/https-proxy.mjs; mail in the catcher E2E_MAIL_DIR; events
 * signed with E2E_CREEM_WEBHOOK_SECRET as Creem signs them. Creem itself is never called.
 *
 * choose a plan -> signup -> confirm -> sign in -> continue to payment (the stand-in's checkout) -> webhook -> plan active
 * -> saved searches open -> cancel in the portal (the stand-in's) -> webhook -> saved searches close, the search is kept, paused.
 */

test.describe('billing closed (no API)', () => {
  test.skip(!!process.env.E2E_REAL_ACCOUNTS || !!process.env.E2E_FAKE_ACCOUNTS || !!process.env.E2E_REAL_BILLING, 'runs against a site without an account API');

  test('/app/billing is behind sign-in', async ({ page }) => {
    await page.goto('/app/billing');
    await expect(page).toHaveURL(/\/signin\?next=%2Fapp%2Fbilling$/);
  });

  test('the webhook route refuses a body over 64 KiB and, with no API, answers 503', async ({ request }) => {
    const big = await request.post('/api/billing/webhook', { data: 'x'.repeat(65 * 1024), headers: { 'content-type': 'application/json', 'creem-signature': '0'.repeat(64) } });
    expect(big.status()).toBe(413);
    const none = await request.post('/api/billing/webhook', { data: '{}', headers: { 'content-type': 'application/json' } });
    expect(none.status()).toBe(503);
  });
});

/* ---- the real flow ---- */

const MAIL_DIR = process.env.E2E_MAIL_DIR ?? '';
const SECRET = process.env.E2E_CREEM_WEBHOOK_SECRET ?? '';
const CREEM = process.env.E2E_CREEM_MOCK_URL ?? '';
const PASSWORD = 'lantern orbit cobalt river';

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

/** The path of the confirmation link in the newest mail to `to`. */
async function confirmPath(page: Page, to: string): Promise<string> {
  for (let i = 0; i < 50; i += 1) {
    const raw = readdirSync(MAIL_DIR).filter((f) => f.endsWith('.eml')).sort().reverse()
      .map((f) => readFileSync(join(MAIL_DIR, f), 'utf8'))
      .find((r) => new RegExp(`^To: ${to.replace(/[.+]/g, '\\$&')}$`, 'mi').test(r) && /^Subject: Confirm your DefenceGate account$/mi.test(r));
    const m = raw && plainText(raw).match(/https:\/\/[^\s/]+(\/auth\/verify\?token=[A-Za-z0-9_-]{43})/);
    if (m) return m[1];
    await page.waitForTimeout(200);
  }
  throw new Error(`no confirmation mail to ${to}`);
}

async function register(page: Page, email: string, from = '/signup') {
  await page.goto(from);
  await page.getByRole('textbox', { name: 'E-mail address' }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page.getByRole('heading', { name: 'Check your mail' })).toBeVisible();
  await page.goto(await confirmPath(page, email));
  await page.getByRole('button', { name: 'Confirm my address' }).click();
  await expect(page.getByRole('heading', { name: 'Your address is confirmed' })).toBeVisible();
}

async function signIn(page: Page, email: string) {
  await page.goto('/signin');
  await page.getByRole('textbox', { name: 'E-mail address' }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL(/\/app(\/welcome)?$/);
}

/** An event as Creem sends it: JSON, signed over the raw bytes (HMAC-SHA256, hex) in `creem-signature`. */
async function deliver(request: APIRequestContext, eventType: string, object: Record<string, unknown>, secret = SECRET) {
  const raw = JSON.stringify({ id: `evt_${randomBytes(8).toString('hex')}`, eventType, created_at: Date.now(), object });
  return request.post('/api/billing/webhook', {
    data: raw, headers: { 'content-type': 'application/json', 'creem-signature': createHmac('sha256', secret).update(raw).digest('hex') },
  });
}

/** "Save this search" on /tenders, retried while the statically built list page still says sign-in is closed (revalidate 60 s). */
async function trySaveSearch(page: Page, name: string): Promise<void> {
  for (let i = 0; i < 20; i += 1) {
    await page.goto('/tenders?q=vehicles');
    if (await page.getByRole('button', { name: 'Save this search' }).isVisible()) break;
    await page.waitForTimeout(5_000);
  }
  await page.getByRole('button', { name: 'Save this search' }).click();
  await page.getByLabel('Name of this search').fill(name);
  await page.getByRole('button', { name: 'Save', exact: true }).click();
}

test.describe('against the real API, billing open (test mode, Creem stand-in)', () => {
  test.skip(!process.env.E2E_REAL_BILLING || !MAIL_DIR || !SECRET || !CREEM, 'needs E2E_REAL_BILLING=1, E2E_MAIL_DIR, E2E_CREEM_WEBHOOK_SECRET, E2E_CREEM_MOCK_URL');
  test.use({ ignoreHTTPSErrors: true });

  test('choose a plan -> pay -> the plan opens saved searches -> cancel -> they close and are kept', async ({ page, context }, info) => {
    test.skip(info.project.name !== 'desktop', 'one account flow; the page at 375 px is the next test');
    test.setTimeout(240_000);
    const email = `e2e-pay-${Date.now()}@example.test`;

    // pricing -> signup with the plan, said as payment-open
    await page.goto('/pricing');
    await page.getByRole('link', { name: 'Choose Pro, monthly' }).click();
    await expect(page).toHaveURL(/\/signup\?plan=pro&billing=monthly$/);
    await expect(page.locator('[data-plan-choice]')).toHaveText('You chose Pro, monthly. You pay for it after you sign in, under Billing.');
    await register(page, email, '/signup?plan=pro&billing=monthly');
    await signIn(page, email);

    // Free until paid: the next step is said on the account pages, and saved searches are closed
    await expect(page.locator('[data-pay-now]')).toContainText('You chose Pro, monthly. Your plan is Free until it is paid.');
    await trySaveSearch(page, 'Before paying');
    await expect(page.getByText('saved searches and e-mail alerts are part of Pro')).toBeVisible();

    // continue to payment -> Creem's hosted checkout (the stand-in): nothing granted by going there or coming back
    await page.goto('/app');
    await page.locator('[data-pay-now]').getByRole('link', { name: 'Continue to payment' }).click();
    await expect(page).toHaveURL(/\/app\/billing\?plan=pro&billing=monthly$/);
    await expect(page.locator('[data-test-mode]')).toHaveText('Test mode: no real payment is taken.');
    await expect(page.locator('[data-chosen]')).toContainText('You chose Pro, monthly: €59 / month, excluding VAT.');
    await expect(page.locator('[data-founding-left]')).toHaveText('Founding customer: 20 of 20 places left.');
    await page.locator('[data-chosen]').getByRole('button', { name: 'Continue to payment' }).click();
    await page.waitForURL((u) => u.href.startsWith(`${CREEM}/checkout/ch_e2e_`));
    await expect(page.getByRole('heading', { name: 'Mock Creem checkout' })).toBeVisible();
    const made = await (await context.request.get(`${CREEM}/__last`)).json();
    expect(made.metadata.account_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(made.success_url).toMatch(/\/app\/billing\?checkout=done$/);
    await page.goto('/app/billing?checkout=done');
    await expect(page.locator('[data-confirming]')).toBeVisible();
    await expect(page.locator('[data-current-plan]')).toHaveText(/^Your plan is Free\./);

    // the webhook: a forged one is refused, Creem's one opens the plan
    const end = new Date(Date.now() + 30 * 86400e3).toISOString();
    const checkoutObject = {
      id: made.id, object: 'checkout', status: 'completed', request_id: made.request_id,
      product: { id: made.product_id }, customer: { id: 'cust_e2e', email },
      order: { id: 'ord_e2e', customer: 'cust_e2e', product: made.product_id, status: 'paid' },
      subscription: { id: 'sub_e2e', status: 'active', current_period_end_date: end }, metadata: made.metadata,
    };
    expect((await deliver(context.request, 'checkout.completed', checkoutObject, 'whsec_not_ours')).status()).toBe(401);
    expect((await deliver(context.request, 'checkout.completed', checkoutObject)).status()).toBe(200);
    await page.goto('/app/billing');
    await expect(page.locator('[data-current-plan]')).toContainText('Your plan is Pro, monthly. Status: Active. Renews on');
    await expect(page.locator('[data-pay-now]')).toHaveCount(0);

    // the gated feature opens
    await trySaveSearch(page, 'Armoured vehicles');
    await expect(page.getByRole('status').filter({ hasText: 'Saved.' })).toBeVisible();
    await page.goto('/app/searches');
    await expect(page.getByRole('heading', { name: 'Armoured vehicles' })).toBeVisible();
    await expect(page.locator('[data-paused]')).toHaveCount(0);

    // cancel in Creem's portal (the stand-in), then Creem's event
    await page.goto('/app/billing');
    await page.getByRole('button', { name: 'Manage subscription' }).click();
    await page.waitForURL(`${CREEM}/portal/cust_e2e`);
    await expect(page.getByRole('heading', { name: 'Mock Creem customer portal' })).toBeVisible();
    const canceled = { id: 'sub_e2e', object: 'subscription', status: 'canceled', product: { id: made.product_id },
      customer: { id: 'cust_e2e' }, current_period_end_date: end, canceled_at: new Date().toISOString(), metadata: made.metadata };
    expect((await deliver(context.request, 'subscription.canceled', canceled)).status()).toBe(200);

    // the feature closes; the search is kept, paused
    await page.goto('/app/billing');
    await expect(page.locator('[data-current-plan]')).toContainText('Your plan is Free. Status: Cancelled.');
    await page.goto('/app/searches');
    await expect(page.getByRole('heading', { name: 'Armoured vehicles' })).toBeVisible();
    await expect(page.locator('[data-paused]')).toContainText('Paused: your plan has no saved searches or alerts.');
    await trySaveSearch(page, 'After cancelling');
    await expect(page.getByText('saved searches and e-mail alerts are part of Pro')).toBeVisible();
  });

  test('/app/billing at this width: the chosen plan and every other one, no horizontal scroll', async ({ page }, info) => {
    test.setTimeout(120_000);
    const email = `e2e-bill-${info.project.name}-${Date.now()}@example.test`;
    await register(page, email, '/signup?plan=founding&billing=yearly');
    await signIn(page, email);
    await page.goto('/app/billing');
    await expect(page.locator('[data-chosen]')).toContainText('You chose Founding customer, yearly: €390 / year, excluding VAT.');
    await expect(page.getByRole('list', { name: 'Other plans' }).getByRole('button')).toHaveCount(6);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});
