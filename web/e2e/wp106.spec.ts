import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-106 (persona round of 24 October 2026: tender pages, lists and exports; p01 to p10). What this proves on the demo build: a tender
 * page says who may bid by its legal basis and links who wins under its code; the list offers the orders by value and by code and All's
 * own default; on a phone nothing is wider than the screen and the CSV comes before the results; the calendar has a CPV field and every
 * country; the change list offers earlier weeks; a funding call and the roadmap print without forms, buttons or menus, on few pages.
 */

const TENDER = '/tenders/1-framework-agreement-machined-aluminium-housings';
const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 768;
const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));

async function pdfPages(page: Page): Promise<number> {
  await page.emulateMedia({ media: 'print' });
  const pdf = await page.pdf({ format: 'A4', printBackground: false });
  if (process.env.WP106_SHOTS) {
    const name = new URL(page.url()).pathname.split('/').filter(Boolean).join('-');
    const { writeFileSync } = await import('node:fs');
    writeFileSync(path.join(process.env.WP106_SHOTS, `print-${name}.pdf`), pdf);
    await page.screenshot({ path: path.join(process.env.WP106_SHOTS, `print-${name}.png`), fullPage: true });
  }
  await page.emulateMedia({ media: 'screen' });
  return (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) ?? []).length;
}

test('a tender page says who may bid by its legal basis and links who wins under its code', async ({ page }) => {
  await visit(page, TENDER, { title: /DefenceGate/, h1: /.+/ });
  const box = page.locator('[data-who-may-bid]');
  await expect(box).toContainText('Directive 2009/81/EC');
  await expect(box).toContainText('recital 18');
  await expect(box).toContainText('Article 21');
  await expect(box).toContainText('not advice');
  await expect(box.locator('[data-who-wins]')).toHaveAttribute('href', /^\/suppliers\?cpv=\d{2,5}/);
});

test('the tenders list orders by value and by code, and All has its own default', async ({ page }) => {
  await visit(page, '/tenders?status=all', { title: /tenders/i, h1: 'Tenders' });
  const options = await page.locator('select').filter({ has: page.locator('option', { hasText: 'Deadline, soonest first' }) }).first().locator('option').allTextContents();
  expect(options[0]).toBe('Open first, then the most recent deadline');
  expect(options).toContain('Value, largest first (EUR, then each other currency)');
  expect(options).toContain('Main product code, ascending');
  expect(options).not.toContain('Military goods and works first, then soonest deadline');
  await visit(page, '/tenders?status=all&sort=value-desc&currency=EUR&size=50', { title: /tenders/i, h1: 'Tenders' });
  // the value order is the API's: the demo build applies the export's own order (lib/export-cache.ts listOrder)
  const values = await page.locator('article').evaluateAll((cards) => cards.map((c) => {
    const m = /EUR\s?([\d,.]+)/.exec(c.textContent ?? '');
    return m ? Number(m[1].replace(/,/g, '')) : null;
  }).filter((v): v is number => v !== null));
  expect([...values].sort((a, b) => b - a)).toEqual(values);
});

test('on a phone the tenders list is no wider than the screen, and its CSV comes before the results', async ({ page }) => {
  test.skip(!isMobile(page), 'phone only');
  for (const url of ['/tenders', '/tenders?status=all', TENDER]) {
    await visit(page, url, { title: /DefenceGate|tenders/i, h1: /.+/ });
    const wide = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(wide, url).toBeLessThanOrEqual(page.viewportSize()!.width);
  }
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  const csv = page.getByRole('link', { name: 'Download CSV' }).locator('visible=true').first();
  const first = page.locator('#results article').first();
  expect((await csv.boundingBox())!.y).toBeLessThan((await first.boundingBox())!.y);
});

