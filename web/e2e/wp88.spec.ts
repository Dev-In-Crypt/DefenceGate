import { expect, test, type Page } from '@playwright/test';
import { openAbout, visit } from './helpers';

/**
 * WP-88 (docs/verification/product/wp88-selfcheck.md): section 3 of the UX audit of 22 October 2026. Each page opens with one sentence
 * and then its list, form or table; what explains coverage, method, caveats, licences or confidence is in a collapsed About this data /
 * How we count (`[data-about] details`), closed by default and open on paper; internal terms are not shown bare outside it.
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;

/** The internal terms of the audit. A term inside a closed details is not in `innerText`, so it does not count. */
const TERMS: RegExp[] = [
  /confidence [0-9]|(?:low|medium|high)(?:est)? confidence/i, /\balias\b/i, /normalised name/i, /\bPIC is held/i, /\bRegime\b/,
  /Financial support to third parties/i, /\bPLACSP\b/, /\bSEDIA\b/, /\bCORDIS\b/, /\bEDIDP\b/, /\bPADR\b/, /\bLCSP\b/, /\bSDA\b/,
  /\bHSE[MS]\b/, /\bNSIP\b/, /\bFNLC\b/, /\bLS-IRA\b/, /\bFSTP\b/, /`/, /Category: the country of establishment/i,
  // the tender pages' terms of the audit
  /Classified automatically/i, /Core: the notice itself/i, /Defence-relevant \(core/i,
];

/**
 * The visible text of main without the source attributions (`[data-attribution]`): a source's own name in its credit line
 * ("Source: CORDIS, European Commission", "Origen de los datos: …") must stay on screen and is not jargon.
 */
async function visibleOutsideAttribution(page: Page): Promise<string> {
  let text = await page.locator('main').innerText();
  for (const a of await page.locator('main [data-attribution]').allInnerTexts()) text = text.replace(a, '');
  return text;
}

const PAGES: { path: string; title: RegExp; h1: string | RegExp; noAbout?: true }[] = [
  { path: '/suppliers', title: /supplier map/i, h1: 'Companies' },
  { path: '/organisations', title: /Organisations/i, h1: 'Companies' },
  { path: '/suppliers/1-demo-airframes-gmbh', title: /Demo Airframes/i, h1: 'Demo Airframes' },
  { path: '/organisations/101-alpha-systems-gmbh', title: /Alpha Systems/i, h1: 'Alpha Systems' },
  { path: '/funding', title: /funding/i, h1: 'Funding', noAbout: true },
  { path: '/readiness', title: /readiness check/i, h1: 'Readiness check' },
  { path: '/readiness/supplier', title: /supplier profile/i, h1: 'Supplier profile' },
  { path: '/regulation', title: /regulat/i, h1: 'Regulatory tracker' },
  { path: '/networks/consortium-gaps', title: /Repeat participants/i, h1: 'Consortium gaps' },
  { path: '/networks/ukraine-partners', title: /Ukrainian organisations/i, h1: 'Ukraine partners' },
  { path: '/market', title: /market/i, h1: 'Market overview' },
  // WP-87's pages, after it was merged
  { path: '/tenders', title: /tenders/i, h1: 'Tenders', noAbout: true },
  { path: '/tenders/1-framework-agreement-machined-aluminium-housings', title: /machined aluminium/i, h1: /machined aluminium/i },
  { path: '/buyers', title: /buyers/i, h1: 'Buyers', noAbout: true },
  { path: '/buyers/1-demo-armaments-agency', title: /Demo Armaments/i, h1: 'Demo Armaments Agency' },
  { path: '/data', title: /Source status/i, h1: 'Source status' },
  { path: '/changes', title: /changed/i, h1: 'What changed' },
  { path: '/calendar', title: /calendar/i, h1: 'Deadline calendar', noAbout: true },
];

for (const p of PAGES) {
  test(`${p.path}: no internal term is shown outside About this data, which is there, closed and keyboard-operable`, async ({ page }) => {
    await visit(page, p.path, p);
    const about = page.locator('main [data-about] details');
    const text = await visibleOutsideAttribution(page);
    for (const re of TERMS) expect(text.match(re)?.[0] ?? null, `${p.path}: "${re}" is shown outside About this data`).toBeNull();
    if (p.noAbout) return;
    expect(await about.count(), `${p.path}: a collapsed About this data`).toBeGreaterThan(0);
    for (const d of await about.all()) expect(await d.evaluate((el) => (el as HTMLDetailsElement).open)).toBe(false);
    // its summary is a keyboard control
    await about.first().locator('summary').focus();
    await page.keyboard.press('Enter');
    await expect(about.first()).toHaveAttribute('open', '');
  });
}

test('a collapsed About this data opens for printing and closes after', async ({ page }) => {
  test.skip(isMobile(page), 'the same at every width');
  await visit(page, '/suppliers', { title: /supplier map/i, h1: 'Companies' });
  const d = page.locator('main [data-about] details').first();
  // the listener is attached once the page has hydrated: ask until it answers
  await expect.poll(async () => {
    await page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
    return d.evaluate((el) => (el as HTMLDetailsElement).open);
  }).toBe(true);
  await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
  await expect(d).not.toHaveAttribute('open', '');
  // what was moved is still on the page, one click away
  await openAbout(page);
  await expect(page.locator('#coverage')).toContainText('published in the last three years');
});

test('licence and attribution lines stay on screen, outside any collapsed block', async ({ page }) => {
  for (const [path, title, h1, said] of [
    ['/suppliers', /supplier map/i, 'Companies', /Source: TED, © European Union/],
    ['/suppliers/1-demo-airframes-gmbh', /Demo Airframes/i, 'Demo Airframes', /© European Union/],
    ['/organisations', /Organisations/i, 'Companies', /Source: CORDIS, European Commission\. Licence: Commission Decision 2011\/833\/EU/],
    ['/organisations/101-alpha-systems-gmbh', /Alpha Systems/i, 'Alpha Systems', /EDF results factsheets\. Licence:/],
  ] as const) {
    await visit(page, path, { title, h1 });
    const line = page.locator('main [data-attribution]').filter({ hasText: said }).first();
    await expect(line, path).toBeVisible();
    expect(await line.evaluate((el) => Boolean(el.closest('details')))).toBe(false);
  }
});

test('the readiness heading says the answers are not stored on our server, and the paragraph says what is sent', async ({ page }) => {
  await visit(page, '/readiness', { title: /readiness check/i, h1: 'Readiness check', text: ['Your answers are not stored on our server'] });
  await expect(page.getByText('Your answers stay in this browser')).toHaveCount(0);
  await openAbout(page);
  await expect(page.getByText(/The only thing that leaves your browser is the request that computes the verdict/)).toBeVisible();
});

test('the recognition of an organisation is in plain words, with the method and confidence one click away', async ({ page }) => {
  await visit(page, '/organisations/101-alpha-systems-gmbh', { title: /Alpha Systems/i, h1: 'Alpha Systems' });
  await expect(page.getByRole('link', { name: 'What “PIC” means' })).toHaveAttribute('href', '/glossary#pic');
  await expect(page.getByText(/normalised name/)).toHaveCount(0);
  await openAbout(page);
  await expect(page.getByText(/matched by the same name \(ignoring accents, capitals and the legal form\) in the same country/).first()).toBeVisible();
});

test('every glossary link of the changed pages has its entry', async ({ page }) => {
  test.skip(isMobile(page), 'the same at every width');
  await visit(page, '/glossary', { title: /glossary/i, h1: 'Glossary' });
  for (const id of ['pic', 'match-confidence', 'edidp', 'padr', 'cordis', 'placsp', 'hsem', 'hses', 'cascade-funding', 'call-and-topic', 'dual-use']) {
    await expect(page.locator(`[id="${id}"]`), id).toHaveCount(1);
  }
});

for (const path of ['/networks/consortium-gaps?topic=CYBER&lacking=UA', '/suppliers', '/market']) {
  test(`${path} fits 375 px without a horizontal scroll`, async ({ page }) => {
    test.skip(!isMobile(page), 'a phone check');
    await page.goto(path, { waitUntil: 'load' });
    const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    expect(scroll, `${path}: ${scroll} px in ${client} px`).toBeLessThanOrEqual(client);
  });
}

test('on a phone the consortium gaps table reads as cards, with no sideways scroll of its own', async ({ page }) => {
  test.skip(!isMobile(page), 'a phone check');
  await visit(page, '/networks/consortium-gaps?topic=CYBER&lacking=UA', { title: /Repeat participants/i, h1: 'Consortium gaps' });
  const table = page.getByRole('table', { name: /Organisations funded repeatedly/i });
  await expect(table.getByRole('link', { name: /Bravo/i })).toBeVisible();
  const fit = await table.evaluate((t) => ({ row: getComputedStyle(t.querySelector('tbody tr')!).display, width: t.scrollWidth, box: t.parentElement!.clientWidth }));
  expect(fit.row).toBe('block');
  expect(fit.width).toBeLessThanOrEqual(fit.box);
  await expect(table.locator('td[data-label="Partner countries seen"]').first()).toBeVisible();
});
