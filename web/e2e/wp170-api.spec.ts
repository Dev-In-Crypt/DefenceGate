import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-170: the two pages of the intermittent React #418 (backlog: /tenders?status=planned, 1 in 4 runs of wp52b-api; and
 * /suppliers/<slug>/competitors, wp155-api) hydrate load after load, each in a fresh page, as a visitor gets them: the document in
 * one piece (`wholeDocuments` in helpers.ts; Caddy's buffer on the site). `visit` fails on any console or page error. Run it with
 * --repeat-each to repeat. The race itself needs a document that trickles (lab: 5 to 10 % of sliced loads, 0 whole).
 */
const PAGES = [
  { path: '/tenders?status=planned', want: { title: /tenders/i, h1: 'Tenders' } },
  { path: '/suppliers/155001-fake-prime-sa/competitors', want: { title: /Competitors/, h1: 'Competitors of Fake Prime SA' } },
];
const LOADS = 6;

for (const { path, want } of PAGES) {
  test(`${path} hydrates without React error #418, load after load`, { tag: '@fake-api' }, async ({ browser }) => {
    for (let i = 0; i < LOADS; i++) {
      const context = await browser.newContext({ viewport: test.info().project.use.viewport ?? undefined, baseURL: test.info().project.use.baseURL });
      const page = await context.newPage();
      await visit(page, path, want);
      await expect(page.locator('#results-heading, h1').first()).toBeVisible();
      await context.close();
    }
  });
}
