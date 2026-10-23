import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { openAbout, visit } from './helpers';

/**
 * The fixes of WP-38, from the persona walk-throughs of 18 October 2026 (docs/verification/product/verify2-ux.md, U1 to U16).
 * The CI site has no API behind it: it answers 503 on /api/*, so every route a page calls is answered here, and a console
 * error fails the visit. The pages read the demo data of web/lib/mock. Runs at desktop width and at 375 px.
 * Locators are roles and labels, scoped to #main where the navigation repeats a name.
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));

const PROFILE = {
  version: 2, step: 6, updatedAt: '2026-10-18T10:00:00.000Z', name: '', sizeClass: 'small', country: 'ES', legalForm: 'legal_person',
  management: 'same', managementCountry: '', control: 'no', uaOccupied: '', regime: 'dual_use', componentPct: '10', restricted: 'no',
  uaEeaComponents: 'no', safeRole: 'contractor', statuses: {}, classified: 'no', exportIntent: 'none',
};
const saveProfile = (page: Page, p: Record<string, unknown> | null) =>
  page.addInitScript((value) => { if (value) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, p);

/** The demo call whose rules were read (web/lib/mock/calls.ts): "no consortium" beside four countries, and a footnote number in a quote. */
const CALL = '/funding/1-edf-2026-additive-manufacturing-spare-parts';

async function mockApis(page: Page) {
  await page.route('**/api/fit/facts*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: {} }) }));
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('assess-es.json')) }));
  // a profile with a country loads the partner list by itself: an answer that says there is nothing to compare
  await page.route('**/api/funding/*/partners*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ call: { id: '1', slug: '1-x', topic: null }, area: null, partners: [], countries: [], total: 0, country: null, prefer: null, note: 'No earlier projects can be compared with this call.' }),
  }));
}

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;

// ---------------------------------------------------------------- U4, U5, U13: the call page

test('U4: the form of a call page starts from the saved profile and summarises its lines', async ({ page }) => {
  await mockApis(page);
  await saveProfile(page, PROFILE);
  await visit(page, CALL, { title: /DefenceGate/, h1: /additive manufacturing/i });
  const form = page.getByRole('form', { name: 'Check your company against this call' });
  await expect(form.getByLabel('Where is your organisation established?')).toHaveValue('ES');
  await expect(form.getByLabel('What kind of organisation?')).toHaveValue('sme');
  await expect(form.getByLabel(/controlled from outside the EU/)).toHaveValue('no');
  await expect(form.getByLabel('Do you already have consortium partners?')).toHaveValue('');
  await expect(form.getByText(/Filled in from the profile saved in this browser/)).toBeVisible();
  const results = page.locator('section[aria-labelledby="can-you-apply-"] [aria-live="polite"]').first();
  await expect(results).toContainText(/All \d+ lines are allowed on your answers/);
  // the one answer the profile does not hold: with partners, the unclear consortium line is a "check"
  await form.getByLabel('Do you already have consortium partners?').selectOption('yes');
  await expect(results).toContainText(/1 of \d+ lines needs your check; none is a no/);
  // a visitor who changes an answer is not overwritten by the profile
  await form.getByLabel('What kind of organisation?').selectOption('university');
  await expect(form.getByLabel('What kind of organisation?')).toHaveValue('university');
});

test('U4: without a profile the form is empty and says so', async ({ page }) => {
  await mockApis(page);
  await saveProfile(page, null);
  await visit(page, CALL, { title: /DefenceGate/, h1: /additive manufacturing/i });
  const form = page.getByRole('form', { name: 'Check your company against this call' });
  await expect(form.getByLabel('Where is your organisation established?')).toHaveValue('');
  await expect(form.getByText('Your answers stay in this page. Nothing is sent or saved.')).toBeVisible();
});

