/**
 * Self-check of the WP-49 helpers: the currency filter on its own, the query a live filter form produces and how two are
 * compared. Not part of the app and not imported by it.
 * Run from web/:  npm run check   (every lib/*.check.ts), or
 *   npx tsc lib/wp49.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop --resolveJsonModule && node /tmp/dgchk/wp49.check.js
 */
import assert from 'node:assert/strict';
import { canonQuery, queryFromEntries } from './filter-query';
import { activeFilterCount, activeTenderFilterCount, describeCallFilters, parseCallFilters, parseTenderFilters, toQuery, toTenderQuery } from './filters';
import * as callMock from './mock/calls';
import * as tenderMock from './mock/tenders';

// ---- The currency alone is a filter, and EUR is a choice like any other (it used to be dropped from the address).
assert.equal(parseTenderFilters({}).currency, undefined, 'no currency in the address: no filter');
assert.equal(parseTenderFilters({ currency: 'pln' }).currency, 'PLN');
assert.equal(parseTenderFilters({ currency: 'EURO' }).currency, undefined, 'not a code: ignored');
assert.equal(toTenderQuery(parseTenderFilters({ currency: 'EUR' })), '?currency=EUR');
assert.equal(toTenderQuery(parseTenderFilters({ currency: 'pln', min: '100000' })), '?min=100000&currency=PLN');
assert.equal(toTenderQuery(parseTenderFilters({})), '', 'the default list stays the cacheable one');
assert.equal(activeTenderFilterCount(parseTenderFilters({})), 0);
assert.equal(activeTenderFilterCount(parseTenderFilters({ currency: 'PLN' })), 1, 'a currency alone counts as an active filter');
assert.equal(activeTenderFilterCount(parseTenderFilters({ currency: 'PLN', min: '5' })), 2);

assert.equal(parseCallFilters({}).currency, undefined);
assert.equal(toQuery(parseCallFilters({ currency: 'sek' })), '?currency=SEK');
assert.equal(toQuery(parseCallFilters({ currency: 'EUR' })), '?currency=EUR');
assert.equal(activeFilterCount(parseCallFilters({})), 0);
assert.equal(activeFilterCount(parseCallFilters({ currency: 'SEK' })), 1);
assert.ok(describeCallFilters(parseCallFilters({ currency: 'SEK' })).includes('a budget stated in SEK'));
assert.ok(describeCallFilters(parseCallFilters({ currency: 'SEK', min: '5' })).some((s) => s.startsWith('budget 5 to ∞ SEK')));

// ---- The demo data answers the way the API does.
const stated = (t: { estimatedValue: { amount: number; currency: string } | null }, cur: string) =>
  t.estimatedValue !== null && t.estimatedValue.amount > 1 && t.estimatedValue.currency === cur;
const everyTender = tenderMock.queryTenders({ status: 'all', scope: 'all', pageSize: 100000 }).items;
for (const cur of ['EUR', 'PLN']) {
  const got = tenderMock.queryTenders({ status: 'all', scope: 'all', currency: cur, pageSize: 100000 }).items;
  assert.deepEqual(got.map((t) => t.id).sort(), everyTender.filter((t) => stated(t, cur)).map((t) => t.id).sort(), `tenders in ${cur}`);
}
assert.ok(tenderMock.queryTenders({ status: 'all', scope: 'all', currency: 'EUR', pageSize: 100000 }).total < everyTender.length,
  'EUR alone leaves out the notices with no value in EUR');
const everyCall = callMock.queryCalls({ status: 'all', pageSize: 100000 }).items;
const sek = callMock.queryCalls({ status: 'all', currency: 'SEK', pageSize: 100000 }).items;
assert.deepEqual(sek.map((c) => c.id).sort(), everyCall.filter((c) => c.budget?.currency === 'SEK').map((c) => c.id).sort());
assert.ok(sek.length < everyCall.length);

// A call with no budget carries the reason in the demo data too (the API's `budgetNote`).
const noBudget = everyCall.filter((c) => c.budget === null);
assert.ok(noBudget.length > 0 && noBudget.every((c) => c.budgetNote && c.budgetNote.short.length > 0));
assert.ok(everyCall.filter((c) => c.budget !== null).every((c) => !c.budgetNote));

// ---- The query of a live form: defaults and empties out, repeats joined, the page dropped.
assert.equal(queryFromEntries([['status', 'open'], ['scope', 'relevant'], ['country', 'PL'], ['country', 'DE']], { status: 'open', scope: 'relevant' }),
  '?country=PL%2CDE');
assert.equal(queryFromEntries([['status', 'open'], ['q', ''], ['page', '3']], { status: 'open' }), '', 'nothing left: the clean address');
assert.equal(queryFromEntries([['status', 'closed'], ['page', '2']], { status: 'open' }), '?status=closed');
assert.equal(queryFromEntries([['currency', 'EUR']], {}), '?currency=EUR', 'a chosen currency is kept, EUR included');
assert.equal(queryFromEntries([['x', new Blob([])]], {}), '', 'a file is not a filter');

// Two addresses with the same filters are the same, whatever the order, the page or a default spelled out.
const d = { status: 'open', scope: 'relevant' };
assert.equal(canonQuery('?country=PL&status=open', d), canonQuery('?country=PL', d));
assert.equal(canonQuery('?b=2&a=1', d), canonQuery('?a=1&b=2', d));
assert.equal(canonQuery('?country=PL&page=4', d), canonQuery('?country=PL', d));
assert.equal(canonQuery('?status=closed', d) === canonQuery('', d), false, 'a changed filter is a different address');
assert.equal(canonQuery('', d), '');

console.log('wp49.check ok');
