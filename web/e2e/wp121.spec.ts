import { expect, test, type Locator, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-121 (verification round 6, 25 October 2026, docs/verification/round6/wp121-selfcheck.md): 17 homepage and site fixes. Evidence:
 * D:/DEFENCEGATE TESTS/verify-oct25/site/problems.csv and personas/problems.csv. The demo build pins "now" (NEXT_PUBLIC_DG_NOW).
 */

const HOME = { title: /DefenceGate/, h1: 'Win, partner, qualify.' };
const NOW = Date.parse(process.env.NEXT_PUBLIC_DG_NOW ?? new Date().toISOString());
const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const DAY = 86_400_000;
/** The instant a listed deadline closes: a date-only one (00:00 UTC) at the end of its day. */
const closesAt = (iso: string) => { const t = Date.parse(iso); return t % DAY === 0 ? t + DAY - 1000 : t; };

// ---------------------------------------------------------------- 1. closing soon: the soonest still open, and no hydration difference

test('1: both closing lists show the soonest deadlines that have not passed, soonest first; no hydration error in four loads', async ({ page }) => {
  for (let i = 0; i < 4; i++) {
    // `visit` fails on any page error, React's #418 (server and browser HTML differ) included
    await visit(page, '/', HOME);
    for (const id of ['closing-tenders', 'closing']) {
      const times = (await page.locator(`section[aria-labelledby="${id}"] li time`).evaluateAll((ts) => ts.map((t) => t.getAttribute('datetime')!))).map(closesAt);
      expect(times.length, id).toBeGreaterThan(0);
      for (const t of times) expect(t, `${id}: a deadline already passed`).toBeGreaterThan(NOW);
      expect(times, `${id}: soonest first`).toEqual([...times].sort((a, b) => a - b));
    }
    await visit(page, '/funding?status=closing-soon', { title: /funding/i, h1: /funding/i });
  }
  // the tenders list's soonest open deadline is the first row (not the military-goods-first order of the open list)
  await visit(page, `/tenders?from=${new Date(NOW).toISOString().slice(0, 10)}&sort=deadline-asc`, { title: /tenders/i, h1: 'Tenders' });
  const soonest = await page.locator('main article').first().locator('a[href^="/tenders/"]').first().getAttribute('href');
  await visit(page, '/', HOME);
  await expect(page.locator('section[aria-labelledby="closing-tenders"] li a').first()).toHaveAttribute('href', soonest!);
});

// ---------------------------------------------------------------- 2-4, 7. the three tiles

test('2: "Find tenders and funding" is a card with two actions, each with its own count; no link inside a link', async ({ page }) => {
  await visit(page, '/', HOME);
  const tile = page.locator('[data-tile]').first();
  expect(await tile.evaluate((e) => e.tagName)).toBe('DIV');
  await expect(tile.getByRole('link', { name: /^Browse tenders [\d,]+ open tenders?$/ })).toHaveAttribute('href', '/tenders');
  await expect(tile.getByRole('link', { name: /^Browse funding [\d,]+ open funding calls?$/ })).toHaveAttribute('href', '/funding');
  expect(await page.locator('a a').count(), 'a link inside a link').toBe(0);
  // one click to funding
  await tile.getByRole('link', { name: /^Browse funding/ }).click();
  await expect(page).toHaveURL(/\/funding$/);
});

for (const theme of ['light', 'dark'] as const) {
  test(`2: the two actions show hover and focus on their box, never an underline (${theme})`, async ({ page }) => {
    test.skip(isMobile(page), 'hover is a pointer state');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.addInitScript((t) => { try { localStorage.setItem('dg-theme', t); } catch { /* none */ } }, theme);
    await visit(page, '/', HOME);
    const look = (l: Locator) => l.evaluate((e) => { const c = getComputedStyle(e); return `${c.borderColor}|${c.backgroundColor}`; });
    const underlined = (l: Locator) => l.evaluate((root) => [root, ...root.querySelectorAll('*')].some((e) => getComputedStyle(e).textDecorationLine.includes('underline')));
    for (const a of await page.locator('[data-tile-action]').all()) {
      await page.mouse.move(1, 1);
      const rest = await look(a);
      expect(await underlined(a)).toBe(false);
      await a.hover();
      await expect.poll(() => look(a)).not.toBe(rest);
      expect(await underlined(a), 'no underline on hover').toBe(false);
      await page.mouse.move(1, 1);
      await a.focus();
      expect(await a.evaluate((e) => e.matches(':focus-visible') || document.activeElement === e)).toBe(true);
      await expect.poll(() => look(a)).not.toBe(rest);
      expect(await a.evaluate((e) => getComputedStyle(e).outlineStyle)).not.toBe('none');
      await a.blur();
    }
    // the tile around them is not a link and does not change
    const tile = page.locator('[data-tile]').first();
    const before = await look(tile);
    await tile.hover({ position: { x: 12, y: 12 } });
    expect(await look(tile)).toBe(before);
  });
}

test('3: the check tile says the questions it asks, not "five short sets"', async ({ page }) => {
  await visit(page, '/', HOME);
  const tile = page.locator('[data-tile]').nth(2);
  await expect(tile).toContainText('five steps of 25 to 35 questions');
  await expect(tile).toContainText('To supply defence buyers, one page of 19 to 35 questions.');
  await expect(tile).not.toContainText(/Five short sets/i);
  // the readiness check says the same of itself; the chooser page too
  await visit(page, '/readiness', { title: /readiness/i, h1: /readiness/i, text: [/25 to 35 in all/] });
  await visit(page, '/check', { title: /Check my company/, h1: 'Check my company', text: [/Five steps of 25 to 35 questions/] });
});

/** The questions a form shows now: each group (a fieldset) once, and each field outside a group. */
const countQuestions = (form: Locator) => form.evaluate((f) => {
  const seen = (e: Element) => (e as HTMLElement).offsetParent !== null || getComputedStyle(e).position === 'fixed';
  const groups = [...f.querySelectorAll('fieldset')].filter((g) => seen(g) && !g.parentElement?.closest('fieldset'));
  const fields = [...f.querySelectorAll('select, input:not([type=hidden]):not([type=radio]):not([type=checkbox]), textarea')]
    .filter((e) => seen(e) && !e.closest('fieldset'));
  return groups.length + fields.length;
});

test('3: the supplier profile asks 19 to 35 questions on one page (the tile says so)', async ({ page }) => {
  await visit(page, '/readiness/supplier', { title: /supplier/i, h1: /supplier/i });
  const form = page.locator('main form').first();
  await page.getByLabel('Country where your company is established').selectOption('DE');
  expect(await countQuestions(form), 'a company outside Spain').toBe(19);
  await page.getByLabel('Country where your company is established').selectOption('ES');
  expect(await countQuestions(form), 'in Spain (the Ministry of Defence route asks more)').toBe(23);
  await page.getByRole('group', { name: /Do you also want EU funding/ }).getByRole('radio').first().check();
  expect(await countQuestions(form), 'in Spain, with EU funding too').toBe(35);
});

test('4: "Find partners" opens the organisations in EU-funded defence projects, with their count, and the list says its order', async ({ page }) => {
  await visit(page, '/', HOME);
  const tile = page.locator('[data-tile]').nth(1);
  await expect(tile).toHaveAttribute('href', '/organisations');
  await expect(tile).toContainText('EU-funded defence projects');
  const n = await tile.locator('[data-figure] > span:first-child').innerText();
  await expect(tile.locator('[data-figure]')).toContainText(/organisations? in EU-funded defence projects$/);
  await tile.click();
  await expect(page).toHaveURL(/\/organisations$/);
  await expect(page.locator('#results-heading')).toContainText(`of ${n} organisations`);
  // the order, on the list
  await expect(page.getByRole('combobox', { name: /Sort|Order/i }).or(page.locator('select[name="sort"]')).first()).toBeAttached();
  expect(await page.locator('main').innerText()).toContain('Most defence projects first');
  // the winners list says its own order, and why Spanish winners lead (only Spain's national awards are read)
  await visit(page, '/suppliers', { title: /supplier/i, h1: 'Companies' });
  const note = page.locator('[data-order-note]');
  if (await note.count()) {
    await expect(note).toContainText('Most wins first');
    await expect(note.getByRole('link', { name: /TED.s winners only/ })).toHaveAttribute('href', '/suppliers?source=ted');
  }
});

test('7: EDF, EDIP and SAFE are expanded where the home page first names them, and /glossary has them', async ({ page }) => {
  await visit(page, '/', HOME);
  const lead = page.locator('section[aria-labelledby="hero"] p').first();
  for (const [id, full] of [['edf', 'European Defence Fund'], ['edip', 'European Defence Industry Programme'], ['safe', 'Security Action for Europe']]) {
    await expect(lead.locator(`abbr[data-glossary="${id}"]`)).toHaveAttribute('title', full);
  }
  await visit(page, '/glossary', { title: /glossary/i, h1: /glossary/i });
  for (const id of ['edf', 'edip', 'safe']) await expect(page.locator(`[id="${id}"]`)).toBeAttached();
});

// ---------------------------------------------------------------- 5, 6. one search on the first screen; a placeholder that fits a phone

test('5: on a desktop the home page has its own search only; every other page keeps the header search', async ({ page }) => {
  test.skip(isMobile(page), 'the phone menu has its own search');
  await page.setViewportSize({ width: 1440, height: 900 });
  await visit(page, '/', HOME);
  await expect(page.getByRole('searchbox')).toHaveCount(1);
  await expect(page.locator('#header-search')).toHaveCount(0);
  await visit(page, '/about', { title: /About/, h1: 'About' });
  await expect(page.locator('#header-search')).toBeVisible();
});

test('5: on a phone the menu keeps its search on the home page', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await visit(page, '/', HOME);
  await page.getByRole('button', { name: 'Open menu' }).click();
  await expect(page.locator('#menu-search')).toBeVisible();
});

