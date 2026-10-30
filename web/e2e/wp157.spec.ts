import { expect, test, type Page } from '@playwright/test';

/**
 * WP-157 (docs/verification/features/wp157-selfcheck.md): the Team and Clients pages of the account area, and the client switcher
 * on the searches and the shortlist. The rules themselves (owner, seats, plan, the invited address, O1 across workspaces) are tested
 * against the API: backend/tests/integration/test_wp157_workspace.py. Screenshots go to E2E_SHOTS when it is set.
 */

const shot = async (page: Page, name: string) => {
  if (process.env.E2E_SHOTS) await page.screenshot({ path: `${process.env.E2E_SHOTS}/${name}.png`, fullPage: true });
};

const noSideScroll = async (page: Page) => {
  const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  expect(scroll).toBeLessThanOrEqual(client);
};

test.describe('the team pages need sign-in (no API needed)', () => {
  test.skip(!!process.env.E2E_FAKE_ACCOUNTS, 'the public part runs against the default build');

  for (const path of ['/app/team', '/app/clients', '/app/team/join']) {
    test(`${path} is behind sign-in`, async ({ page }) => {
      await page.goto(path);
      await expect(page).toHaveURL(new RegExp(`/signin\\?next=${encodeURIComponent(path)}$`));
    });
  }
});

