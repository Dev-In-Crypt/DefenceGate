/**
 * Self-check of WP-139 (verification round 8, 25 October 2026): a title cut ends on a word that carries meaning, not on one that
 * leads into the next; the supplier description counts "1 contract"; robots.txt keeps crawlers out of every address with a query
 * string and leaves the plain pages open; /regulation's description is whole. Not part of the app. Run from web/:
 * node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { TITLE_MAX, trimAtPhrase, trimAtWord } from './seo-trim';
import { tenderTitle } from './seo';
import { plural } from './format';

// ---------------------------------------------------------------- 1. cuts at a phrase's end

const tornado = 'Suministro de repuestos consumibles para preparación de alistamiento del BAM Tornado';
assert.equal(tenderTitle({ title: tornado, noticeId: '2026/123', country: 'ES', cpv: null, buyerName: 'Intendente de las Palmas' }),
  'Suministro de repuestos consumibles…');
const cea = 'Commissariat a L Energie Atomique et Aux Energies Alternatives';
assert.equal(trimAtPhrase(cea, TITLE_MAX, 12), 'Commissariat a L Energie Atomique…');
assert.equal(trimAtWord('Repair, maintenance and associated services related to aircraft and other equipment', TITLE_MAX),
  'Repair, maintenance and associated services…', 'a cut that ends on a word of meaning is unchanged');
assert.equal(trimAtWord('Framework agreement for the supply of', 30), 'Framework agreement…');
assert.equal(trimAtWord('de de de de de de de de de', 10), 'de…', 'the first word always stays');
for (const t of [tornado, cea, 'Dostawa części zamiennych do pojazdów i sprzętu wojskowego oraz ich naprawa w roku 2026']) {
  const cut = trimAtPhrase(t, TITLE_MAX, 12);
  assert.ok(cut.length <= TITLE_MAX, cut);
  assert.ok(!/\s(?:de|para|et|aux|and|of|for|the|i|w|do|oraz|L)…$/i.test(cut), cut);
}

// ---------------------------------------------------------------- 2. one contract

const supplier = readFileSync('app/(public)/suppliers/[slug]/page.tsx', 'utf8');
assert.match(supplier, /defence-relevant \$\{plural\(s\.noticeCount, 'contract'\)\}/);
assert.equal(`1 defence-relevant ${plural(1, 'contract')}`, '1 defence-relevant contract');
assert.equal(`2 defence-relevant ${plural(2, 'contract')}`, '2 defence-relevant contracts');

// ---------------------------------------------------------------- 3. robots.txt

const robots = readFileSync('app/robots.ts', 'utf8');
assert.match(robots, /disallow: \['\/\*\?'/, 'every address with a query string');
assert.match(robots, /allow: \['\/', '\/_next\/'\]/, 'the plain pages and the scripts they need');

// ---------------------------------------------------------------- 4. /regulation's description

const regulation = /description: '([^']+)'/.exec(readFileSync('app/(public)/regulation/page.tsx', 'utf8'))?.[1] ?? '';
assert.ok(regulation.length >= 110 && regulation.length <= 160, `${regulation.length}: ${regulation}`);

console.log('wp139 checks passed');