for (const width of [320, 375]) {
  test(`6: the home search placeholder fits at ${width} px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await visit(page, '/', HOME);
    const fit = await page.locator('#home-search').evaluate((el) => {
      const input = el as HTMLInputElement;
      const s = getComputedStyle(input);
      const ctx = document.createElement('canvas').getContext('2d')!;
      ctx.font = `${s.fontWeight} ${s.fontSize} ${s.fontFamily}`;
      return { text: ctx.measureText(input.placeholder).width, room: input.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight) };
    });
    expect(fit.text).toBeLessThanOrEqual(fit.room);
  });
}

// ---------------------------------------------------------------- 8-10. lists, the 404 tab, breadcrumbs

test('8: What changed past its last page goes to the last page, as the other lists do', async ({ request }) => {
  for (const path of ['/changes?page=999', '/changes?page=60']) {
    const r = await request.get(path, { maxRedirects: 0 });
    expect(r.status(), path).toBe(307);
    const to = new URL(r.headers().location, 'http://x.test');
    expect(to.pathname).toBe('/changes');
    expect(Number(to.searchParams.get('page') ?? '1')).toBeLessThan(60);
  }
  expect((await request.get('/buyers?page=999', { maxRedirects: 0 })).status()).toBe(307);
});

test('9: /styleguide in production is a 404 whose tab says so', async ({ page }) => {
  await visit(page, '/styleguide', { status: 404, title: /^Page not found/, h1: /.+/ });
});

test('10: breadcrumbs use the menu’s names', async ({ page }) => {
  const crumbs = (p: Page) => p.getByRole('navigation', { name: 'Breadcrumb' }).getByRole('listitem').allInnerTexts();
  await visit(page, '/networks/consortium-gaps', { title: /.+/, h1: 'Consortium gaps' });
  expect((await crumbs(page)).map((t) => t.trim())).toEqual(['Home', 'Partners', 'Consortium gaps']);
  await visit(page, '/networks/ukraine-partners', { title: /.+/, h1: 'Ukraine partners' });
  expect((await crumbs(page)).map((t) => t.trim())).toEqual(['Home', 'Partners', 'Ukraine partners']);
  await visit(page, '/organisations/101-alpha-systems-gmbh', { title: /.+/, h1: /.+/ });
  expect((await crumbs(page)).slice(0, 3).map((t) => t.trim())).toEqual(['Home', 'Companies', 'In EU-funded projects']);
  await visit(page, '/projects/201-alpha', { title: /.+/, h1: /.+/ });
  expect((await crumbs(page)).slice(0, 3).map((t) => t.trim())).toEqual(['Home', 'Companies', 'In EU-funded projects']);
  await visit(page, '/suppliers', { title: /.+/, h1: 'Companies' });
  const supplier = await page.locator('main a[href^="/suppliers/"]').first().getAttribute('href');
  await visit(page, supplier!, { title: /.+/, h1: /.+/ });
  expect((await crumbs(page)).slice(0, 3).map((t) => t.trim())).toEqual(['Home', 'Companies', 'Won contracts']);
  for (const old of ['Organisations', 'Gaps in consortia', 'Partners of Ukrainian organisations']) expect(await crumbs(page)).not.toContain(old);
});

// ---------------------------------------------------------------- 11, 12. the funding list's count and the eligibility box

const fact = (value: unknown) => ({ value, note: null, scope: 'call_document' });
/** Three kinds of call (fit.spec.ts): eligible, SME-only (a no for a large company), rules not read. */
const factsOf = (id: number) => (id % 3 === 0
  ? { state: 'read', basis: 'call_document', programme: 'HORIZON', topic: 'HORIZON-CL3-2026-01-BM-01', facts: { eligible_countries: fact('EU Member States'), consortium_required: fact(false), sme_only: fact(false), ownership_control_restriction: fact(false) } }
  : id % 3 === 1
    ? { state: 'read', basis: 'call_document', programme: 'HORIZON', topic: 'HORIZON-CL3-2026-01-BM-01', facts: { eligible_countries: fact('EU Member States'), consortium_required: fact(false), sme_only: fact(true) } }
    : { state: 'not_read', basis: 'call_document', programme: 'HORIZON', topic: 'HORIZON-CL3-2026-01-BM-01', facts: {} });
const LARGE_ES = {
  version: 2, step: 6, updatedAt: '2026-10-17T10:00:00.000Z', name: '', management: 'same', managementCountry: '', uaOccupied: '', regime: 'dual_use',
  componentPct: '10', restricted: 'no', statuses: {}, classified: 'no', exportIntent: 'none', sizeClass: 'large', control: 'no', country: 'ES',
};

test('11: with "Fits my profile" on, the count says how many calls are shown and how many are hidden', async ({ page }) => {
  await page.addInitScript((v) => window.localStorage.setItem('dg.profile.v1', JSON.stringify(v)), LARGE_ES);
  await page.route('**/api/fit/facts*', (route) => {
    const ids = (new URL(route.request().url()).searchParams.get('ids') ?? '').split(',').filter(Boolean).map(Number);
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: Object.fromEntries(ids.map((i) => [String(i), factsOf(i)])) }) });
  });
  await visit(page, '/funding?fit=1', { title: /funding/i, h1: /funding/i });
  const heading = page.locator('#results-heading');
  await expect(heading).toHaveText(/^Showing \d+ of \d+ calls? \(\d+ hidden: blocked or without rules\)$/);
  const [, shown, total, hidden] = (await heading.innerText()).match(/^Showing (\d+) of (\d+) calls? \((\d+) hidden/)!.map(Number);
  const items = page.locator('section[aria-labelledby="results-heading"] > ul > li');
  expect(await items.locator(':scope:not([hidden])').count()).toBe(shown);
  expect(shown + hidden).toBe(total);
  // switched off, the plain count again
  await page.getByRole('checkbox', { name: /^Fits my profile/ }).uncheck();
  await expect(heading).not.toContainText('hidden');
});

test('12: the eligibility box names a rule as blocking only where its line says no', async ({ page }) => {
  await page.route('**/api/fit/facts*', async (route) => {
    const ids = (new URL(route.request().url()).searchParams.get('ids') ?? '').split(',').filter(Boolean);
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: Object.fromEntries(ids.map((i) => [i, {
      state: 'read', basis: 'call_document', programme: 'EDIP', topic: 'EDF-EDIP-P-2027-FNLC-CPA-TEST',
      facts: { eligible_countries: fact('EU Member States'), entity_types: { value: ['private_company', 'public_body'], note: null, quote: 'q', scope: 'call_document' } } }])) }) });
  });
  await page.route('**/api/funding/*/partners*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    call: { id: '21', slug: '21-x', topic: null }, area: null, partners: [], countries: [], total: 0, country: null, prefer: null, note: '' }) }));
  await visit(page, '/funding/21-edip-2027-shared-testing-facilities-manufacturers', { title: /Common procurement/, h1: /Common procurement/ });
  const top = page.locator('[data-apply-summary]');
  await top.getByLabel('Your country').selectOption('ES');
  await top.getByLabel('Your kind of organisation').selectOption('sme');
  await expect(top.locator('[data-page-verdict]')).toHaveAttribute('data-verdict', 'no');
  const form = page.getByRole('form', { name: 'Check your company against this call' });
  if (await form.count()) {
    const box = form.locator('xpath=..').locator('[aria-live="polite"]').first();
    await expect(page.locator('[data-form-word]')).toHaveText(/^Blocked by: Who may apply/);
    const lines = await box.locator('li').allInnerTexts();
    const who = lines.filter((l) => l.startsWith('Who may apply:'));
    expect(who, 'one line named "Who may apply"').toHaveLength(1);
    expect(who[0]).not.toMatch(/^Who may apply: Check\./);
    await expect(box).toContainText(/is a no on your answers/);
  }
});

// ---------------------------------------------------------------- 13-15. names, search counts, how to cite

test('13: a buyer’s name variants never show the removal placeholder', async ({ page }) => {
  await visit(page, '/buyers/1-demo-armaments-agency', { title: /Demo Armaments Agency/i, h1: 'Demo Armaments Agency' });
  const fold = page.locator('[data-variant-names]');
  await fold.locator('summary').click();
  await expect(fold.locator('li')).toHaveText(['Skarb Panstwa - Demo Armaments Agency', 'DEMO ARMAMENTS AGENCY, WARSZAWA']);
  expect(await page.locator('main').innerText()).not.toContain('[email removed]');
});

test('14: the search never says "See all at least"', async ({ page }) => {
  await visit(page, '/search?q=Demo', { title: /Search/i, h1: /Search|Results/ });
  expect(await page.locator('main').innerText()).not.toMatch(/See all at least/);
  await expect(page.getByRole('link', { name: /^See (all|the) [\d,]+\+? / }).first()).toBeVisible();
});

test('15: the market page says how to cite its figures, next to their date', async ({ page }) => {
  await visit(page, '/market', { title: /Market overview/, h1: 'Market overview' });
  const cite = page.locator('[data-cite]');
  await expect(cite).toContainText(/^How to cite: DefenceGate \(https?:\/\/[^)]+\/market\), from .+, figures as of \d{1,2} \w{3} \d{4}, \d{2}:\d{2} UTC\. Terms of use, 12$/);
  await expect(cite.getByRole('link', { name: 'Terms of use, 12' })).toHaveAttribute('href', '/terms#c12');
  const asOf = await page.locator('.facts-grid time').last().innerText();
  await expect(cite).toContainText(asOf);
});

// ---------------------------------------------------------------- 16. old notice addresses

test('16: an old address of a notice that left the scope says what it was; one with a publication in scope goes there', async ({ page, request }) => {
  await visit(page, '/tenders/990001', { title: /^No longer in our defence scope/, h1: 'No longer in our defence scope' });
  await expect(page.getByRole('link', { name: 'Latvia – Utility vehicles' })).toHaveAttribute('href', 'https://ted.europa.eu/en/notice/-/detail/711894-2026');
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/);
  const moved = await request.get('/tenders/990002', { maxRedirects: 0 });
  expect(moved.status()).toBe(308);
  expect(moved.headers().location).toMatch(/^\/tenders\/1-/);
  // an id never held stays a 404
  await visit(page, '/tenders/990003', { status: 404, title: /Tender not found/, h1: 'This tender is not in the directory' });
});

// ---------------------------------------------------------------- 17. a short filter column

test('17: the tenders filter column folds its long groups; the chosen ones stay in sight; the scope note uses the labels', async ({ page }) => {
  test.skip(isMobile(page), 'the filters fold away on a phone');
  await page.setViewportSize({ width: 1440, height: 900 });
  await visit(page, '/tenders?country=SE,PT', { title: /tenders/i, h1: 'Tenders' });
  const form = page.getByRole('search', { name: 'Filter tenders' });
  // 2,450 px on the demo build with two countries chosen (the product groups 460 px, the countries 305 px); the production column was
  // ~3,500 px (p01). The bound leaves room for the scope counts' words.
  const height = await form.evaluate((f) => f.getBoundingClientRect().height);
  expect(height, 'the filter column').toBeLessThan(2600);
  for (const [group, most] of [['[data-cpv-presets]', 520], ['details:has(> summary:has-text("Buyer country"))', 360]] as const) {
    expect(await form.locator(group).first().evaluate((e) => e.getBoundingClientRect().height), group).toBeLessThan(most);
  }
  const country = form.locator('details', { hasText: 'Buyer country' }).first();
  for (const c of ['SE', 'PT']) await expect(country.locator(`input[value="${c}"]`)).toBeVisible();
  const all = country.locator('[data-show-all] > summary');
  await expect(all).toHaveText(/^Show all \d+ countries/);
  await expect(country.locator('input[value="SI"]')).toBeHidden();
  await all.click();
  await expect(country.locator('input[value="SI"]')).toBeVisible();
  // every box is still a filter the form sends
  expect(await country.locator('input[type=checkbox]').count()).toBeGreaterThanOrEqual(25);
  // product groups: the first few of each in sight, the rest folded, the chosen one in sight
  const presets = page.locator('[data-cpv-presets]');
  await expect(presets.locator('[data-preset-group="goods"] [data-show-all] > summary')).toHaveText(/^Show all 9 goods groups/);   // the folded "Show fewer" is in its text too
  await visit(page, '/tenders?cpv=345,355,5064,50241', { title: /tenders/i, h1: 'Tenders' });
  await expect(page.locator('[data-cpv-presets] a[aria-current="true"]')).toBeVisible();
  await expect(page.locator('[data-cpv-presets] a[aria-current="true"]')).toHaveText('Ships and naval');
  // the note says the labels' words
  const text = await page.locator('main').innerText();
  expect(text).not.toContain('Core and supplies');
});
