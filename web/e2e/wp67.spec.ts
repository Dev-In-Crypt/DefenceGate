import { mkdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-67: the printable supplier report (/readiness/supplier/report) and the entry copy of /readiness/supplier. What this proves: for the three
 * sample companies of WP-65 (stored profiles `fixtures/profile-es-sup-*.json`), the report sends nothing but the request of the results page
 * (`request-es-sup-*.json`), shows the profile as entered, the verdicts, and the red / amber / green roadmap of `lib/wp67.check.ts` in its
 * order, with the PECAL note, the specialist flags and the disclaimer; "Who buys what you make" is shown (WP-66, wp66.spec.ts); in print the site
 * chrome and the buttons are gone, each section starts a page and an outside link prints its address. The print pictures and PDFs of the
 * three reports are written to `WP67_SHOTS` (the self-check) or the test's output folder.
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));

async function asSupplier(page: Page, key: string): Promise<unknown[]> {
  const posted: unknown[] = [];
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); },
    fixture(`profile-${key}.json`));
  await page.route('**/api/readiness/assess', async (route) => {
    posted.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture(`assess-${key}.json`)) });
  });
  return posted;
}

const ORDER: Record<string, string[]> = {
  'es-sup-civil': ['REQ-ISO9001', 'IATF16949', 'REQ-RID', 'REQ-PIC', 'REQ-NCAGE', 'REQ-AQAP2110', 'REQ-PECAL', 'REQ-EXPORT'],
  // WP-73: the HSEM is not answered on the page, so it is amber ("Needs an answer") after the PIC, no longer red by default
  'es-sup-defence': ['REQ-NCAGE', 'REQ-ISO9001', 'REQ-AQAP2110', 'REQ-RID', 'REQ-PIC', 'REQ-FSC-ES', 'REQ-PECAL', 'REQ-EXPORT', 'US-COMPONENTS'],
  'es-sup-partial': ['REQ-ISO9001', 'REQ-NCAGE', 'REQ-RID', 'REQ-PIC', 'REQ-AQAP2110', 'REQ-PECAL', 'REQ-EN9100', 'REQ-FSC-ES', 'REQ-EXPORT', 'US-COMPONENTS'],
};

for (const key of Object.keys(ORDER)) {
  test(`the report of ${key}: profile, verdicts and roadmap, nothing else sent, printable`, async ({ page }, info) => {
    const others: string[] = [];
    // WP-66: the demand map is the second request (its body, the CPV codes alone, is checked in wp66.spec.ts)
    page.on('request', (r) => { if (r.method() !== 'GET' && !/\/api\/readiness\/(assess|demand)$/.test(r.url())) others.push(`${r.method()} ${r.url()}`); });
    const posted = await asSupplier(page, key);
    await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
    const items = page.locator('[data-item]');
    await expect(items).toHaveCount(ORDER[key].length);
    expect(await items.evaluateAll((els) => els.map((e) => e.getAttribute('data-item')))).toEqual(ORDER[key]);
    expect(posted).toEqual([fixture(`request-${key}.json`)]);
    expect(others).toEqual([]);

    await expect(page.locator('[data-disclaimer]')).toHaveText('Indicative, sources linked, not legal advice.');
    for (const s of ['r-profile', 'r-results', 'r-roadmap', 'r-about']) await expect(page.locator(`[data-report-section="${s}"]`)).toBeVisible();
    await expect(page.locator('[data-report-section="r-demand"]')).toBeVisible();     // WP-66: the profiles hold CPV codes
    await expect(page.getByText('generated 12 Oct 2026, 08:00 UTC')).toBeVisible();
    // the profile as entered: the CPV codes with their titles; the verdicts of the Spanish route; the summary
    await expect(page.locator('[data-report-section="r-profile"]')).toContainText('34300000 Parts and accessories for vehicles and their engines');
    await expect(page.locator('[data-report-programme="ES-MOD"]')).toBeVisible();
    await expect(page.locator('[data-report-summary]')).toContainText('does not win a contract');
    // PECAL: amber, explained as the step that comes with a first contract
    const pecal = page.locator('[data-item="REQ-PECAL"]');
    await expect(pecal).toHaveAttribute('data-rag', 'amber');
    await expect(pecal.locator('[data-item-note]')).toContainText('not a block before a first contract');
    await expect(pecal.locator('[data-consultant]')).toContainText('Prime qualification');
    await expect(page.locator('[data-item="REQ-EXPORT"] [data-consultant]')).toContainText('Export classification');
    // no figure that a primary source does not state
    await expect(page.locator('[data-item="REQ-NCAGE"]')).not.toContainText('Free');
    await expect(page.locator('[data-item="REQ-PIC"]').getByText('Not stated in a primary source').first()).toBeVisible();

    // print: no site chrome, no buttons, a page per section, outside links followed by their address
    await page.emulateMedia({ media: 'print' });
    await expect(page.getByRole('banner')).toBeHidden();
    await expect(page.getByRole('contentinfo')).toBeHidden();
    await expect(page.getByRole('button', { name: 'Print or save as PDF' })).toBeHidden();
    const brk = await page.locator('[data-report-section]').evaluateAll((els) => els.map((e) => getComputedStyle(e).breakBefore));
    expect(brk[0]).not.toBe('page');
    expect(brk.slice(1).every((b) => b === 'page')).toBe(true);
    const after = await page.locator('[data-item="REQ-PECAL"] a[href^="http"]').first().evaluate((a) => getComputedStyle(a, '::after').content);
    expect(after).toContain('https://www.defensa.gob.es/');

    const dir = process.env.WP67_SHOTS ?? info.outputPath();
    mkdirSync(dir, { recursive: true });
    const name = `${key}-${info.project.name}`;
    await page.screenshot({ path: path.join(dir, `${name}-print.png`), fullPage: true });
    if (info.project.name === 'desktop') await page.pdf({ path: path.join(dir, `${key}.pdf`), format: 'A4', printBackground: false });
  });
}

test('no profile in this browser: the report asks for the answers', async ({ page }) => {
  await visit(page, '/readiness/supplier/report', { title: /supplier readiness report/i, h1: 'Supplier readiness report' });
  await expect(page.getByText('No answers in this browser yet')).toBeVisible();
  await expect(page.locator('[data-item]')).toHaveCount(0);
});

test('the supplier page says who it is for, and the results link to the report', async ({ page }) => {
  await asSupplier(page, 'es-sup-civil');
  await visit(page, '/readiness/supplier', { title: /supplier profile/i, h1: 'Supplier profile' });
  await expect(page.getByRole('heading', { name: 'Who this is for' })).toBeVisible();
  const copy = page.locator('[data-supplier-audience]');
  await expect(copy).toContainText('Manufacturers in Spain that make civilian products today');
  await expect(copy).toContainText('does not say that you will win one');
  await visit(page, '/readiness/results', { title: /readiness results/i, h1: 'Your readiness results' });
  await page.getByRole('link', { name: 'My supplier report' }).click();
  await expect(page).toHaveURL(/\/readiness\/supplier\/report$/);
  await expect(page.locator('[data-item="REQ-RID"]')).toHaveAttribute('data-rag', 'red');
});