test('U5: "no consortium" beside a minimum of four countries is shown as unclear, never as a bare "No"', async ({ page }) => {
  await mockApis(page);
  await saveProfile(page, null);
  await visit(page, CALL, { title: /DefenceGate/, h1: /additive manufacturing/i });
  const row = page.locator('section[aria-labelledby="can-you-apply-"] dl > div').filter({ has: page.getByText('Consortium required', { exact: true }) });
  await expect(row).toContainText('The document is unclear, read it: it says no consortium is required and also asks for at least 4 countries.');
  await expect(row.getByText('No', { exact: true })).toHaveCount(0);
  await expect(page.locator('section[aria-labelledby="can-you-apply-"] dl').getByText('Smallest number of countries')).toBeVisible();
});

test('U13: a footnote number glued to a word in a quoted sentence is not shown', async ({ page }) => {
  await mockApis(page);
  await saveProfile(page, null);
  await visit(page, CALL, { title: /DefenceGate/, h1: /additive manufacturing/i });
  await expect(page.getByText('Small mid-caps up to 499 staff may apply under Horizon Europe rules.')).toBeVisible();
  await expect(page.getByText(/Europe202/)).toHaveCount(0);
});

test('U14: a long call page has an index of its parts at the top, and each link goes to its part', async ({ page }) => {
  await mockApis(page);
  await saveProfile(page, null);
  await visit(page, CALL, { title: /DefenceGate/, h1: /additive manufacturing/i });
  const index = page.getByRole('navigation', { name: 'On this page' });
  await expect(index).toBeVisible();
  for (const name of ['Who can apply', 'Can you apply?', 'Terms', 'Source']) await expect(index.getByRole('link', { name })).toBeVisible();
  await index.getByRole('link', { name: 'Terms' }).click();
  await expect(page).toHaveURL(/#terms$/);
  await expect(page.locator('#terms')).toBeInViewport();
});

// ---------------------------------------------------------------- U1, U6: partners

test('U6: the partner list of a call with no category says "whole programme" before the list', async ({ page }) => {
  await mockApis(page);
  await saveProfile(page, null);
  await page.route('**/api/funding/*/partners*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      call: { id: '1', slug: '1-x', topic: 'EDF-EDIP-P-2027-FNLC-CPA-AMDS' }, partners: [{ organisationId: '1', slug: '1-big-prime', name: 'Big Prime SA', country: 'FR', projects: 70, coordinated: 20, firstYear: 2021, lastYear: 2025, evidence: [] }],
      area: { kind: 'edf', label: 'all projects of the European Defence Fund', rule: 'All EDF projects read from the factsheets of the call results, 2021 onwards.', projects: 283, organisations: 1200, firstYear: 2021, lastYear: 2025, broaderThanCall: false },
      countries: [{ country: 'FR', organisations: 300 }, { country: 'PL', organisations: 60 }], total: 1200, country: null, prefer: null, note: null,
      source: { readAt: '2026-10-17T12:00:00Z', sources: ['CORDIS, European Commission'], licence: 'Commission Decision 2011/833/EU' },
    }),
  }));
  await visit(page, CALL, { title: /DefenceGate/, h1: /additive manufacturing/i });
  await page.getByRole('button', { name: 'Show organisations from earlier projects' }).click();
  await expect(page.getByText(/names no capability category, so this list is compared with the whole programme/)).toBeVisible();
  await expect(page.getByText(/Start with your country/)).toBeVisible();
});

// ---------------------------------------------------------------- U7, U16: the wizard

test('U7: Change my answers opens at the first step with an unanswered question and names it', async ({ page }) => {
  await saveProfile(page, { ...PROFILE, regime: '', classified: '' });
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check' });
  await expect(page.getByText('Step 3 of 5: Products and regime')).toBeVisible();
  const note = page.getByText('2 questions have no answer yet');
  await note.click();
  await expect(page.getByRole('button', { name: /Step 3: Which export regime your main product is in/ })).toBeVisible();
  await page.getByRole('button', { name: /Step 5: Whether you will handle classified information/ }).click();
  await expect(page.getByText('Step 5 of 5: Classified work and exports')).toBeVisible();
});

