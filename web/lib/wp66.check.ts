/**
 * Self-check of WP-66 (the demand map): the request carries the CPV codes and the five countries and nothing else of the profile; the words
 * of the counts; and the demo answer (lib/mock/demand.json, the API's answer on production data) keeps the mosaic rule: a winner is named
 * only with at least kMin awards, and named plus aggregated winners are never more than the winners (the demo leaves out one partnership
 * named after its partners, so not all of them).
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buyerLine, demandRequest, directiveShare, otherWinnersLine, type Demand } from './demand';
import { parseProfile } from './profile';
import mock from './mock/demand.json';

const profile = parseProfile(JSON.parse(readFileSync('e2e/fixtures/profile-es-sup-civil.json', 'utf8')));
const req = demandRequest(profile);
// WP-105: the seven countries of the map, and the company's own country (ES), so its own winners are named past the first 30
assert.deepEqual(req, { cpv: ['34300000', '34100000', '35421000', '42600000', '44300000'], countries: ['ES', 'DE', 'FR', 'PL', 'NL', 'PT', 'IT'], home: 'ES' });
assert.deepEqual(Object.keys(req ?? {}), ['cpv', 'countries', 'home'], 'nothing else of the profile is sent');
assert.deepEqual(Object.keys(demandRequest({ ...profile, country: 'BE' }) ?? {}), ['cpv', 'countries'], 'a country outside the map is not sent');
assert.equal(demandRequest({ ...profile, supplier: { ...profile.supplier, cpv: [] } }), null, 'no codes, no request');
assert.equal(demandRequest({ ...profile, supplier: { ...profile.supplier, cpv: ['34300000', 'x', '343'] } })?.cpv.length, 1);

assert.equal(directiveShare({ directive: 0, procurements: 0 }), 'none');
assert.equal(directiveShare({ directive: 33, procurements: 1515 }), '33 of 1515 (2 %)');
assert.equal(buyerLine({ coreBuyers: 1, otherBuyers: 0 }), '1 core defence buyer and 0 other defence-scope buyers');

const demo: Demand = mock;
assert.deepEqual(demo.countries, ['ES', 'DE', 'FR', 'PL', 'NL']);
for (const c of demo.byCountry) {
  assert.ok(c.topWinners.every((w) => w.awards >= demo.kMin), `${c.country}: a winner below kMin is named`);
  assert.ok(c.topWinners.length + c.otherWinners.winners <= c.winners, `${c.country}: named and aggregated winners exceed the winners`);
  assert.ok(c.topBuyers.length <= c.coreBuyers + c.otherBuyers, `${c.country}: more buyers listed than counted`);
  assert.ok(c.directive <= c.procurements && c.awarded <= c.procurements, c.country);
  if (c.otherWinners.winners) assert.match(otherWinnersLine(c, demo.kMin) ?? '', /not named: a winner is named only with at least 3 awards/);
}
assert.match(demo.coverage, /not the sub-tier needs of prime contractors/);
console.log('wp66 ok');
