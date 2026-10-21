import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-63 (docs/verification/product/wp63-selfcheck.md): titles and descriptions that were cut mid-phrase, the copy of /pricing, /pack,
 * /alerts and the privacy notice's mail provider, and (against the fake API only) a list that fails answers 5xx, not 200.
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;

// The pages of the content re-audit (NEW-5) whose title or description ended in "…", and the four more found by the crawl of WP-63.
const PAGES = ['/glossary', '/calendar', '/requirements/aqap2310', '/requirements/edip-elig', '/requirements/export', '/data/sovereignty',
  '/readiness', '/requirements/edf-elig', '/requirements/safe-35', '/digest', '/networks/consortium-gaps', '/networks/ukraine-partners',
  '/organisations', '/alerts', '/pricing', '/pack'];

test('NEW-5: no title or description of these pages is cut, and each fits its limit', async ({ page }) => {
  test.skip(isMobile(page), 'the metadata does not depend on the width');
  for (const path of PAGES) {
    await page.goto(path);
    const title = await page.title();
    const description = (await page.locator('meta[name="description"]').getAttribute('content')) ?? '';
    expect(title, `${path} title`).not.toContain('…');
    expect(description, `${path} description`).not.toContain('…');
    expect(title.length, `${path} title: ${title}`).toBeLessThanOrEqual(60);
    expect(description.length, `${path} description: ${description}`).toBeLessThanOrEqual(160);
    expect(description.length, `${path} description says something`).toBeGreaterThanOrEqual(40);
  }
});

test('/pricing says the site is free and lists only what exists, with no placeholder', async ({ page }) => {
  await visit(page, '/pricing', { title: /pricing/i, h1: 'Pricing', text: ['DefenceGate is free to use.'] });
  const table = page.getByRole('table', { name: 'What is offered and what it costs' });
  await expect(table.getByRole('row')).toHaveCount(7);
  for (const name of ['Browsing', 'CSV export', 'Atom feeds', 'Calendar feed', 'Readiness check']) {
    await expect(table.getByRole('row', { name: new RegExp(name) })).toContainText('Free');
  }
  await expect(table.getByRole('row', { name: /Account and e-mail alerts/ })).toContainText('Not open yet');
  await expect(page.locator('main')).not.toContainText(/Not announced|Not available yet|Scope is not defined|Pro archive/);
});

test('/pack says it is not offered and how to put the same list together, with links that exist', async ({ page }) => {
  await visit(page, '/pack', { title: /opportunity pack/i, h1: 'Opportunity pack', text: ['Put it together yourself', 'What it is not'] });
  await expect(page.locator('main')).not.toContainText(/Coming soon|planned/i);
  for (const [name, href] of [['Tenders', '/tenders'], ['Funding calls', '/funding'], ['Readiness check', '/readiness']]) {
    await expect(page.locator('main').getByRole('link', { name, exact: true })).toHaveAttribute('href', href);
  }
});

test('/alerts and /privacy: no "no date", no bracketed placeholder for the mail provider', async ({ page }) => {
  await visit(page, '/alerts', { title: /alerts/i, h1: 'Alerts and saved searches', text: ['What works today, without an account', 'A calendar feed'] });
  await expect(page.locator('main')).not.toContainText(/There is no date|being prepared|calendar file/);
  await visit(page, '/privacy', { title: /privacy/i, h1: /privacy/i });
  await expect(page.locator('main')).not.toContainText('[mail provider');
  await expect(page.locator('main')).toContainText('None has been chosen yet, which is why sign-in is not open');
});

/**
 * A list the data service cannot answer is a server error, never a 200 page (re-audit N2). The framework answers 500; the edge
 * (infra/Caddyfile) turns it into 503 with Retry-After and no-store, which the lab of the self-check shows. Needs the fake API.
 */
test.describe('against the fake API', () => {
  test.skip(!process.env.E2E_FAKE_API, 'needs the fake API: E2E_FAKE_API=1 and a site started with DG_API_URL=http://127.0.0.1:4010');
  for (const path of ['/tenders?q=unavailable', '/organisations', '/networks/ukraine-partners']) {
    test(`${path}: a failed list answers 5xx and is not indexed`, async ({ request }) => {
      const r = await request.get(path);
      expect(r.status(), path).toBeGreaterThanOrEqual(500);
      expect(await r.text()).toMatch(/<meta name="robots" content="noindex/);
    });
  }
});