test('U7: the link under "answers are missing" opens the step that asks the question', async ({ page }) => {
  await saveProfile(page, PROFILE);
  await visit(page, '/readiness?step=3', { title: /readiness check/i, h1: 'Readiness check' });
  await expect(page.getByText('Step 3 of 5: Products and regime')).toBeVisible();
});

/** Open the "keep my answers" block if it is closed (it keeps its state when the answers are cleared). */
async function openKeep(page: Page) {
  if (!(await page.getByLabel('Or paste the copied answers here').isVisible())) await page.getByText('Keep my answers in a file, or load answers from one').click();
}

test('U7: the answers can be saved to a file and loaded back, and a block that is not ours is refused', async ({ page }) => {
  await saveProfile(page, { ...PROFILE, name: 'Client One' });
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check' });
  await openKeep(page);
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download my answers' }).click()]);
  expect(download.suggestedFilename()).toBe('defencegate-answers-client-one.json');
  const block = readFileSync(await download.path(), 'utf8');
  expect(JSON.parse(block).country).toBe('ES');

  // clear, then load the block back
  await page.getByRole('button', { name: 'Clear my answers' }).click();
  await page.getByRole('button', { name: 'Yes, clear them' }).click();
  expect(await page.evaluate(() => window.localStorage.getItem('dg.profile.v1'))).toBeNull();
  await openKeep(page);
  await page.getByLabel('Or paste the copied answers here').fill('{"hello": 1}');
  await page.getByRole('button', { name: 'Load the pasted answers' }).click();
  await expect(page.getByRole('alert').filter({ hasText: /not a set of answers/ })).toBeVisible();
  await page.getByLabel('Or paste the copied answers here').fill(block);
  await page.getByRole('button', { name: 'Load the pasted answers' }).click();
  await expect(page.getByText(/Answers loaded from the file/)).toBeVisible();
  const stored = await page.evaluate(() => window.localStorage.getItem('dg.profile.v1'));
  expect(stored).toContain('"country":"ES"');
  expect(stored).toContain('Client One');
});

test('U16: after Next the focus is on the heading of the step, and a refused Next puts it on the field to fix', async ({ page }) => {
  await saveProfile(page, null);
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check' });
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByText('Choose a country to go on.')).toBeVisible();
  await expect(page.getByLabel('Country where your company is established')).toBeFocused();
  await page.getByLabel('Country where your company is established').selectOption('ES');
  await page.getByRole('group', { name: /legal form of your organisation/ }).getByLabel(/^A legal person/).check();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Ownership and control', level: 2 })).toBeFocused();
});

// ---------------------------------------------------------------- U8, U13: the roadmap and the results

test('U8: the roadmap says "no time needed", shows no converted figure and does not say a programme asks for AQAP', async ({ page }) => {
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('assess-ua.json')) }));
  await saveProfile(page, { ...PROFILE, country: 'UA', uaOccupied: 'no' });
  await visit(page, '/readiness/roadmap', { title: /roadmap/i, h1: 'Your roadmap' });
  const main = page.locator('#main');
  await expect(main.getByRole('heading', { name: /PIC \(Participant Identification Code\)/ })).toHaveCount(1);
  await expect(main.getByText(/0 to 0 days/)).toHaveCount(0);
  await expect(main.getByText(/as converted in the research notes/)).toHaveCount(0);
  await expect(main.getByText(/EUR 15,700/)).toHaveCount(0);
  const aqap = main.locator('li[data-step="REQ-AQAP2110"]');
  await expect(aqap).toContainText('Named by contracts under');
  await expect(aqap).toContainText('not a condition for applying to a programme');
  await expect(aqap.getByText(/^Asked by:/)).toHaveCount(0);
  // the issuer's country code does not run into its name
  await expect(main.getByText(/UANational/)).toHaveCount(0);
  await expect(main.locator('li[data-step="REQ-NCAGE"]')).toContainText('UA National Codification Bureau');
  // the "What is this?" links have names that tell them apart
  await expect(main.getByRole('link', { name: /^What is PIC \(Participant Identification Code\)\?$/ })).toBeVisible();
});

