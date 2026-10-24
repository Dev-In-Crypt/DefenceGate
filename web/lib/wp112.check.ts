/**
 * Self-check of WP-112 (persona round 4 of 24 October 2026: supplier report, supplier pages, market).
 *   1. the readiness calls: "Too many requests" waited out while the patience lasts, and one request per answer shared by the pages
 *   2. who to approach: a winner matched by an additional code only listed apart, the source line once per group, buyer links with the codes
 *   3. the sums account for every contract and say that ceilings are not added (Leonardo, Seko Benelux)
 *   4. the coverage line from the sources counted (Poland: three), the CPV group titles of the full vocabulary
 *   5. the supplier file's company number, the country filter by name, the requirements of another country's route
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { PATIENCE_SECONDS, fetchPatiently, shared } from './answer-cache';
import { approachGroups, buyerHref, firstOfGroup, type Approach, type ApproachWinner } from './demand';
import { countedLine } from './coverage-copy';
import { cpvGroupName } from './cpv';
import { SUPPLIER_CONTRACT_HEADER, supplierContractRows } from './export-tables';
import { appearsLine } from './readiness';
import { countryOrder } from './taxonomy';
import { listValueLine, restNote, totalLine } from './value-totals';
import type { SupplierContracts } from './types';

const winner = (name: string, extra: Partial<ApproachWinner> = {}): ApproachWinner => ({
  name, country: 'ES', contracts: 1, slug: `1-${name}`, values: { byCurrency: [], of: 1, withoutValue: 1, shared: 0 }, buyers: [],
  countries: ['ES'], lastAward: null, prime: null, edfProjects: 0, defenceBuyer: false, ...extra,
});
const prime = (group: string) => ({ group, jointVenture: false, source: 's', sourceUrl: 'https://example.org/' });

void (async () => {
  // ---------------------------------------------------------------- 1. the readiness calls
  const answers = (statuses: number[]) => {
    let i = 0;
    return async () => new Response('{}', { status: statuses[Math.min(i++, statuses.length - 1)], headers: { 'retry-after': '2' } });
  };
  let now = 0;
  const clock = () => now;
  const wait = async (ms: number) => { now += ms; };
  // two refusals in a row (other requests from the same address took the tokens first) are waited out, not shown
  const ok = await fetchPatiently('/api/readiness/demand', {}, wait, answers([429, 429, 200]), clock);
  assert.equal(ok.status, 200);
  assert.equal(now, 4000);
  // the patience is counted in time, the requests' own time included: past it, the refusal is shown
  now = 0;
  const slow = async () => { now += 9000; return new Response('{}', { status: 429, headers: { 'retry-after': '2' } }); };
  const gaveUp = await fetchPatiently('/x', {}, wait, slow, clock);
  assert.equal(gaveUp.status, 429);
  assert.ok(now <= (PATIENCE_SECONDS + 9) * 1000, `${now}`);
  // one request per answer: the results page's request is the report's, and it is not aborted with the page
  let runs = 0;
  const one = () => new Promise<number>((r) => { runs += 1; setTimeout(() => r(42), 5); });
  const [a, b] = await Promise.all([shared('demand', 'k1', one, null), shared('demand', 'k1', one, null)]);
  assert.deepEqual([a, b, runs], [42, 42, 1]);
  await shared('demand', 'k1', one, null);
  assert.equal(runs, 2, 'a finished request is not kept here (the tab store keeps the answer)');
  await assert.rejects(shared('demand', 'k2', () => Promise.reject(new Error('x')), null));
  assert.equal(await shared('demand', 'k2', async () => 7, null), 7, 'a failed request is forgotten, a retry asks again');

  // ---------------------------------------------------------------- 2. who to approach
  const ap: Approach = {
    winners: [winner('Talleres'), winner('Indra Sistemas', { prime: prime('Indra') }), winner('Indra Soluciones', { prime: prime('Indra') }),
      winner('Tubos y Juntas', { byOtherCodeOnly: true }), winner('URO', { prime: prime('URO'), byOtherCodeOnly: true })],
    below: { winners: 0, awards: 0 }, more: { winners: 0, awards: 0 },
  };
  const g = approachGroups(ap, 'ES');
  assert.deepEqual(g.primes.map((w) => w.name), ['Indra Sistemas', 'Indra Soluciones'], 'a prime matched by another code is no way in');
  assert.deepEqual(g.side.map((w) => w.name), ['Tubos y Juntas', 'URO']);
  assert.deepEqual(g.home.map((w) => w.name), ['Talleres']);
  assert.deepEqual(g.primes.map((_, i) => firstOfGroup(g.primes, i)), [true, false], 'p06: the Indra line once, not five times');
  assert.equal(buyerHref('62149-estado-maior-do-exercito', ['35811000', '18100000', '3511']),
    '/buyers/62149-estado-maior-do-exercito?cpv=35811%2C181%2C3511');
  assert.equal(buyerHref('1-x'), '/buyers/1-x');

  // ---------------------------------------------------------------- 3. the sums
  // p07, Leonardo S.p.A.: 10 EUR + 2 SEK contract values, 2 framework ceilings, 4 without a value: 18
  const leo = totalLine({
    byCurrency: [{ currency: 'EUR', amount: 1e7, count: 10, lotEstimates: 0 }, { currency: 'SEK', amount: 5e6, count: 2, lotEstimates: 0 }],
    frameworks: [{ currency: 'BGN', amount: 54e6, count: 2, lotEstimates: 0 }], estimates: [], of: 18, withoutValue: 4, shared: 0,
  }, 'contract');
  assert.equal(leo, 'EUR 10,000,000 over 10 contracts; SEK 5,000,000 over 2 contracts; of the 18 contracts, 2 with a framework ceiling only, '
    + '4 with no value for this company alone (ceilings, estimates and unit prices are not added)');
  // p06, Seko Benelux in the report: one contract value and two framework ceilings of three
  assert.match(totalLine({ byCurrency: [{ currency: 'EUR', amount: 15867768, count: 1, lotEstimates: 0 }],
    frameworks: [{ currency: 'EUR', amount: 29.4e6, count: 2, lotEstimates: 0 }], of: 3, withoutValue: 0, shared: 0 }, 'contract'),
  /^EUR 15,867,768 over 1 contract; of the 3 contracts, 2 with a framework ceiling only \(/);
  assert.equal(restNote(2, 3), '; 1 more with a framework ceiling, an estimate or no value of their own (not added)');
  assert.equal(restNote(3, 3), '');
  assert.ok(listValueLine([{ currency: 'EUR', amount: 15867768, count: 1, lotEstimates: 0 }], 3).endsWith('2 more with a framework ceiling, an estimate or no value of their own (not added)'));

  // ---------------------------------------------------------------- 4. coverage and group titles
  assert.equal(countedLine('PL', ['pl_ezam', 'ted', 'pl_atlas']),
    'Poland: TED + e-Zamówienia + Atlas Przetargów (a one-off load of its archive of past notices)');
  assert.equal(countedLine('NL', ['ted', 'nl_tenderned']), 'Netherlands: TED + TenderNed; in practice chiefly one buyer, the Ministry of Defence');
  assert.equal(countedLine('IT', ['ted', 'fr_boamp']), 'Italy: TED only; the national portal is not collected', 'another country\'s source is not counted');
  assert.equal(cpvGroupName('374'), 'Sports goods and equipment');
  assert.equal(cpvGroupName('246'), 'Explosives');

  // ---------------------------------------------------------------- 5. file, filter, requirements
  const file: SupplierContracts = { slug: '1-leonardo', name: 'Leonardo S.p.A.', total: 1, cap: 5000, identifiers: ['IT00881841001'], items: [{
    noticeId: '1-2026', slug: '1-x', title: 'X', buyerName: null, buyerCountry: 'IT', publishedAt: null, cpv: null, winnersInNotice: 1,
    valueAmount: null, valueCurrency: null, valueKind: null, inContractSum: false, frameworkNoticeId: null, source: 'ted',
    sourceName: 'TED', sourceUrl: null, licence: '', attribution: '' }] };
  const [row] = supplierContractRows(file, (p) => p);
  assert.equal(row[SUPPLIER_CONTRACT_HEADER.indexOf('supplier')], 'Leonardo S.p.A.');
  assert.equal(row[SUPPLIER_CONTRACT_HEADER.indexOf('company_number')], 'IT00881841001');
  const order = countryOrder();
  assert.ok(order.indexOf('PT') < order.indexOf('RO') && order[0] === 'AT', 'p02: by name, Portugal not below the others by count');
  assert.deepEqual(countryOrder(['PT']).slice(0, 2), ['PT', 'AT']);
  assert.equal(appearsLine(['ES-MOD'], 'DE', 'Germany'),
    'No rule we hold for Germany names it; we hold it from the rules of Spanish defence supplier (MoD) only. ');
  assert.equal(appearsLine(['ES-MOD', 'NATO-SUPPLY'], 'DE', 'Germany'), 'Appears in the rules of NATO and NSPA supply. ');
  assert.equal(appearsLine(['ES-MOD'], 'ES', 'Spain'), 'Appears in the rules of Spanish defence supplier (MoD). ');
  assert.equal(appearsLine(['ES-MOD']), 'Appears in the rules of Spanish defence supplier (MoD). ');
  console.log('wp112 checks passed');
})();