test('on a phone the supplier results page, its sections open, is no wider than the screen', async ({ page }) => {
  test.skip(!isMobile(page), 'phone only');
  const demand = JSON.parse(readFileSync(path.join(__dirname, '..', 'lib', 'mock', 'demand.json'), 'utf8'));
  const profile = {
    version: 4, step: 1, updatedAt: '2026-10-23T15:05:57.221Z', name: '', sizeClass: 'medium', country: 'DE', legalForm: '', applicantKind: '', offering: '',
    topics: '', orgKind: 'company', headcount: '50_249', inGroup: 'no', groupHeadcount: '', management: '', managementCountry: '', control: 'no',
    controlCountry: '', investor: '', uaOccupied: '', uaPartner: '', seapPartner: '', regime: '', componentPct: '', componentBand: '', restricted: '',
    uaEeaComponents: '', safeRole: '', classified: 'no', exportIntent: 'within_eu',
    statuses: { 'REQ-ISO9001': 'held', 'REQ-EN9100': 'held', 'REQ-AQAP2110': 'not_held', 'REQ-AQAP2310': 'not_held', 'REQ-NCAGE': 'not_held' },
    supplier: { region: 'Bayern', foreignOwner: 'no', foreignCountry: '', nace: '25.62', cpv: ['35421000', '35641000', '34320000', '34913000', '35420000', '34731000', '42141000', '35340000'],
      processes: ['machining'], held: [], expiry: {}, usComponents: 'no', answers: {}, euFunding: 'no' },
  };
  await page.addInitScript((value) => window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)), profile);
  await page.route('**/api/readiness/assess', async (route) => {
    const body = route.request().postDataJSON() as { programmes?: string[] };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture(`assess-de-mach97${body.programmes ? '-routes' : ''}.json`)) });
  });
  await page.route('**/api/readiness/demand', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(demand) }));
  await visit(page, '/readiness/results?from=supplier', { title: /Your supplier report/, h1: 'Your supplier report' });
  await page.evaluate(() => document.querySelectorAll('details').forEach((d) => { d.open = true; }));
  await page.waitForTimeout(300);
  const wide = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const over = [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > vw + 1);
    // the outermost elements that overflow, whose parent does not (the cause, not its contents)
    const culprits = over.filter((e) => !e.parentElement || e.parentElement.getBoundingClientRect().right <= vw + 1)
      .slice(0, 5).map((e) => `${e.tagName.toLowerCase()}.${(e.getAttribute('class') ?? '').slice(0, 90)} "${(e.textContent ?? '').slice(0, 40)}"`);
    const widest = over.sort((a, b) => b.getBoundingClientRect().right - a.getBoundingClientRect().right).slice(0, 6)
      .map((e) => `${e.tagName.toLowerCase()}[${Math.round(e.getBoundingClientRect().right)}].${(e.getAttribute('class') ?? '').slice(0, 50)} <${e.parentElement?.tagName.toLowerCase()}.${(e.parentElement?.getAttribute('class') ?? '').slice(0, 50)}>`);
    const spill = [...document.querySelectorAll('body, body *')].filter((e) => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX === 'visible' && e.clientWidth > 0)
      .slice(-6).map((e) => `SPILL ${e.tagName.toLowerCase()}[${e.scrollWidth}/${e.clientWidth}].${(e.getAttribute('class') ?? '').slice(0, 70)}`);
    return { width: document.documentElement.scrollWidth, culprits: [...culprits, ...widest, ...spill] };
  });
  if (wide.width > page.viewportSize()!.width) console.log('overflow:', wide.culprits.join(' | '));
  expect(wide.width, wide.culprits.join(' | ')).toBeLessThanOrEqual(page.viewportSize()!.width);
});

test('the calendar has a CPV field and every country, also when filtered by one', async ({ page }) => {
  await visit(page, '/calendar?country=DE', { title: /calendar/i, h1: 'Deadline calendar' });
  if (isMobile(page)) await page.getByRole('button', { name: /filters/i }).first().click().catch(() => undefined);
  await expect(page.locator('form[aria-label="Filter the calendar"] input[name="cpv"]')).toHaveCount(1);
  expect(await page.locator('form[aria-label="Filter the calendar"] input[name="country"]').count()).toBeGreaterThanOrEqual(25);
  await visit(page, '/calendar?kind=tenders&cpv=35', { title: /calendar/i, h1: 'Deadline calendar' });
  await expect(page.locator('form[aria-label="Filter the calendar"] input[name="cpv"]')).toHaveValue('35');
});

test('the change list offers the archive’s weeks as its period, and only the legend of what it lists', async ({ page }) => {
  await visit(page, '/changes?kind=amended', { title: /changed/i, h1: 'What changed' });
  const period = page.locator('select[name="week"]');
  await expect(period).toHaveCount(1);
  await expect(period.locator('option').first()).toHaveText('The last 14 days');
  expect(await period.locator('option').count()).toBeGreaterThanOrEqual(2);
  await expect(page.getByText('First collected by DefenceGate on this day.', { exact: true }).locator('visible=true')).toHaveCount(0);
});

test('a funding call prints without forms, buttons or menus, on at most two pages', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'one print run');
  await visit(page, '/funding?status=all', { title: /funding/i, h1: /funding/i });
  const href = await page.locator('a[href^="/funding/"]:not([href*="export"])').first().getAttribute('href');
  await page.goto(href!);
  await page.emulateMedia({ media: 'print' });
  const shown = await page.evaluate(() => [...document.querySelectorAll('main form, main button, nav')].filter((e) => (e as HTMLElement).offsetParent !== null).length);
  expect(shown, 'no form, button or menu is printed').toBe(0);
  expect(await pdfPages(page)).toBeLessThanOrEqual(2);
});

test('the roadmap prints without forms, buttons or menus, on at most four pages (it was seven)', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'one print run');
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('assess-es.json')) }));
  await page.addInitScript((value) => window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)), {
    version: 2, step: 6, updatedAt: '2026-10-19T10:00:00.000Z', name: '', sizeClass: 'small', country: 'ES', legalForm: 'legal_person', applicantKind: 'company_or_research',
    management: 'same', managementCountry: '', control: 'no', uaOccupied: '', uaPartner: '', seapPartner: '', regime: 'military', componentPct: '10', restricted: 'no',
    uaEeaComponents: 'no', safeRole: 'contractor', statuses: {}, classified: 'yes', exportIntent: 'outside_eu',
  });
  await visit(page, '/readiness/roadmap', { title: /roadmap/i, h1: 'Your roadmap' });
  await page.emulateMedia({ media: 'print' });
  const shown = await page.evaluate(() => [...document.querySelectorAll('main form, main button, nav')].filter((e) => (e as HTMLElement).offsetParent !== null).length);
  expect(shown).toBe(0);
  const pages = await pdfPages(page);
  info.annotations.push({ type: 'roadmap print pages', description: String(pages) });
  // the demo profile has eight steps, each with its issuers, notes and sources: 7 A4 pages before WP-106, 4 now (nothing left out)
  expect(pages).toBeLessThanOrEqual(4);
});