test('U13: the programme keys are shown as names on the requirements pages', async ({ page }) => {
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 503, body: '{}' }));
  await visit(page, '/requirements', { title: /requirements/i, h1: 'Requirements' });
  const main = page.locator('#main');
  await expect(main.getByText(/Appears in the rules of/).first()).toBeVisible();
  await expect(main.getByText(/\b(GENERAL|NATO-SUPPLY|EDIP-USI)\b/)).toHaveCount(0);
});

// ---------------------------------------------------------------- U9: suppliers

test('U9: the supplier map searches by product through the CPV finder and links to it', async ({ page }) => {
  await visit(page, '/suppliers?product=ammunition', { title: /supplier map/i, h1: 'Companies' });
  const main = page.locator('#main');
  await expect(main.getByLabel(/^Product, for example ammunition/)).toHaveValue('ammunition');
  // WP-88: the method, coverage and caveats are in the collapsed About this data (owner-approved copy change, 22 Oct 2026)
  await openAbout(page);
  await expect(main.getByRole('link', { name: 'CPV finder' }).first()).toHaveAttribute('href', '/cpv');
  await expect(main.getByRole('status').filter({ hasText: /“ammunition” matches \d+ codes? of the finder/ })).toContainText('3533');
  await expect(main.getByText(/a count, not a ranking/)).toBeVisible();
  await visit(page, '/suppliers?product=zzzzqqq', { title: /supplier map/i, h1: 'Companies' });
  await expect(page.locator('#main').getByRole('status').filter({ hasText: /No code in the CPV finder has/ })).toBeVisible();
});

// ---------------------------------------------------------------- U10: programmes and countries

test('U10: the directory opens on the defence programmes and one visible link shows all', async ({ page }) => {
  await visit(page, '/organisations', { title: /organisations/i, h1: 'Companies' });
  const main = page.locator('#main');
  await expect(main.getByRole('status').filter({ hasText: /Showing the European Defence Fund and its two predecessor programmes/ })).toBeVisible();
  await expect(main.getByRole('link', { name: /Kyiv Institute/i })).toHaveCount(0);
  await main.getByRole('link', { name: 'Show all programmes' }).click();
  await expect(page).toHaveURL(/programme=all/);
  await expect(main.getByRole('link', { name: /Kyiv Institute/i })).toBeVisible();
  await expect(main.getByRole('link', { name: /Show only the European Defence Fund/ })).toBeVisible();
  // WP-88: the method, coverage and caveats are in the collapsed About this data (owner-approved copy change, 22 Oct 2026)
  await openAbout(page);
  await expect(main.getByText(/shown under Spain although its address is recorded in Italy/)).toBeVisible();
});

test('U10: the Ukraine partners analysis says what the defence programmes hold and what the others hold', async ({ page }) => {
  // WP-46: when the defence programmes have no project with a Ukrainian participant the page opens on all programmes, says so, and keeps the link back.
  await visit(page, '/networks/ukraine-partners', { title: /Ukrainian organisations/i, h1: 'Ukraine partners' });
  const main = page.locator('#main');
  const opened = main.getByRole('status').filter({ hasText: /Showing all programmes/ });
  await expect(opened).toContainText('No project of the European Defence Fund and its two predecessor programmes started in or after 2021 has a Ukrainian participant');
  await expect(opened.getByRole('link', { name: /Show only the European Defence Fund and its two predecessor programmes/ })).toBeVisible();
  await expect(main.getByRole('table', { name: /Coordinators with a Ukrainian participant/i }).getByRole('link', { name: /Alpha Systems/i })).toBeVisible();
  // a programme the visitor chose stays as chosen, and the page says what all the others hold
  await visit(page, '/networks/ukraine-partners?programme=EDF', { title: /Ukrainian organisations/i, h1: 'Ukraine partners' });
  await expect(main.getByRole('status').filter({ hasText: /Showing .*European Defence Fund/ })).toContainText('All programmes together hold 1 more project');
  await main.getByRole('link', { name: 'Show all programmes' }).click();
  await expect(page).toHaveURL(/programme=all/);
  await expect(main.getByRole('table', { name: /Coordinators with a Ukrainian participant/i }).getByRole('link', { name: /Alpha Systems/i })).toBeVisible();
  // WP-88: on a phone the table reads as cards (one row a block), so it fits and no "scroll sideways" line is needed at any width
  const hint = main.getByText(/More columns to the right: scroll sideways/);
  await expect(hint).toHaveCount(0);
  if (isMobile(page)) {
    const row = main.getByRole('table', { name: /Coordinators with a Ukrainian participant/i }).locator('tbody tr').first();
    expect(await row.evaluate((r) => getComputedStyle(r).display)).toBe('block');
  }
});

