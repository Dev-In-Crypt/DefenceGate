// WP-155 self-check: the line under a signal's first rows (mosaic rule: the anonymous rows leave small companies out, the count is
// the whole list's) and the paid features the site knows. Run: node scripts/run-checks.mjs
import assert from 'node:assert/strict';
import { firstRowsLine } from './signals';
import { PAID_FEATURES } from './types';

const rows = (n: number) => Array.from({ length: n }, () => ({})) as never[];

// anonymous, the full list open: "N of M shown; sign in for the rest", and why small companies are not among them
assert.equal(firstRowsLine({ items: rows(10), total: 240, public: true, smallBelow: 10, fullOpen: true }),
  '10 of 240 companies shown; sign in for the rest. Rows of companies with fewer than 10 awarded procurements in three years are shown only after sign-in.');
// anonymous, the full list closed: no promise of the rest, the small companies still after sign-in
assert.equal(firstRowsLine({ items: rows(3), total: 12, public: true, smallBelow: 10, fullOpen: false }),
  '3 of 12 companies shown. Rows of companies with fewer than 10 awarded procurements in three years are shown only after sign-in.');
// signed in: the first rows as they rank
assert.equal(firstRowsLine({ items: rows(10), total: 240, public: false, fullOpen: true }), 'The first 10 of 240 companies.');
// everything shown: no word on the rest
assert.equal(firstRowsLine({ items: rows(1), total: 1, public: true, fullOpen: true }), 'All 1 company.');
assert.equal(firstRowsLine({ items: rows(3), total: 3, public: false, fullOpen: false }), 'All 3 companies.');

// the owner's split: every gate the backend has (billing.FEATURES), and none of them is "api_keys" (a licence, not a plan)
assert.deepEqual([...PAID_FEATURES].sort(), ['branded_reports', 'client_profiles', 'company_report', 'competitors_full', 'consortium_gaps', 'eligibility_export', 'email_alerts', 'saved_searches', 'signals_csv', 'signals_full', 'supplier_map_csv', 'team_workspace']);   // WP-156: the two exports; WP-157: workspace and clients
assert.ok(!(PAID_FEATURES as readonly string[]).includes('api_keys'));

console.log('wp155 checks ok');
