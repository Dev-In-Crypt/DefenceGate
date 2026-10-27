// WP-154 self-check: company signals. The filters as the API takes them, what the paid part shows in each state, the comparable
// value line and the CSV rows. Run: node scripts/run-checks.mjs
import assert from 'node:assert/strict';
import { CSV_ROWS, NOT_ADVICE, SIGNAL_CSV_HEADER, comparableLine, fullState, parseSignalFilters, signalCsvRows, signalHref, signalQuery, type FundingRow, type GrowingRow, type MarketRow } from './signals';

// filters: an unknown kind is the first tab; CPV only for the procurement signals, a programme only for funding (the API refuses the other)
assert.deepEqual(parseSignalFilters({ kind: 'rumours', cpv: '35a40,', programme: 'EDF' }), { kind: 'growing', country: '', cpv: '3540,', programme: '', page: 1 });
assert.deepEqual(parseSignalFilters({ kind: 'funding', cpv: '35', programme: 'edf,NATO,EDIP', country: 'Germany<script>', page: '3' }),
  { kind: 'funding', country: 'Germanyscript', cpv: '', programme: 'EDF,EDIP', page: 3 });
assert.equal(signalQuery({ country: 'DE', cpv: '', programme: '' }), 'country=DE');
assert.equal(signalHref({ kind: 'growing', country: '', cpv: '', programme: '', page: 1 }), '/signals');
assert.equal(signalHref({ kind: 'markets', country: 'DE', cpv: '35', programme: '', page: 2 }), '/signals?kind=markets&country=DE&cpv=35&page=2');
assert.equal(signalHref({ kind: 'markets', country: 'DE', cpv: '', programme: '', page: 4 }, { page: 1 }, '/signals/export.csv'), '/signals/export.csv?kind=markets&country=DE');

// the paid part: closed by its switch whatever the account; open: sign in, a plan, or the list
assert.equal(fullState(false, 200), 'closed');
assert.equal(fullState(true, 404), 'closed');
assert.equal(fullState(true, 0), 'signin');
assert.equal(fullState(true, 401), 'signin');
assert.equal(fullState(true, 402), 'plan');
assert.equal(fullState(true, 200), 'full');

const company = { id: '7', slug: '7-alpha', name: 'Alpha GmbH', country: 'DE' };
const growing: GrowingRow = { company, recent: 3, prior: 1, recentValues: [], priorValues: [], latest: null,
  comparable: { currency: 'EUR', recent: 3_000_000, recentCount: 2, prior: 500_000, priorCount: 1 } };
assert.equal(comparableLine(growing), 'EUR 3,000,000 (2) against EUR 500,000 (1)');
assert.equal(comparableLine({ ...growing, comparable: null }), null);

// CSV: one cell per header column, the company page link absolute, a funding row with its projects
const g = signalCsvRows('growing', [growing], 'https://site.test');
assert.equal(g[0].length, SIGNAL_CSV_HEADER.growing.length);
assert.equal(g[0][g[0].length - 1], 'https://site.test/suppliers/7-alpha');
const market: MarketRow = { company, market: 'LT', firstWinAt: '2026-09-02T00:00:00Z', winsThere: 1, winsBefore: 4, firstWin: null };
assert.deepEqual(signalCsvRows('markets', [market], 'https://site.test')[0].slice(2, 6), ['LT', '2026-09-02', 1, 4]);
const funding: FundingRow = { company, year: 2025, first: true, newProjects: 2, earlierProjects: 0,
  projects: [{ slug: '1-a', acronym: 'ALPHA', title: 'A', programme: 'EDF', year: 2025, role: 'participant', source: 'edf_factsheets', factsheetUrl: null },
    { slug: '2-b', acronym: null, title: 'Bravo project', programme: 'EDF', year: 2025, role: 'coordinator', source: 'edf_factsheets', factsheetUrl: null }] };
const fr = signalCsvRows('funding', [funding], 'https://site.test')[0];
assert.equal(fr.length, SIGNAL_CSV_HEADER.funding.length);
assert.deepEqual(fr.slice(2, 7), [2025, 'yes', 2, 0, 'ALPHA | Bravo project']);
assert.equal(fr[7], 'https://site.test/organisations/7-alpha');
assert.equal(CSV_ROWS, 2000);
assert.equal(NOT_ADVICE, 'Facts from public records, not investment advice.');
console.log('wp154 ok');