// ---------------------------------------------------------------- U11: consortium gaps

test('U11: the gap analysis uses selects for the programme and the country and explains the capability codes', async ({ page }) => {
  await visit(page, '/networks/consortium-gaps?topic=CYBER&lacking=PL', { title: /Repeat participants/i, h1: 'Consortium gaps' });
  const main = page.locator('#main');
  await expect(main.getByLabel('With no participant from')).toHaveValue('PL');
  await expect(main.getByLabel('Programme')).toHaveValue('EDF');
  await expect(main.getByRole('combobox', { name: 'With no participant from' })).toBeVisible();
  // WP-88: the method, coverage and caveats are in the collapsed About this data (owner-approved copy change, 22 Oct 2026)
  await openAbout(page);
  await expect(main.getByText(/our plain reading\s+of the abbreviation/)).toBeVisible();
  await expect(main.getByRole('link', { name: 'GROUND' })).toBeVisible();
  await expect(main.getByText('Ground combat')).toBeVisible();
});

// ---------------------------------------------------------------- U12: tracker and digest

test('U12: every tracker entry has a permalink and a line to cite, newest event first', async ({ page }) => {
  await visit(page, '/regulation', { title: /regulatory tracker/i, h1: 'Regulatory tracker' });
  const main = page.locator('#main');
  const entries = main.locator('li[id]');
  const n = await entries.count();
  expect(n).toBeGreaterThan(5);
  await expect(main.getByRole('link', { name: /^Link to this entry/ })).toHaveCount(n);
  const first = entries.first();
  const code = await first.getAttribute('id');
  await expect(first.getByRole('link', { name: /^Link to this entry/ })).toHaveAttribute('href', `#${code}`);
  // the line to cite sits in a disclosure, collapsed until it is opened; it is in the page either way
  await expect(first.getByText('Cite this entry:')).toBeHidden();
  await first.locator('summary').click();
  await expect(first.getByText('Cite this entry:')).toBeVisible();
  await expect(first).toContainText(`/regulation#${code}`);
  const dates = await entries.evaluateAll((els) => els.map((e) => e.querySelector('time')?.getAttribute('datetime') ?? ''));
  expect(dates, 'newest event first').toEqual([...dates].sort().reverse());
});

test('U12: the digest says what "new" means', async ({ page }) => {
  await visit(page, '/digest', { title: /weekly digest/i, h1: 'Weekly digest' });
  const main = page.locator('#main');
  // with no digest behind the demo build the page says so; with one it explains "new"
  const explains = main.getByText('What “new” means here');
  if (await explains.count()) {
    await explains.click();
    await expect(main.getByText(/collected for the first time in this week/).first()).toBeVisible();
  } else {
    await expect(main.getByText(/no issue to show/i)).toBeVisible();
  }
});

// ---------------------------------------------------------------- U15, U16: home and the menu

