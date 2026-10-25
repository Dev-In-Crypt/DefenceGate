import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-130 (round-7 accessibility and SEO audit, 25 October 2026, docs/verification/round6/wp130-selfcheck.md). Evidence:
 * D:/DEFENCEGATE TESTS/verify-oct25/r7-a11y-seo/problems.csv, axe.json, seo.json. The TED title shapes ("France-Toulon: ...") are
 * covered by lib/wp130.check.ts; this spec checks the pages.
 */

const isMobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 700;
const squash = (s: string) => s.replace(/\s+/g, ' ').trim();
const SUFFIX = ' · DefenceGate';

async function ldOf(page: Page, type: string): Promise<Record<string, any>[]> {
  const blocks = await page.locator('script[type="application/ld+json"]').evaluateAll((s) => s.map((n) => JSON.parse(n.textContent ?? '{}')));
  return blocks.filter((b) => b['@type'] === type);
}

test('1: tender page titles are unique and say what is bought, with the notice number where both fit', async ({ page, request }) => {
  const xml = await (await request.get('/sitemaps/tenders-0.xml')).text();
  const slugs = [...xml.matchAll(/<loc>[^<]*\/tenders\/([^<]+)<\/loc>/g)].map((m) => m[1]).slice(0, 8);
  expect(slugs.length).toBeGreaterThanOrEqual(5);
  const titles: string[] = [];
  for (const slug of slugs) {
    await page.goto(`/tenders/${slug}`);
    const title = await page.title();
    const h1 = squash(await page.locator('#main h1').first().innerText());
    expect(title.endsWith(SUFFIX), title).toBe(true);
    expect(title.length, title).toBeLessThanOrEqual(60);
    const m = /^(.+?)(?: \(([^()]+)\))?$/.exec(title.slice(0, -SUFFIX.length))!;
    const subject = m[1].replace(/…$/, '');
    // the subject is what the page's heading says (cut at a word or a phrase end, never mid-word); the notice number follows it when
    // both fit, else the subject was the longer one
    expect(h1.startsWith(subject), `${title} / ${h1}`).toBe(true);
    if (m[2]) await expect(page.locator('#main')).toContainText(m[2]);
    else expect(h1.length + ' (123456-2026)'.length, `${title}: no number although it fitted`).toBeGreaterThan(60 - SUFFIX.length);
    titles.push(title);
  }
  expect(new Set(titles).size, titles.join(' | ')).toBe(titles.length);
});

test('1: descriptions of the detail pages are not cut inside a word; the supplier profile says more than its first clause', async ({ page }) => {
  for (const path of ['/readiness/supplier', '/tenders/2-workshop-consumables-supply', '/requirements/ncage']) {
    await page.goto(path);
    const d = (await page.locator('meta[name="description"]').getAttribute('content')) ?? '';
    expect(d.length, `${path}: ${d}`).toBeLessThanOrEqual(160);
    expect(d, path).toMatch(/[.…]$/);
  }
  await page.goto('/readiness/supplier');
  expect(((await page.locator('meta[name="description"]').getAttribute('content')) ?? '').length).toBeGreaterThan(110);
});

test('2: each homepage tile link is named by all the words it shows (WCAG 2.5.3 Label in Name)', async ({ page }) => {
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  const links = page.locator('a[data-tile], [data-tile-action]');
  await expect(links).toHaveCount(4);
  for (const link of await links.all()) {
    const shown = squash(await link.innerText());
    const escaped = shown.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    await expect(link, shown).toHaveAccessibleName(new RegExp(escaped));
  }
  await expect(page.getByRole('link', { name: /Find partners.*Find partners/ })).toHaveAttribute('href', '/organisations');
  await expect(page.getByRole('link', { name: /Start the check/ })).toHaveAttribute('href', '/check');
  // the tile is a card: its hover shows on its edge, never as an underline (card hover rule)
  if (!isMobile(page)) {
    const tile = page.locator('a[data-tile]').first();
    await tile.hover();
    expect(await tile.evaluate((a) => [a, ...a.querySelectorAll('*')].every((e) => !getComputedStyle(e).textDecorationLine.includes('underline')))).toBe(true);
  }
});

test('3: the footer link to the last collection run is underlined in both themes', async ({ page }) => {
  for (const scheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto('/about');
    const link = page.locator('footer').getByRole('link', { name: 'Last collection run (any source)' });
    await expect(link).toBeVisible();
    expect(await link.evaluate((a) => getComputedStyle(a).textDecorationLine), scheme).toContain('underline');
  }
});

test('4: on /search the search landmarks have names of their own', async ({ page }) => {
  await visit(page, '/search?q=radar', { title: /Search/, h1: 'Search' });
  const names = await page.getByRole('search').evaluateAll((els) => els.filter((e) => (e as HTMLElement).offsetParent !== null).map((e) => e.getAttribute('aria-label')));
  expect(names.length).toBeGreaterThanOrEqual(1);
  expect(new Set(names).size, names.join(' | ')).toBe(names.length);
  await expect(page.locator('#main').getByRole('search', { name: 'Site search', exact: true })).toBeVisible();
});

