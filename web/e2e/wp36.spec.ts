import { expect, test, type Page } from '@playwright/test';
import { pace, visit } from './helpers';

/**
 * WP-36: the "rules that apply" block of a call, the Ukraine filter, the regulatory tracker and the sovereignty page.
 * Read-only. The same file runs against a local build with demo data and against a real site, so it asks for shapes,
 * and checks the content only where there is some.
 */

/** Below the `lg` breakpoint the filters sit behind a "Filters" button; open it so the controls are on screen. */
async function openFilters(page: Page) {
  const button = page.getByRole('button', { name: /^(Show|Hide) filters/ });
  if (await button.isVisible() && (await button.getAttribute('aria-expanded')) !== 'true') await button.click();
}

test('the Ukraine filter keeps its value, counts, and every result carries the badge', async ({ page }) => {
  await visit(page, '/funding?status=all&ukraine=true', { title: /funding/i, h1: /funding/i });
  await openFilters(page);
  const box = page.getByRole('checkbox', { name: /Only calls open to Ukraine/ });
  await expect(box).toBeChecked();
  await expect(box).toHaveAccessibleName(/\(\d+\)/);
  const total = (await page.locator('#results-heading').textContent()) ?? '';
  if (/^No calls/.test(total.trim())) {
    await expect(page.getByText(/No calls match/)).toBeVisible();
    return;
  }
  const cards = page.locator('article');
  const n = await cards.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i += 1) await expect(cards.nth(i).getByText('Open to Ukraine', { exact: true })).toBeVisible();
  await pace(page);
});

test('the glossary explains the Ukraine flag, and says unknown is not no', async ({ page }) => {
  await visit(page, '/glossary', { title: /glossary/i, h1: /glossary/i });
  await expect(page.locator('#open-to-ukraine')).toBeAttached();
  await expect(page.getByText(/unknown is not no/i).first()).toBeAttached();
});

test('a call page names its regime, lists conditions with their source, and says it is not legal advice once', async ({ page }) => {
  await visit(page, '/funding?status=all&programme=EDF', { title: /funding/i, h1: /funding/i });
  const href = await page.locator('a[href^="/funding/"]:not([href*="export"])').first().getAttribute('href');
  expect(href, 'an EDF call link on /funding').toMatch(/^\/funding\/\d+/);
  await visit(page, href!, { title: /DefenceGate/, h1: /.+/ });
  const block = page.locator('section[aria-labelledby="rules-that-apply"]');
  await expect(block.getByRole('heading', { name: 'Rules that apply', exact: true })).toBeVisible();
  await expect(block.getByText(/This call falls under/)).toBeVisible();
  await expect(block.getByText(/Indicative, not legal advice/)).toHaveCount(1);
  await expect(block.getByRole('link', { name: /readiness check/ })).toHaveAttribute('href', '/readiness');
  // Every listed condition has its source reference and a link to the Official Journal.
  const items = block.locator('li');
  const n = await items.count();
  for (let i = 0; i < n; i += 1) await expect(items.nth(i).getByRole('link', { name: /Official Journal/ })).toBeVisible();
  await pace(page);
});

test('/regulation: every entry has a status, a source with a quote, and the day it was checked', async ({ page }) => {
  await visit(page, '/regulation', { title: /regulatory tracker/i, h1: 'Regulatory tracker', text: [/Last checked/] });
  const entries = page.locator('ol > li').filter({ has: page.getByRole('link', { name: /Primary source/ }) });
  const n = await entries.count();
  expect(n).toBeGreaterThan(5);
  for (let i = 0; i < n; i += 1) {
    const e = entries.nth(i);
    await expect(e.getByRole('link', { name: /Primary source/ })).toHaveAttribute('href', /^https?:\/\//);
    await expect(e.locator('blockquote')).not.toBeEmpty();
    // the quote and the citation are in a disclosure (collapsed); the day we last read the source is a fact beside the summary
    await expect(e.locator('dt', { hasText: 'Last checked' }).locator('xpath=following-sibling::dd[1]')).toHaveText(/^\d{1,2} \w+ \d{4}$/);
    await expect(e.locator('dt', { hasText: 'Last checked' })).toBeVisible();
  }
  await expect(page.locator('#main').getByRole('link', { name: /Atom feed/ })).toHaveAttribute('href', '/regulation.atom');
  await pace(page);
});

test('/regulation.atom is an Atom feed with one entry per tracker entry', async ({ request }) => {
  const res = await request.get('/regulation.atom');
  expect(res.status()).toBe(200);
  expect(res.headers()['content-type']).toContain('application/atom+xml');
  const body = await res.text();
  expect(body).toContain('<feed xmlns="http://www.w3.org/2005/Atom"');
  expect((body.match(/<entry>/g) ?? []).length).toBeGreaterThan(5);
  expect(body).toMatch(/<link rel="related"[^>]+title="Primary source"/);
});

test('/data/sovereignty: says what is in the EU and what is not, and does not claim there is no US service', async ({ page }) => {
  await visit(page, '/data/sovereignty', { title: /where the data runs/i, h1: 'Where the data runs' });
  await expect(page.getByRole('heading', { name: 'In the EU', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Not in the EU, or not assessed', exact: true })).toBeVisible();
  await expect(page.getByText('OpenAI').first()).toBeVisible();
  await expect(page.getByText(/does not say that no US company is in the path/)).toBeVisible();
  await expect(page.getByText(/no US SaaS/i)).toHaveCount(0);
});
