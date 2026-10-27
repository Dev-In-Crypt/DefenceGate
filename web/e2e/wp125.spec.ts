import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Locator, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-125 (verification round 6, 25 October 2026, docs/verification/round6/wp125-selfcheck.md). Evidence: D:/DEFENCEGATE TESTS/verify-oct25/
 * personas (problems.csv, recheck.csv). What this proves: after the five steps, the results count as missing only what the steps ask, and
 * the supplier page's questions are listed apart as optional, each linked there; step 1 asks one question of what the organisation is; the
 * readiness check asks 24 to 35 questions (counted on the page, as WP-121 counted the supplier page), as the home tile and the check's own
 * pages say; the supplier report of a cable-harness maker is not told it is an automotive supplier.
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));
const DEMO = JSON.parse(readFileSync(path.join(__dirname, '..', 'lib', 'mock', 'demand.json'), 'utf8'));
const stored = (page: Page) => page.evaluate(() => JSON.parse(window.localStorage.getItem('dg.profile.v1') ?? 'null'));

/** The questions a form shows now: each group (a fieldset) once, and each field outside a group (as e2e/wp121.spec.ts counts). */
const countQuestions = (form: Locator) => form.evaluate((f) => {
  const seen = (e: Element) => (e as HTMLElement).offsetParent !== null || getComputedStyle(e).position === 'fixed';
  const groups = [...f.querySelectorAll('fieldset')].filter((g) => seen(g) && !g.parentElement?.closest('fieldset'));
  const fields = [...f.querySelectorAll('select, input:not([type=hidden]):not([type=radio]):not([type=checkbox]), textarea')]
    .filter((e) => seen(e) && !e.closest('fieldset'));
  return groups.length + fields.length;
});

interface Path { country: string; prefer: Record<string, string>; selects?: Record<string, string> }

/**
 * Walk the five steps answering every question shown (a follow-up as it appears): the preferred answer of a group, else its first. Returns
 * the questions counted on each step once all are answered.
 */
async function walk(page: Page, p: Path): Promise<number[]> {
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check' });
  await page.getByLabel('Country where your company is established').selectOption(p.country);
  const form = page.locator('main form').first();
  const counts: number[] = [];
  for (let step = 1; step <= 5; step++) {
    await expect(page.getByText(new RegExp(`^Step ${step} of 5`))).toBeVisible();
    for (let round = 0; round < 6; round++) {
      const open = await form.evaluate((f) => [...f.querySelectorAll('fieldset')]
        .filter((g) => (g as HTMLElement).offsetParent !== null && g.querySelector('input[type=radio]') && !g.querySelector('input[type=radio]:checked'))
        .map((g) => g.id.replace(/^q-/, '')));
      for (const [label, value] of Object.entries(p.selects ?? {})) {
        const field = page.getByLabel(label, { exact: true });
        if (await field.isVisible() && (await field.inputValue()) === '') await field.selectOption(value);
      }
      if (open.length === 0) break;
      for (const name of open) {
        const group = page.locator(`#q-${name}`);
        const want = p.prefer[name];
        await (want ? group.getByLabel(want, { exact: true }) : group.locator('input[type=radio]').first()).check();
      }
    }
    counts.push(await countQuestions(form));
    await page.getByRole('button', { name: step === 5 ? 'See my results' : 'Next', exact: true }).click();
  }
  return counts;
}

/** The longest route: a Spanish maker of products, run from another country, controlled from outside, in a group, with classified work. */
const LONGEST: Path = {
  country: 'ES',
  prefer: { management: 'In another country', control: 'Yes, by another country or an entity from another country', 'in-group': 'Yes', classified: 'Yes' },
  selects: { 'Country of the executive management': 'FR' },
};
/** The shortest: a company outside the EU that makes software or services. */
const SHORTEST: Path = {
  country: 'US',
  prefer: { offering: 'We make software or services (no physical product of our own)', 'in-group': 'No', management: 'In the country where the company is established', control: 'No' },
};

