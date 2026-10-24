import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';
import { FOOTER_GROUPS, LEGAL_LINKS, MAIN_NAV } from '../lib/nav';

/**
 * WP-86 (docs/verification/product/wp86-selfcheck.md): the menu of the UX audit of 22 October 2026, the site search, the home
 * page's tasks, Check my company and the old addresses. The demo data's companies, buyers and some tenders are named "Demo …".
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const h1Of = async (page: Page, href: string) => {
  const res = await page.goto(href, { waitUntil: 'load' });
  expect(res?.status(), href).toBe(200);
  return (await page.locator('h1').first().innerText()).trim();
};

test('every label of the header and the footer is the h1 of the page it opens', async ({ page }) => {
  test.skip(isMobile(page), 'the same links at every width; once is enough');
  const links = new Map<string, string>();
  for (const n of MAIN_NAV) {
    if (n.href) links.set(n.href, n.label);
    for (const c of n.children ?? []) links.set(c.href, c.label);
  }
  for (const g of FOOTER_GROUPS) for (const l of g.links) links.set(l.href, l.label);
  for (const l of LEGAL_LINKS) links.set(l.href, l.label);
  // The one exception: the alerts page's link says that alerts are not open yet.
  links.set('/alerts', 'Alerts and saved searches');
  for (const [href, label] of links) expect(await h1Of(page, href), href).toBe(label);
});

test('the header has the six items and the search field; the footer repeats each group by name', async ({ page }) => {
  test.skip(isMobile(page), 'the phone menu has its own test');
  await visit(page, '/about', { title: /About/i, h1: 'About' });
  const nav = page.getByRole('navigation', { name: 'Main' });
  for (const name of ['Tenders', 'Funding', 'Buyers', 'Companies', 'Check my company']) {
    await expect(nav.getByRole('link', { name, exact: true }).first()).toBeVisible();
  }
  await expect(nav.getByRole('button', { name: /What.s new/ })).toBeVisible();
  await expect(page.locator('header').getByRole('searchbox', { name: /Search tenders, funding, buyers and companies/ })).toBeVisible();
  for (const name of ['Pricing', 'Opportunity pack', 'Market', 'Data', 'Network', 'Readiness']) {
    await expect(nav.getByRole('link', { name, exact: true }), `${name} is not in the header`).toHaveCount(0);
  }
  // What's new opens its three pages
  await nav.getByRole('button', { name: /What.s new/ }).click();
  for (const name of ['What changed', 'Weekly digest', 'Deadline calendar']) await expect(page.locator('#sub-new').getByRole('link', { name })).toBeVisible();
  for (const title of ['Companies', 'Check my company', 'What’s new', 'Directory', 'About the data']) {
    await expect(page.locator(`footer nav[aria-label="${title}"]`), title).toHaveCount(1);
  }
});

test('on a phone the menu lists every item, each a target of 44 px, and starts with the search field', async ({ page }) => {
  test.skip(!isMobile(page), 'the phone menu');
  await visit(page, '/', { title: /DefenceGate/, h1: 'Defence and dual-use tenders and funding' });
  await page.getByRole('button', { name: 'Open menu' }).click();
  const menu = page.getByRole('navigation', { name: 'Main menu' });
  await expect(menu.getByRole('searchbox')).toBeFocused();
  const labels = new Set<string>();
  for (const n of MAIN_NAV) { labels.add(n.label); for (const c of n.children ?? []) labels.add(c.label); }
  for (const label of labels) await expect(menu.getByText(label, { exact: true }).first(), label).toBeVisible();
  const heights = await menu.locator('a, button, form div:has(> input)').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height));
  expect(Math.min(...heights), 'smallest target in the menu').toBeGreaterThanOrEqual(43.5);
  await menu.getByRole('link', { name: 'Ukraine partners' }).click();
  await expect(page.locator('h1')).toHaveText('Ukraine partners');
});

test('the search finds the same words in every list and leads to each list, filtered', async ({ page }) => {
  await visit(page, '/search?q=Demo', { title: /Search/, h1: 'Search', text: ['Results for “Demo”'] });
  for (const g of ['Tenders', 'Funding', 'Buyers', 'Companies']) await expect(page.getByRole('heading', { name: g, exact: true })).toBeVisible();
  const companies = page.locator('section[aria-labelledby="group-companies"]');
  await expect(companies.getByRole('heading', { name: 'Won contracts' })).toBeVisible();
  await expect(companies.getByRole('link', { name: /Demo Airframes GmbH/ })).toHaveAttribute('href', '/suppliers/1-demo-airframes-gmbh');
  const all = companies.getByRole('link', { name: /^See all 5 companies that won contracts$/ });
  await expect(all).toHaveAttribute('href', '/suppliers?q=Demo');
  await all.click();
  await expect(page).toHaveURL(/\/suppliers\?q=Demo$/);
  await expect(page.locator('h1')).toHaveText('Companies');
  // nothing found is said per list
  await visit(page, '/search?q=zzzz-nothing', { title: /Search/, h1: 'Search', text: ['No open tenders match.', 'No buyers match.'] });
  // no words: only the form
  await visit(page, '/search', { title: /Search/, h1: 'Search' });
  await expect(page.getByRole('heading', { name: /Results for/ })).toHaveCount(0);
});

test('the header search and the home search open the results page', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Defence and dual-use tenders and funding' });
  const home = page.locator('#main').getByRole('search', { name: 'Site search' });
  await home.getByRole('searchbox').fill('Demo');
  await home.getByRole('button', { name: 'Search' }).click();
  await expect(page).toHaveURL(/\/search\?q=Demo$/);
  await expect(page.getByRole('heading', { name: 'Results for “Demo”' })).toBeVisible();
  if (isMobile(page)) await page.getByRole('button', { name: 'Open menu' }).click();
  // the header's field (in the menu on a phone)
  const header = page.locator(isMobile(page) ? 'form:has(#menu-search)' : 'form:has(#header-search)');
  await header.getByRole('searchbox').fill('Ordnance');
  await header.getByRole('button', { name: 'Search' }).click();
  await expect(page).toHaveURL(/\/search\?q=Ordnance$/);
  await expect(page.getByRole('link', { name: /Demo Ordnance SA/ })).toBeVisible();
});

test('home: one sentence for whom, three tasks and the search before anything else; no "What is in here"', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Defence and dual-use tenders and funding', text: [/^For suppliers, bid teams and advisers/] });
  const start = page.getByRole('navigation', { name: 'Start here' });
  await expect(start.getByRole('link', { name: 'Find a tender' })).toHaveAttribute('href', '/tenders');
  await expect(start.getByRole('link', { name: 'Find funding' })).toHaveAttribute('href', '/funding');
  await expect(start.getByRole('link', { name: 'I make parts or provide services: who buys and who wins?' })).toHaveAttribute('href', '/readiness/supplier');   // WP-97: not the Spain page for every visitor
  await expect(page.getByRole('heading', { name: 'What is in here' })).toHaveCount(0);
  // the tasks and the search are on the first screen, at every width
  const bottom = await page.locator('#home-search').evaluate((el) => el.getBoundingClientRect().bottom);
  expect(bottom).toBeLessThanOrEqual(page.viewportSize()!.height);
  for (const t of await start.getByRole('link').all()) expect((await t.boundingBox())!.height).toBeGreaterThanOrEqual(43.5);
});

test('Check my company asks first what you want and leads to the check that answers it', async ({ page }) => {
  await visit(page, '/check', { title: /Check my company/, h1: 'Check my company', text: ['What do you want?'] });
  await expect(page.getByRole('link', { name: 'Start the supplier profile' })).toHaveAttribute('href', '/readiness/supplier');
  await expect(page.getByRole('link', { name: /I make parts in Spain/ })).toHaveAttribute('href', '/readiness/spain-automotive');
  const main = page.locator('#main');
  await expect(main.getByRole('link', { name: 'Requirements', exact: true })).toHaveAttribute('href', '/requirements');
  await expect(main.getByRole('link', { name: 'Regulatory tracker', exact: true })).toHaveAttribute('href', '/regulation');
  await page.getByRole('link', { name: 'Start the readiness check' }).click();
  await expect(page.locator('h1')).toHaveText('Readiness check');
  // the checks sit under it in the breadcrumbs
  await expect(page.getByRole('navigation', { name: /breadcrumb/i }).getByRole('link', { name: 'Check my company' })).toHaveAttribute('href', '/check');
});

test('the old addresses still answer; /companies opens the Won contracts tab; the sitemap lists the pages, not the redirect', async ({ page, request }) => {
  await visit(page, '/companies', { title: /DefenceGate/, h1: 'Companies' });
  await expect(page).toHaveURL(/\/suppliers$/);
  const tabs = page.getByRole('navigation', { name: 'Companies' });
  await expect(tabs.getByRole('link', { name: 'Won contracts' })).toHaveAttribute('aria-current', 'page');
  await tabs.getByRole('link', { name: 'In EU-funded projects' }).click();
  await expect(page).toHaveURL(/\/organisations$/);
  await expect(page.locator('h1')).toHaveText('Companies');
  await expect(page.getByRole('navigation', { name: 'Companies' }).getByRole('link', { name: 'In EU-funded projects' })).toHaveAttribute('aria-current', 'page');
  for (const path of ['/suppliers?q=Demo', '/organisations?q=alpha', '/networks/ukraine-partners', '/networks/consortium-gaps', '/readiness', '/readiness/supplier',
    '/readiness/spain-automotive', '/market', '/data', '/methodology', '/digest', '/pricing', '/pack', '/alerts', '/glossary', '/cpv']) {
    expect((await request.get(path)).status(), path).toBe(200);
  }
  const sitemap = await (await request.get('/sitemap.xml')).text();
  for (const p of ['/check', '/suppliers', '/organisations', '/readiness']) expect(sitemap, p).toContain(`${p}</loc>`);
  expect(sitemap).not.toContain('/companies</loc>');
  expect(sitemap).not.toContain('/search</loc>');
});
