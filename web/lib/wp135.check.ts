/**
 * Self-check of WP-135: the page of the hidden copy of a Polish notice (bulletin and mirror) names the listed copy as its
 * canonical address. Not part of the app. Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { tenderCanonicalPath } from './seo';

assert.equal(tenderCanonicalPath({ slug: '41-dostawa', copyOf: '40-dostawa' }), '/tenders/40-dostawa');
assert.equal(tenderCanonicalPath({ slug: '40-dostawa', copyOf: null }), '/tenders/40-dostawa');
assert.equal(tenderCanonicalPath({ slug: '40-dostawa' }), '/tenders/40-dostawa', 'an older API without the field');
assert.equal(tenderCanonicalPath({ slug: '41-dostawa', copyOf: '../admin' }), '/tenders/41-dostawa', 'never a path that is not a slug');

console.log('wp135 checks passed');