/** The API answer for what was sent: the fixture's, with the answered fields out of `missing`, as the API leaves them out. */
async function answerAssess(page: Page, name: string): Promise<void> {
  await page.route('**/api/readiness/assess', async (route) => {
    const sent = (route.request().postDataJSON() as { profile: Record<string, unknown> }).profile;
    const body = fixture(name);
    for (const a of [...body.assessments, ...body.general]) a.missing = a.missing.filter((m: { field: string }) => sent[m.field] === undefined || sent[m.field] === null);
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
}

test('1, 3: the five steps ask 35 questions at most; the results then count none they did not ask, and list the supplier page\'s apart', async ({ page }) => {
  await answerAssess(page, 'assess-es.json');
  expect(await walk(page, LONGEST), 'questions per step, longest route').toEqual([8, 7, 7, 10, 3]);
  await expect(page).toHaveURL(/\/readiness\/results$/);
  const mod = page.getByRole('article', { name: 'Spanish defence supplier (MoD)' });
  await expect(mod).toBeVisible();
  // every answer counted as missing is one the five steps ask, and links to its step
  for (const href of await page.locator('[data-programme] [data-missing] a').evaluateAll((as) => as.map((a) => a.getAttribute('href')))) {
    expect(href).toMatch(/^\/readiness\?step=[1-5]$/);
  }
  await expect(page.locator('[data-missing] [data-supplier-asks]')).toHaveCount(0);
  await expect(mod.locator('[data-missing]')).toHaveCount(0);
  // the supplier page's questions: apart, optional, each a link to that page
  const extra = mod.locator('[data-supplier-questions]');
  await expect(extra.locator('> p').first()).toHaveText(/^\d+ more questions for this route are on the supplier page \(optional\):$/);
  const links = await extra.locator('li a').evaluateAll((as) => as.map((a) => a.getAttribute('href')!));
  expect(links.length).toBeGreaterThan(5);
  for (const h of links) expect(h).toMatch(/^\/readiness\/supplier#/);
  await expect(extra.getByRole('link', { name: /current RID certificate/ })).toHaveAttribute('href', '/readiness/supplier#q-REQ-RID');
  await expect(extra.getByRole('link', { name: 'Go to the supplier page' })).toHaveAttribute('href', '/readiness/supplier');
  // a specialist's question says where it is asked
  const us = page.locator('[data-consultant-flag="US-COMPONENTS"]');
  await expect(us).toContainText('(on the supplier page, optional)');
  await expect(us.getByRole('link', { name: /components, technology or software of US origin/ })).toHaveAttribute('href', '/readiness/supplier#q-us_components');
  // and the wizard itself has no question left without an answer
  await page.goto('/readiness');
  await expect(page.getByText(/questions? ha(s|ve) no answer yet/)).toHaveCount(0);
});

test('3: the five steps ask 24 questions at least, and the pages that count them say 24 to 35', async ({ page }) => {
  await answerAssess(page, 'assess-ua.json');
  expect(await walk(page, SHORTEST), 'questions per step, shortest route').toEqual([7, 5, 2, 8, 2]);
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  const tile = page.locator('[data-tile]').nth(2);
  // WP-150: the tile lost its description; its figure says the five steps and the range
  await expect(tile.locator('[data-figure]')).toContainText('steps, 24 to 35 questions');
  await visit(page, '/readiness', { title: /readiness/i, h1: /readiness/i, text: [/24 to 35 in all/] });
  await visit(page, '/check', { title: /Check my company/, h1: 'Check my company', text: [/Five steps of 24 to 35 questions/] });
});

test('3: the services route of the supplier profile asks 18 to 23 questions, within what the tile says (17 to 53, WP-131)', async ({ page }) => {
  await visit(page, '/readiness/supplier?offer=services', { title: /supplier/i, h1: /supplier/i });
  const form = page.locator('main form').first();
  await page.getByLabel('Country where your company is established').selectOption('NL');
  expect(await countQuestions(form), 'services, outside Spain').toBe(18);
  await page.getByLabel('Country where your company is established').selectOption('ES');
  expect(await countQuestions(form), 'services, in Spain').toBe(23);
  // WP-150: the home tile no longer describes the routes; /check, which it opens, says the supplier profile's range
  await visit(page, '/check', { title: /Check my company/, h1: 'Check my company', text: ['one page of 17 to 53 questions'] });
});

test('2: step 1 asks one question of what the organisation is, and its answer sets both inputs of the rules', async ({ page }) => {
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check' });
  await page.getByLabel('Country where your company is established').selectOption('PL');
  await expect(page.getByRole('group', { name: /Which of these is your organisation/ })).toHaveCount(0);
  const kind = page.getByRole('group', { name: /What kind of organisation are you/ });
  await expect(kind).toHaveCount(1);
  await expect(kind.getByRole('radio')).toHaveCount(7);
  await kind.getByLabel('A contracting authority, for example a ministry or a procurement agency').check();
  await expect.poll(async () => { const p = await stored(page); return [p.applicantKind, p.orgKind]; }).toEqual(['contracting_authority', '']);
  await kind.getByLabel('A university or another higher-education institution').check();
  await expect.poll(async () => { const p = await stored(page); return [p.applicantKind, p.orgKind]; }).toEqual(['company_or_research', 'university']);
  // the staff and group questions follow, as before
  await expect(page.getByRole('group', { name: /How many people does your organisation employ/ })).toBeVisible();
});

test('4: a cable-harness maker\'s report is not told it is an automotive supplier, and gets no car-parts article', async ({ page }) => {
  const profile = {
    version: 5, step: 1, updatedAt: '2026-10-25T10:00:00.000Z', name: '', sizeClass: 'small', country: 'ES', legalForm: '', applicantKind: '', offering: 'products',
    topics: '', orgKind: 'company', headcount: 'lt50', inGroup: 'no', groupHeadcount: '', management: '', managementCountry: '', control: 'no',
    controlCountry: '', investor: '', uaOccupied: '', uaPartner: '', seapPartner: '', regime: '', componentPct: '', componentBand: '', restricted: '',
    uaComponents: '', eeaComponents: '', safeRole: '', statuses: {}, classified: 'no', exportIntent: 'within_eu',
    supplier: { region: '', foreignOwner: 'no', foreignCountry: '', nace: '', cpv: ['31611000', '31612000', '35422000'], processes: ['harness'], held: [], expiry: {},
      usComponents: 'no', answers: {}, euFunding: 'no' },
  };
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, profile);
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('assess-es-auto97.json')) }));
  await page.route('**/api/readiness/demand', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DEMO) }));
  await visit(page, '/readiness/results?from=supplier', { title: /Your supplier report/, h1: 'Your supplier report' });
  const explainer = page.locator('[data-approach-explainer]').first();
  await expect(explainer).toHaveAttribute('data-approach-explainer', 'goods');
  await expect(page.locator('main')).not.toContainText('Automotive suppliers usually enter defence');
  await expect(page.locator('[data-approach-indra]')).toHaveCount(0);
  await expect(page.locator('a[href*="eldiario.es"]')).toHaveCount(0);
});
