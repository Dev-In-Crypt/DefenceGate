import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-58 (docs/verification/product/wp58-selfcheck.md): accessibility and interaction. The branded select as the accessibility tree
 * sees it, focus after Escape and after a route change, the radio-group error, titles of list views, `lang`, distinct link names,
 * the skip past the filters, and the wording of a failed check. Desktop checks skip on the phone where the control differs.
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const CHANGES = { title: /what changed/i, h1: 'What changed' };

type AxNode = { role?: { value: string }; name?: { value: string }; properties?: { name: string; value: { value?: unknown; relatedNodes?: { idref?: string }[] } }[] };
/** What the accessibility tree (Chromium's, through the DevTools protocol) says about the focused node. */
async function axFocused(page: Page) {
  const cdp = await page.context().newCDPSession(page);
  const { nodes } = await cdp.send('Accessibility.getFullAXTree') as { nodes: AxNode[] };
  await cdp.detach();
  const props = (n: AxNode): Record<string, unknown> => Object.fromEntries((n.properties ?? []).map((p) => [p.name, p.value.value ?? p.value.relatedNodes?.map((r) => r.idref)]));
  // The document is "focused" too; the element with focus is the other one.
  const n = nodes.find((x) => props(x).focused === true && x.role?.value !== 'RootWebArea');
  const out: Record<string, unknown> | null = n ? { ...props(n), role: n.role?.value, name: n.name?.value } : null;
  return out;
}

test('the branded select: while open the list has focus and names its active option; Escape closes and returns focus', async ({ page }) => {
  test.skip(isMobile(page), 'a touch screen keeps the system picker (select.tsx)');
  await visit(page, '/changes', CHANGES);
  const combo = page.getByRole('combobox', { name: 'Buyer country' });
  await combo.focus();
  await page.keyboard.press('ArrowDown');
  const list = page.getByRole('listbox', { name: 'Buyer country' });
  await expect(list).toBeVisible();
  await expect(list).toBeFocused();
  await expect(combo).toHaveAttribute('aria-expanded', 'true');
  await expect(combo).toHaveAttribute('aria-controls', (await list.getAttribute('id'))!);
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('ArrowDown');
  const activeId = await list.locator('[data-active]').getAttribute('id');
  await expect(list.locator('[data-active]')).toHaveAttribute('role', 'option');
  await expect(list).toHaveAttribute('aria-activedescendant', activeId!);
  // The tree a screen reader reads: a focused listbox with the control's name, whose active descendant is that option.
  const ax = await axFocused(page);
  expect(ax?.role).toBe('listbox');
  expect(ax?.name).toBe('Buyer country');
  expect(ax?.activedescendant).toEqual([activeId]);
  await page.keyboard.press('Escape');
  await expect(list).toHaveCount(0);
  await expect(combo).toBeFocused();
  await expect(combo).toHaveAttribute('aria-expanded', 'false');
  expect((await axFocused(page))?.role).toBe('combobox');
});

test('the branded select: Tab from the open list chooses and moves on from the select, Shift+Tab goes back before it', async ({ page }) => {
  test.skip(isMobile(page), 'a touch screen keeps the system picker (select.tsx)');
  await visit(page, '/changes', CHANGES);
  const combo = page.getByRole('combobox', { name: 'Buyer country' });
  const order = await page.evaluate(() => [...document.querySelectorAll<HTMLElement>('#main a[href], #main button, #main input, #main select')].filter((e) => e.offsetParent !== null).map((e) => e.outerHTML.slice(0, 60)));
  const at = order.findIndex((h) => h.startsWith('<select'));
  await combo.focus();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('listbox')).toHaveCount(0);
  expect(await combo.getAttribute('data-value'), 'Tab chose the active option').not.toBe('');
  expect(await page.evaluate(() => document.activeElement!.outerHTML.slice(0, 60)), 'focus moved on from the select').toBe(order[at + 1]);
  await combo.focus();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Shift+Tab');
  expect(await page.evaluate(() => document.activeElement!.outerHTML.slice(0, 60))).toBe(order[at - 1]);
});

test('Escape on a link of a header menu returns focus to its button', async ({ page }) => {
  test.skip((page.viewportSize()?.width ?? 0) < 1280, 'the menus of the bar are shown from xl');
  await visit(page, '/', { title: /DefenceGate/, h1: /.+/ });
  const button = page.getByRole('button', { name: 'Network: more pages' });
  await button.focus();
  await page.keyboard.press('Enter');
  await expect(button).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Tab');
  await expect(page.locator('#sub-Network a').first()).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(button).toBeFocused();
  await expect(button).toHaveAttribute('aria-expanded', 'false');
});

test('after a client-side route change focus is on the new page heading; on the first load it is not moved', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: /.+/ });
  expect(await page.evaluate(() => document.activeElement?.tagName)).toBe('BODY');
  if (isMobile(page)) {
    await page.getByRole('button', { name: 'Open menu' }).click();
    await page.locator('#mobile-nav').getByRole('link', { name: 'Tenders', exact: true }).click();
  } else {
    await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Tenders', exact: true }).click();
  }
  await page.waitForURL(/\/tenders$/);
  await expect(page.locator('#main h1')).toBeFocused();
  await expect(page.locator('#main h1')).toContainText('Tenders');
  // The heading takes focus but is not a tab stop.
  await expect(page.locator('#main h1')).toHaveAttribute('tabindex', '-1');
});