test.describe('team workspace and client profiles, against the fake account API', () => {
  test.skip(!process.env.E2E_FAKE_ACCOUNTS, 'needs E2E_FAKE_ACCOUNTS=1 and a site started with DG_API_URL pointing at e2e/support/fake-accounts.mjs');
  test.use({ ignoreHTTPSErrors: true });

  test.beforeEach(async ({ page }) => {
    await page.goto('/signin');
    await page.getByRole('textbox', { name: 'E-mail address' }).fill('team@example.test');
    await page.getByLabel('Password', { exact: true }).fill('right password here');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForURL(/\/app$/);
  });

  const open = async (page: Page, name: 'Team' | 'Clients') => {
    if ((page.viewportSize()?.width ?? 1280) < 1024) await page.getByText('Menu', { exact: true }).click();
    await page.getByRole('link', { name, exact: true }).click();
    await expect(page.locator('h1')).toHaveText(name);
  };

  test('T: a workspace is made, a colleague invited and the invitation withdrawn; a refused one says why', async ({ page }, info) => {
    await open(page, 'Team');
    const make = page.getByRole('button', { name: 'Make the workspace' });
    if (await make.isVisible()) await make.click();
    await expect(page.locator('[data-member]').first()).toContainText('Owner');
    const email = `colleague-${info.project.name}-${Date.now()}@example.test`;
    await page.getByLabel('Their e-mail address').fill(email);
    await page.getByRole('button', { name: 'Send invitation' }).click();
    await expect(page.getByText('Invitation sent.')).toBeVisible();
    const row = page.locator('[data-invite]', { hasText: email });
    await expect(row).toContainText('invited, until');
    await noSideScroll(page);
    await shot(page, `team-${info.project.name}`);
    await row.getByRole('button', { name: /Withdraw/ }).click();
    await expect(page.locator('[data-invite]', { hasText: email })).toHaveCount(0);
    await page.getByLabel('Their e-mail address').fill('full@example.test');
    await page.getByRole('button', { name: 'Send invitation' }).click();
    await expect(page.locator('p[role="alert"]')).toContainText('no place left');
    // ending needs the box ticked
    await page.getByRole('button', { name: 'End the workspace' }).click();
    await expect(page.locator('p[role="alert"]')).toContainText('Tick the box');
  });

  test('J: the join page joins only on its button; a dead link says so', async ({ page }) => {
    await page.goto(`/app/team/join?token=${'x'.repeat(43)}`);
    await expect(page.locator('[data-join-form]')).toContainText('shared');
    await page.getByRole('button', { name: 'Join the team' }).click();
    await expect(page).toHaveURL(/\/app\/team\?n=invalid_or_expired$/);
    await expect(page.locator('p[role="alert"]')).toContainText('not valid any more');
    await page.goto('/app/team/join?token=short');
    await expect(page.locator('[data-join-form]')).toHaveCount(0);
  });

  test('C: a client profile is added, picked in the switcher, and labels the searches and the shortlist', async ({ page }, info) => {
    await open(page, 'Clients');
    const name = `Client ${info.project.name} ${Date.now()}`;
    const form = page.locator('[data-client-new]');
    await form.getByLabel('Company name').fill(name);
    await form.getByLabel('Country').fill('de');
    await form.getByLabel('CPV codes').fill('35400000, 35');
    await form.getByRole('button', { name: 'Add client' }).click();
    await expect(page.getByText('Saved.')).toBeVisible();
    const card = page.locator('[data-client]', { hasText: name });
    await expect(card).toContainText('DE');
    await card.getByRole('button', { name: 'Work on this client' }).click();
    await expect(page.locator('[data-client]', { hasText: name })).toContainText('Working on');
    // a CPV code that is not one is refused before the API
    await form.getByLabel('Company name').fill('Bad codes');
    await form.getByLabel('CPV codes').fill('35-x');
    await form.getByRole('button', { name: 'Add client' }).click();
    await expect(page.locator('p[role="alert"]')).toContainText('not accepted');
    await noSideScroll(page);
    await shot(page, `clients-${info.project.name}`);

    await page.goto('/app/searches');
    await expect(page.locator('[data-client-switcher]')).toBeVisible();
    await expect(page.locator('[data-client-filter]')).toContainText(`The searches of ${name}.`);
    await expect(page.getByText("A teammate's search")).toHaveCount(0);                     // narrowed to the client
    await expect(page.locator('li', { hasText: 'Vehicles for a client' })).toContainText(name);   // its client's tag
    await expect(page.locator('[data-search-client]')).toHaveCount(1);
    await noSideScroll(page);
    await shot(page, `searches-${info.project.name}`);
    await page.goto('/app/shortlist');
    await expect(page.locator('[data-client-filter]')).toContainText(`The shortlist of ${name}.`);
    await expect(page.getByLabel('Note (seen by your team, up to 500 characters)')).toBeVisible();
    await expect(page.locator('main')).toContainText('shared with your team');
    await noSideScroll(page);
    await shot(page, `shortlist-${info.project.name}`);
  });

  test('S: a teammate\'s search is shown without its controls', async ({ page }) => {
    // the switcher back on all clients
    await page.goto('/app/clients');
    const switcher = page.locator('[data-client-switcher]');
    if (await switcher.count()) {
      await switcher.locator('select[name="clientId"]').selectOption('', { force: true }).catch(() => undefined);
      await switcher.getByRole('button', { name: 'Show' }).click();
    }
    await page.goto('/app/searches');
    const theirs = page.locator('li', { hasText: 'A colleague\'s search' });
    await expect(theirs).toContainText('A teammate');
    await expect(theirs.getByRole('button', { name: /Delete/ })).toHaveCount(0);
    const mine = page.locator('li', { hasText: 'Vehicles for a client' });
    await expect(mine.getByRole('button', { name: /Delete/ })).toHaveCount(1);
  });

  test('at 1440 px in both themes (screenshots for the self-check)', async ({ page }, info) => {
    test.skip(!process.env.E2E_SHOTS || info.project.name !== 'desktop', 'screenshots only');
    await page.setViewportSize({ width: 1440, height: 900 });
    for (const scheme of ['light', 'dark'] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      for (const path of ['/app/team', '/app/clients', '/app/searches']) {
        await page.goto(path);
        await noSideScroll(page);
        await shot(page, `1440-${scheme}-${path.split('/').pop()}`);
      }
    }
  });

  test('no horizontal scroll at 320 px on Team and Clients, in both themes', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 800 });
    for (const scheme of ['light', 'dark'] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      for (const path of ['/app/team', '/app/clients', '/app/searches', '/app/shortlist']) {
        await page.goto(path);
        await noSideScroll(page);
      }
    }
  });
});