test('5: every filter checkbox and radio of /tenders has a free 24 x 24 px target (WCAG 2.5.8)', async ({ page }) => {
  test.skip(isMobile(page), 'the filters are folded on a phone; the overlap was measured at 1440 px');
  await page.setViewportSize({ width: 1440, height: 900 });
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  const problems = await page.getByRole('search', { name: 'Filter tenders' }).evaluate((form) => {
    const out: string[] = [];
    // only what is shown: a control inside a closed <details> ("Show all 31 countries") keeps a box but is not drawn
    const shown = (e: Element) => e.checkVisibility({ visibilityProperty: true });
    const others = [...document.querySelectorAll<HTMLElement>('a, button, input, select, textarea, summary')].filter(shown);
    for (const input of form.querySelectorAll<HTMLInputElement>('input[type=checkbox], input[type=radio]')) {
      if (!shown(input)) continue;
      const r = input.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      const label = `${input.name}=${input.value}`;
      if (r.width < 24 || r.height < 24) out.push(`${label}: ${r.width}x${r.height}`);
      for (const o of others) {
        if (o === input || o.contains(input) || input.closest('label')?.contains(o)) continue;
        for (const b of o.getClientRects()) {
          const w = Math.min(r.right, b.right) - Math.max(r.left, b.left);
          const h = Math.min(r.bottom, b.bottom) - Math.max(r.top, b.top);
          if (w > 0.5 && h > 0.5) out.push(`${label}: covered by ${o.tagName} "${(o.textContent ?? '').trim().slice(0, 30)}" (${w.toFixed(1)} x ${h.toFixed(1)})`);
        }
      }
    }
    return out;
  });
  expect(problems).toEqual([]);
});

test('6: breadcrumbs, shown and in the structured data, name each address once and no menu group as a page', async ({ page }) => {
  await page.goto('/suppliers');
  const supplier = await page.locator('#main a[href^="/suppliers/"]').first().getAttribute('href');
  for (const path of ['/suppliers', supplier!, '/organisations', '/networks/consortium-gaps', '/networks/ukraine-partners']) {
    await page.goto(path);
    const [list] = await ldOf(page, 'BreadcrumbList');
    const items: string[] = list.itemListElement.map((i: { item: string }) => new URL(i.item).pathname);
    expect(new Set(items).size, `${path}: ${items.join(' > ')}`).toBe(items.length);
    expect(list.itemListElement.map((i: { name: string }) => i.name), path).not.toContain('Partners');
    list.itemListElement.forEach((i: { position: number }, n: number) => expect(i.position).toBe(n + 1));
    const hrefs = await page.getByRole('navigation', { name: 'Breadcrumb' }).getByRole('link').evaluateAll((as) => as.map((a) => a.getAttribute('href')));
    expect(new Set(hrefs).size, `${path}: ${hrefs.join(' ')}`).toBe(hrefs.length);
  }
  // the menu's words stay (WP-121): Partners is shown, as text
  await page.goto('/networks/consortium-gaps');
  const crumbs = page.getByRole('navigation', { name: 'Breadcrumb' });
  await expect(crumbs.getByText('Partners', { exact: true })).toBeVisible();
  await expect(crumbs.getByRole('link', { name: 'Partners' })).toHaveCount(0);
});

test('7: an organisation description puts its years in a sentence; requirement articles name their author and publisher with its logo', async ({ page }) => {
  await page.goto('/organisations');
  await page.goto((await page.locator('#main a[href^="/organisations/"]').first().getAttribute('href'))!);
  expect((await page.locator('meta[name="description"]').getAttribute('content')) ?? '').not.toMatch(/between \d{4} to/);
  // 9.
  await page.goto('/requirements/ncage');
  const [article] = await ldOf(page, 'Article');
  for (const who of [article.author, article.publisher]) {
    expect(who).toMatchObject({ '@type': 'Organization', name: 'DefenceGate' });
    expect(who.logo.url).toMatch(/\/brand\/app-icon\.svg$/);
  }
});

test('8: fixed pages carry no lastmod in the sitemap; records keep theirs', async ({ request }) => {
  const xml = await (await request.get('/sitemaps/pages.xml')).text();
  const urls = [...xml.matchAll(/<url>(.*?)<\/url>/g)].map((m) => m[1]);
  const entry = (path: string) => urls.find((u) => new RegExp(`<loc>[^<]*${path.replace(/[/.]/g, '\\$&')}</loc>`).test(u));
  for (const path of ['/', '/about', '/glossary', '/methodology', '/tenders', '/check', '/requirements']) {
    expect(entry(path), path).toBeTruthy();
    expect(entry(path), path).not.toContain('<lastmod>');
  }
  const records = urls.filter((u) => /\/(funding|digest)\/[^<]+<\/loc>/.test(u));
  expect(records.length).toBeGreaterThan(0);
  for (const r of records) expect(r).toContain('<lastmod>');
});