test('U15: the home page names the three parts in the first screen', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: /tenders and funding/i });
  const parts = page.getByRole('list', { name: 'The three parts of DefenceGate' });
  await expect(parts).toBeVisible();
  for (const name of [/1\. What is open to me\?/, /2\. Who is already inside\?/, /3\. What do I need to qualify\?/]) await expect(parts.getByText(name)).toBeVisible();
  await expect(parts.getByRole('link', { name: 'Check my company' })).toHaveAttribute('href', '/check');
  // WP-46: the hero tiles and the "Three questions" section were one message twice; the section is the only block saying it.
  // WP-86 (owner-approved home): the hero's tasks and search come first, then the lists closing next (the first useful thing),
  // then the three parts, before "Why DefenceGate"; "What is in here" is gone from home.
  const top = await parts.evaluate((el) => el.getBoundingClientRect().top + window.scrollY);
  const at = (name: string | RegExp) => page.getByRole('heading', { name }).evaluate((el) => el.getBoundingClientRect().top + window.scrollY);
  expect(top, 'after the closing funding calls').toBeGreaterThan(await at('Funding calls closing soon'));
  expect(top, 'before "Why DefenceGate"').toBeLessThan(await at('Why DefenceGate'));
  await expect(page.getByRole('heading', { name: 'What is in here' })).toHaveCount(0);
});

test('U16: a small menu opens from a button that says it is open, and closes with Escape', async ({ page }) => {
  test.skip(isMobile(page), 'the bar menus are the desktop navigation');
  await visit(page, '/', { title: /DefenceGate/, h1: /tenders and funding/i });
  const nav = page.getByRole('navigation', { name: 'Main' });
  const toggle = nav.getByRole('button', { name: 'Companies: more pages' });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(nav.getByRole('link', { name: 'Ukraine partners' })).toBeHidden();
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(nav.getByRole('link', { name: 'Ukraine partners' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
});

test('U16: the mobile menu opens with focus on its first field (the search, WP-86) and Escape returns it to the button', async ({ page }) => {
  test.skip(!isMobile(page), 'the mobile menu is below md');
  await visit(page, '/', { title: /DefenceGate/, h1: /tenders and funding/i });
  const button = page.getByRole('button', { name: 'Open menu' });
  await button.click();
  const menu = page.getByRole('navigation', { name: 'Main menu' });
  await expect(menu.getByRole('searchbox')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(menu).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Open menu' })).toBeFocused();
});

test('U16: no button or stand-alone link on these pages is smaller than 24 px', async ({ page }) => {
  await mockApis(page);
  await saveProfile(page, PROFILE);
  const small: string[] = [];
  for (const url of ['/', CALL, '/readiness', '/readiness/results', '/regulation', '/networks/consortium-gaps']) {
    await visit(page, url, { title: /.+/, h1: /.+/ });
    await page.waitForTimeout(300);
    const found = await page.evaluate(() => {
      const out: string[] = [];
      for (const el of Array.from(document.querySelectorAll<HTMLElement>('a[href], button, summary, select, input:not([type=hidden]), textarea'))) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0 || getComputedStyle(el).visibility === 'hidden') continue;
        // a link inside a sentence is exempt (WCAG 2.5.8): its line is the target
        const inline = el.tagName === 'A' && getComputedStyle(el).display === 'inline';
        if (inline) continue;
        if (el.closest('.sr-only') || el.classList.contains('sr-only')) continue;
        // a checkbox or radio is clicked through its label, which is the target
        const label = el.closest('label')?.getBoundingClientRect();
        if (el.tagName === 'INPUT' && label && label.height >= 24 && label.width >= 24) continue;
        if (r.width < 24 || r.height < 24) out.push(`${el.tagName.toLowerCase()} "${(el.textContent ?? el.getAttribute('aria-label') ?? '').trim().slice(0, 40)}" ${Math.round(r.width)}x${Math.round(r.height)}`);
      }
      return out;
    });
    small.push(...found.map((f) => `${url}: ${f}`));
  }
  expect(small, 'targets under 24 px').toEqual([]);
});
