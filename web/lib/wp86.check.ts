/**
 * Self-check of the WP-86 menu (lib/nav.ts). Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 * The labels against the pages' h1 are checked in a browser (e2e/wp86.spec.ts); here the structure.
 */
import assert from 'node:assert/strict';
import { FOOTER_GROUPS, LEGAL_LINKS, MAIN_NAV } from './nav';

// The owner-approved menu, in this order.
assert.deepEqual(MAIN_NAV.map((n) => n.label), ['Tenders', 'Funding', 'Buyers', 'Companies', 'Check my company', 'What’s new']);
// Market sits inside Tenders; pricing and the pack are not in the header.
assert.ok(MAIN_NAV.find((n) => n.key === 'tenders')!.children!.some((c) => c.href === '/market'));
const headerHrefs = MAIN_NAV.flatMap((n) => [n.href, ...(n.children ?? []).map((c) => c.href)]).filter((h): h is string => Boolean(h));
for (const h of ['/pricing', '/pack', '/alerts', '/data', '/organisations', '/suppliers']) assert.ok(!headerHrefs.includes(h), `${h} is not in the header`);
// Check my company holds Requirements and the tracker; What's new its three pages and no page of its own.
assert.deepEqual(MAIN_NAV.find((n) => n.key === 'check')!.children!.map((c) => c.href), ['/check', '/requirements', '/regulation']);
const news = MAIN_NAV.find((n) => n.key === 'new')!;
assert.equal(news.href, undefined);
assert.deepEqual(news.children!.map((c) => c.href), ['/changes', '/digest', '/calendar']);
// Every header link is in the footer under the same label; the footer's own group "About the data" has the five pages.
const footer = FOOTER_GROUPS.flatMap((g) => g.links);
for (const n of MAIN_NAV) for (const l of [...(n.href ? [{ label: n.label, href: n.href }] : []), ...(n.children ?? [])]) {
  assert.ok(footer.some((f) => f.href === l.href && f.label === l.label), `footer has ${l.label}`);
}
assert.deepEqual(FOOTER_GROUPS.find((g) => g.title === 'About the data')!.links.map((l) => l.href), ['/data', '/methodology', '/data/sovereignty', '/glossary', '/cpv']);
assert.deepEqual(LEGAL_LINKS.map((l) => l.href), ['/privacy', '/terms', '/imprint']);
// One address, one label, everywhere.
const label = new Map<string, string>();
for (const l of [...footer, ...LEGAL_LINKS]) {
  assert.ok(!label.has(l.href) || label.get(l.href) === l.label, `${l.href} has one label`);
  label.set(l.href, l.label);
}
console.log('wp86 nav: ok');
