import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-73: fixes from the frontend QA of 21 October 2026 (docs/verification/product/qa-full-frontend.md, wp73-selfcheck.md).
 * MJ-1 the CPV search holds the whole official vocabulary, loaded on the supplier page only; MJ-2 no CPV code is required; MJ-3 what the
 * page does not ask is sent as unknown, and the HSEM is asked; MJ-4 the route's verdict follows its rules; MJ-5 the results link to the
 * supplier page; and the minors m-7, m-8, m-9, m-10, m-14, m-16.
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
interface Posted { profile: Record<string, unknown>; statuses: Record<string, string> }

async function mockAssess(page: Page, answer: string): Promise<Posted[]> {
  const posted: Posted[] = [];
  await page.route('**/api/readiness/assess', async (route) => {
    posted.push(route.request().postDataJSON() as Posted);
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture(answer)) });
  });
  return posted;
}
const store = (page: Page, profile: unknown) => page.addInitScript((p) => window.localStorage.setItem('dg.profile.v1', JSON.stringify(p)), profile);

test('the CPV search finds castings, steel, aluminium, forging, machining and the prefix 4452 from the full vocabulary', async ({ page }) => {
  await visit(page, '/readiness/supplier', { title: /supplier profile/i, h1: 'Supplier profile' });
  const search = page.getByLabel('Search the CPV codes');
  await expect(page.getByRole('group', { name: /CPV codes of what you make \(optional, up to 15\)/ })).toContainText('5 to 15 recommended for the demand map');
  for (const word of ['castings', 'steel', 'aluminium', 'forging', 'machining']) {
    await search.fill(word);
    await expect(page.getByRole('status').filter({ hasText: /codes? match/ }), word).toBeVisible();
  }
  await search.fill('4452');
  await expect(page.getByRole('checkbox', { name: /^44521000 / })).toBeVisible();
  await search.fill('gun');
  await expect(page.getByRole('checkbox', { name: /Gunmetal/ })).toHaveCount(0);
});

test('the full vocabulary is not loaded by the other pages', async ({ page }) => {
  const scripts: string[] = [];
  page.on('request', (r) => { if (r.resourceType() === 'script') scripts.push(r.url()); });
  await visit(page, '/tenders', { title: /tenders/i, h1: /tenders/i });
  const supplierOnly = new Set<string>();
  const before = new Set(scripts);
  await visit(page, '/readiness/supplier', { title: /supplier profile/i, h1: 'Supplier profile' });
  await page.getByLabel('Search the CPV codes').fill('steel');
  await expect(page.getByRole('checkbox', { name: /steel/i }).first()).toBeVisible();
  for (const s of scripts) if (!before.has(s)) supplierOnly.add(s);
  // a chunk the supplier page loads and /tenders did not: the vocabulary; and no request on /tenders is that chunk
  const sizes = await Promise.all([...supplierOnly].map(async (u) => (await page.request.get(u)).body().then((b) => ({ u, n: b.length }))));
  const vocab = sizes.filter((s) => s.n > 300_000);
  expect(vocab.length).toBe(1);
  expect([...before]).not.toContain(vocab[0].u);
});

