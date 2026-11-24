/**
 * Self-check of WP-176 (QA of 24 November 2026: closed pages and site-wide UX). Not part of the app and not imported by it.
 * Run from web/:  npm run check
 */
import assert from 'node:assert/strict';
import { PLANS_FROM } from './plans';
import { PLANS, ON_REQUEST } from './pricing';
import { FOOTER_GROUPS, MAIN_NAV, MORE_NAV } from './nav';
import { L, SR_CRUMBS } from './sell-report';

// E-27: a gate names every plan that has the feature, Founding customer (Pro) included
assert.equal(PLANS_FROM.pro, 'Pro, Team, Consultant and Founding customer plans');
assert.equal(PLANS_FROM.team, 'Team and Consultant plans');

// E-02: each paid plan names the self-serve "Who to sell to" report; the one-off report says it is prepared by us
const text = (id: string) => PLANS.find((p) => p.id === id)!.features.map((f) => f.text).join(' | ');
for (const id of ['pro', 'team', 'consultant']) assert.match(text(id), /“Who to sell to”/, id);
assert.match(ON_REQUEST.find((o) => o.name === '“Who to approach” report')!.features[0].text, /^Prepared by us/);

// A-15: the phone menu ends with the footer-only pages, under the same labels as the footer (each the h1 of its page)
const footer = new Map(FOOTER_GROUPS.flatMap((g) => g.links.map((l) => [l.href, l.label] as const)));
for (const c of MORE_NAV.children!) assert.equal(footer.get(c.href), c.label, c.href);
assert.deepEqual(MORE_NAV.children!.map((c) => c.href), ['/about', '/pricing', '/methodology', '/data', '/glossary']);
assert.equal(MAIN_NAV.length, 4, 'the desktop bar keeps its four items');

// E-33: one buyer, one procurement
assert.equal(L.countryLine(1, 1, 0), '1 procurement · 1 buyer, not a defence buyer');
assert.equal(L.countryLine(6, 1, 1), '6 procurements · 1 buyer, a defence buyer');
assert.equal(L.countryLine(16, 3, 1), '16 procurements · 3 buyers, 1 of them defence buyers');

// E-39: the report's breadcrumb starts at Home and names the report
assert.deepEqual(SR_CRUMBS.map((c) => c.label), ['Home', 'Who to sell to']);

console.log('wp176 ok');
