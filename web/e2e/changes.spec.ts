import { expect, test } from '@playwright/test';
import { openAbout, pace, visit } from './helpers';

test('/changes: the window, the filters and the feed link', async ({ page }) => {
  await visit(page, '/changes', {
    title: /what changed/i,
    h1: 'What changed',
    text: [/The last 14 days/, 'Atom feed of this list'],
  });
  // Honest about the archive's age and about our own corrections.
  // WP-88: the method is in the collapsed How we count (owner-approved copy change)
  await openAbout(page);
  await expect(page.getByText(/began in September 2026/i)).toBeVisible();
  await expect(page.getByRole('search', { name: /filter changes/i })).toBeVisible();
  await expect(page.locator('link[rel="alternate"][type="application/atom+xml"]')).toHaveCount(1);
});

test('/changes with a country filter', async ({ page }) => {
  await visit(page, '/changes?country=PL', { title: /what changed/i, h1: 'What changed' });
  await expect(page.getByLabel('Buyer country')).toHaveValue('PL');
});

test('/changes.atom is a valid Atom 1.0 feed and answers conditional requests', async ({ page, request }) => {
  test.skip(test.info().project.name !== 'desktop', 'one run is enough: the feed does not depend on the viewport');
  const response = await request.get('/changes.atom');
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('application/atom+xml');
  const etag = response.headers()['etag'];
  expect(etag).toBeTruthy();
  expect(response.headers()['last-modified']).toBeTruthy();
  const body = await response.text();

  // The browser's own XML parser is the validator: a well-formed document with the Atom elements RFC 4287 requires.
  await page.goto('/changes');
  const verdict = await page.evaluate((xml) => {
    const ATOM = 'http://www.w3.org/2005/Atom';
    const doc = new DOMParser().parseFromString(xml, 'application/xml');
    const problems: string[] = [];
    if (doc.getElementsByTagName('parsererror').length) return ['not well-formed XML'];
    const feed = doc.documentElement;
    if (feed.localName !== 'feed' || feed.namespaceURI !== ATOM) problems.push('root is not an Atom feed');
    const kid = (el: Element, name: string) => Array.from(el.children).filter((c) => c.localName === name && c.namespaceURI === ATOM);
    const RFC3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;
    for (const name of ['id', 'title', 'updated']) if (kid(feed, name).length !== 1) problems.push(`feed needs exactly one ${name}`);
    const updated = kid(feed, 'updated')[0]?.textContent ?? '';
    if (!RFC3339.test(updated)) problems.push(`feed updated is not RFC 3339: ${updated}`);
    const self = kid(feed, 'link').filter((l) => l.getAttribute('rel') === 'self');
    if (self.length !== 1) problems.push('feed needs one link rel=self');
    if (kid(feed, 'author').length === 0) problems.push('feed needs an author (its entries carry none)');
    const ids = new Set<string>();
    for (const entry of kid(feed, 'entry')) {
      const id = kid(entry, 'id')[0]?.textContent ?? '';
      if (!id || ids.has(id)) problems.push(`entry id missing or repeated: ${id}`);
      ids.add(id);
      if (kid(entry, 'title').length !== 1) problems.push(`entry ${id}: needs one title`);
      if (!RFC3339.test(kid(entry, 'updated')[0]?.textContent ?? '')) problems.push(`entry ${id}: updated is not RFC 3339`);
      // A notice links to its tender page, a funding call (categories call-new, call-amended) to its call page.
      if (!kid(entry, 'link').some((l) => l.getAttribute('rel') === 'alternate' && /\/(tenders|funding)\//.test(l.getAttribute('href') ?? ''))) {
        problems.push(`entry ${id}: needs an alternate link to the tender or the call`);
      }
    }
    if (/@[A-Za-z0-9-]+\.[A-Za-z]{2,}/.test(xml)) problems.push('an e-mail address is in the feed');
    return problems;
  }, body);
  expect(verdict).toEqual([]);

  const again = await request.get('/changes.atom', { headers: { 'if-none-match': etag } });
  expect(again.status()).toBe(304);
  await pace(page);
});