test('a Spanish company that needs classified work: saved with no CPV code, nothing unasked is "not held", the HSEM is asked', async ({ page }) => {
  const posted = await mockAssess(page, 'assess-es-sup-defence.json');
  await visit(page, '/readiness/supplier', { title: /supplier profile/i, h1: 'Supplier profile' });
  await page.getByLabel('Country where your company is established').selectOption('ES');
  await page.getByRole('group', { name: /access to classified information/ }).getByLabel('Yes', { exact: true }).check();
  const hsem = page.getByRole('group', { name: /company security clearance \(HSEM/ });
  await expect(hsem).toBeVisible();
  await hsem.getByLabel('I am not sure').check();
  await page.getByRole('button', { name: 'Save and see my results' }).click();
  await expect(page).toHaveURL(/\/readiness\/results\?from=supplier$/);   // WP-97: the supplier path says so
  await expect.poll(() => posted.length).toBeGreaterThan(0);
  const sent = posted[posted.length - 1].statuses;
  for (const code of ['REQ-PIC', 'REQ-EXPORT', 'REQ-REOCE', 'REQ-FSC-ES']) expect(sent[code], code).toBe('unknown');
  for (const code of ['REQ-NCAGE', 'REQ-ISO9001', 'REQ-RID', 'REQ-PECAL']) expect(sent[code], code).toBe('not_held');
  // MJ-4 with the generated answer of the sample firm: the route is "Conditional" (the HSEM needs an answer), never "Eligible"
  const card = page.getByRole('article', { name: 'Spanish defence supplier (MoD)' });
  await expect(card).toHaveAttribute('data-verdict', 'conditional');
  // WP-97: "I am not sure" is an answer: the HSEM rule stays open and is said so, not counted among the missing answers
  await expect(card.locator('[data-not-sure-field="REQ-FSC-ES"]')).toContainText('HSEM facility security clearance');
  await expect(card.locator('[data-missing] a', { hasText: /HSEM facility security clearance/ })).toHaveCount(0);
  await expect(card).not.toContainText('Financial Regulation');
  await expect(card).toContainText('each rule above names its own source');
  await expect(card).not.toContainText('not asked by the questionnaire yet');
});

test('a wizard-only Spanish company is sent to the supplier page from its results', async ({ page }) => {
  await mockAssess(page, 'assess-es.json');
  await store(page, { ...fixture('profile-es-sup-partial.json'), supplier: undefined, step: 6 });
  await visit(page, '/readiness/results', { title: /results/i, h1: /results/i });
  await expect(page.getByRole('link', { name: 'Answer the supplier questions' })).toHaveAttribute('href', '/readiness/supplier');
  const card = page.getByRole('article', { name: 'Spanish defence supplier (MoD)' });
  // the wizard's answer "We do not hold it" for the HSEM, with classified work: blocked by the HSEM rule, not "Eligible"
  await expect(card).toHaveAttribute('data-verdict', 'blocked');
  await expect(card.locator('[data-supplier-asks]').first()).toHaveAttribute('href', /^\/readiness\/supplier#/);
  await expect(card).not.toContainText('does not ask yet');
});

test('/changes past its last page, and unknown filter values, say so', async ({ page }) => {
  // WP-121 (moved): past the last page the address goes to the last page, as the other lists answer (it said "There is no page 101")
  await visit(page, '/changes?page=101', { title: /changed/i, h1: 'What changed' });
  await expect(page).toHaveURL(/\/changes(\?page=\d+)?$/);
  expect(Number(new URL(page.url()).searchParams.get('page') ?? '1')).toBeLessThanOrEqual(100);
  await expect(page.getByText('The change list is not available right now')).toHaveCount(0);
  await visit(page, '/changes?kind=bogus&week=garbage&country=XX', { title: /changed/i, h1: 'What changed' });
  for (const t of ['Ignored filter: kind=bogus', 'Ignored filter: week=garbage', 'Ignored filter: country=XX']) await expect(page.getByText(t, { exact: false })).toBeVisible();
  await visit(page, '/organisations?country=XX&sort=bogus', { title: /organisations/i, h1: 'Companies', text: ['Ignored filter: country=XX', 'Ignored filter: sort=bogus'] });
  await visit(page, '/suppliers?cpv=abc', { title: /supplier/i, h1: 'Companies', text: ['Ignored filter: cpv=abc'] });
  await visit(page, '/calendar?month=2025-01', { title: /calendar/i, h1: /calendar/i, text: [/Ignored filter: month=2025-01/] });
  await visit(page, '/tenders?page=0', { title: /tenders/i, h1: /tenders/i, text: ['Ignored filter: page=0 (pages start at 1)'] });
  // m-9: a page past the end goes to the last page, as the other lists do, not to a 404
  for (const [url, h1] of [['/organisations?page=9999', 'Companies'], ['/suppliers?page=999', 'Companies']] as const) {
    await visit(page, url, { title: /./, h1 });
    expect(page.url()).not.toMatch(/page=999/);
  }
});

test('the not-found pages of the detail routes have an h1', async ({ page }) => {
  for (const [url, h1] of [['/tenders/999999999-nope', 'This tender is not in the directory'], ['/buyers/nope', 'This buyer is not in the directory'],
    ['/funding/nope', /not/], ['/organisations/nope', /not/], ['/projects/nope', /not/], ['/suppliers/nope', /not found/]] as const) {
    await visit(page, url, { title: /./, h1, status: 404 });
    await expect(page.locator('h1')).toHaveCount(1);
  }
});

// WP-122: the table became a list of plan cards; each card (not only the page) fits without scrolling sideways, and the account's
// alerts, built but not open, are still said to be not open ("Coming").
test('/pricing fits a phone without scrolling sideways', async ({ page }) => {
  await visit(page, '/pricing', { title: /pricing/i, h1: 'Pricing' });
  const cards = page.getByRole('list', { name: 'Plans' }).locator(':scope > li');
  await expect(cards).toHaveCount(5);
  for (const card of await cards.all()) {
    const { scroll, client } = await card.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
    expect(scroll).toBeLessThanOrEqual(client + 1);
  }
  await expect(cards.getByRole('listitem').filter({ hasText: 'E-mail alerts' })).toContainText('Opens with sign-in');   // WP-131: the tag of a built feature
});

test('a funding call opens its disclosures when printed', async ({ page }) => {
  await visit(page, '/funding?status=all', { title: /funding/i, h1: /funding/i });
  const href = await page.locator('a[href^="/funding/"]:not([href*="export"])').first().getAttribute('href');
  await page.goto(href!);
  const closed = () => page.locator('main details:not([open])').count();
  // the demo calls carry no long text: a closed disclosure is added to the page so that there is one to print
  if ((await closed()) === 0) {
    await page.locator('main').evaluate((m) => m.insertAdjacentHTML('beforeend', '<details data-probe><summary>More</summary><p>Hidden text</p></details>'));
  }
  const before = await closed();
  expect(before).toBeGreaterThan(0);
  await page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
  expect(await closed()).toBe(0);
  await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
  expect(await closed()).toBe(before);
  // and in print emulation the closed content is shown by CSS (::details-content)
  await page.emulateMedia({ media: 'print' });
  const shown = await page.evaluate(() => [...document.querySelectorAll('main details:not([open])')].every((d) => {
    const inner = d.querySelector(':scope > :not(summary)') as HTMLElement | null;
    return !inner || inner.getBoundingClientRect().height > 0;
  }));
  expect(shown).toBe(true);
});