test('the legal-form error belongs to its group: fieldset described by it, radios invalid', async ({ page }) => {
  await visit(page, '/readiness', { title: /readiness/i, h1: /.+/ });
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  const group = page.getByRole('group', { name: 'What is the legal form of your organisation?' });
  await expect(group).toContainText('Choose the legal form to go on.');
  const described = await group.evaluate((el) => (el.getAttribute('aria-describedby') ?? '').split(' ').map((id) => document.getElementById(id)?.textContent ?? '').join(' | '));
  expect(described).toContain('Choose the legal form to go on.');
  for (const r of await group.getByRole('radio').all()) await expect(r).toHaveAttribute('aria-invalid', 'true');
  await group.getByRole('radio').first().check();
  await expect(group).not.toContainText('Choose the legal form to go on.');
  for (const r of await group.getByRole('radio').all()) await expect(r).not.toHaveAttribute('aria-invalid', 'true');
});

test('filtered and paged list views have titles of their own', async ({ page }) => {
  const cases: [string, RegExp][] = [
    ['/tenders', /^Defence and dual-use tenders · DefenceGate$/],
    ['/tenders?page=2', /^Tenders, page 2 · DefenceGate$/],
    ['/tenders?country=DE', /^Tenders in Germany · DefenceGate$/],
    ['/funding?page=2', /^Funding calls, page 2 · DefenceGate$/],
    ['/funding?q=drone', /^Funding calls: “drone” · DefenceGate$/],
    ['/buyers?country=PL', /^Buyers in Poland · DefenceGate$/],
    ['/organisations?country=DE', /^Organisations in Germany · DefenceGate$/],
    ['/suppliers?country=DE', /^Supplier map in Germany · DefenceGate$/],
  ];
  for (const [url, title] of cases) {
    await page.goto(url);
    await expect(page, url).toHaveTitle(title);
  }
});

test('a non-English tender title carries its language on the page and in the breadcrumb', async ({ page }) => {
  await page.goto('/tenders/3');
  await expect(page.locator('#main h1')).toHaveAttribute('lang', 'pl');
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' }).locator('[aria-current=page]')).toHaveAttribute('lang', 'pl');
});

test('the "View original" links of a list have names of their own', async ({ page }) => {
  await page.goto('/tenders');
  const names = await page.locator('#main a', { hasText: 'View original' }).evaluateAll((els) => els.map((e) => (e.textContent ?? '').replace(/\s+/g, ' ').trim()));
  expect(names.length).toBeGreaterThan(3);
  expect(new Set(names).size, names.join('\n')).toBe(names.length);
  expect(names[0]).toMatch(/^View original: .+, at .+ \(opens in new tab\)$/);
});

test('a keyboard skips the filters: "Skip to results" is the first stop of the filter column and lands on the results', async ({ page }) => {
  await page.goto('/funding');
  const skip = page.getByRole('link', { name: 'Skip to results' });
  await skip.focus();
  await expect(skip).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(page.locator('#results')).toBeFocused();
  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => document.getElementById('results')!.contains(document.activeElement))).toBe(true);
});

test('a check that gets no answer shows the standard error, not the browser\'s words', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('dg.profile.v1', JSON.stringify({
    version: 2, step: 6, updatedAt: '2026-10-18T10:00:00.000Z', name: '', sizeClass: 'small', country: 'ES', legalForm: 'legal_person',
    management: 'same', managementCountry: '', control: 'no', uaOccupied: '', regime: 'dual_use', componentPct: '10', restricted: 'no',
    uaEeaComponents: 'no', safeRole: 'contractor', statuses: {}, classified: 'no', exportIntent: 'none',
  })));
  await page.route('**/api/readiness/assess', (route) => route.abort('failed'));
  await page.goto('/readiness/results');
  const alert = page.getByRole('alert').filter({ hasText: 'The check could not be computed' });
  await expect(alert).toBeVisible();
  await expect(alert.getByRole('button', { name: 'Try again' })).toBeVisible();
  await expect(page.locator('#main')).not.toContainText(/failed to fetch/i);
});

test('the empty-state link of /digest is underlined like any link in running text', async ({ page }) => {
  await page.goto('/digest');
  await page.waitForLoadState('networkidle');
  // The empty state's text is a div of running text: its links are underlined (WP-55 rule, `.run-text`).
  const line = await page.evaluate(() => {
    const d = document.createElement('div'); d.className = 'run-text';
    const a = document.createElement('a'); a.href = '/changes'; a.className = 'font-semibold'; a.textContent = 'What changed';
    d.append(a); (document.querySelector('main') ?? document.body).append(d);
    return getComputedStyle(a).textDecorationLine;
  });
  expect(line).toBe('underline');
});

test('the buyer link of a tender page is a 32 px target (it follows "Buyer:", so the stand-alone rule of WP-55 missed it)', async ({ page }) => {
  await page.goto('/tenders/1-framework-agreement-machined-aluminium-housings');
  const h = await page.locator('#main p', { hasText: 'Buyer:' }).getByRole('link').first().evaluate((el) => el.getBoundingClientRect().height);
  expect(h).toBeGreaterThanOrEqual(32);
});
