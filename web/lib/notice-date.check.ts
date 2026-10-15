/**
 * Self-check of the notice-date label (WP-12, 15 October 2026). Not part of the app.
 * Run from web/:  npx tsc lib/notice-date.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop && node /tmp/dgchk/notice-date.check.js
 */
import assert from 'node:assert/strict';
import { noticeDateLabel } from './format';

assert.equal(noticeDateLabel({ noticeDate: '2026-09-12T00:00:00Z', noticeKind: 'award' }), 'Award notice dated 12 Sep 2026');
assert.equal(noticeDateLabel({ noticeDate: '2026-09-12T00:00:00Z', noticeKind: 'cancellation' }), 'Cancellation notice dated 12 Sep 2026');
assert.equal(noticeDateLabel({ noticeDate: '2026-09-12T00:00:00Z', noticeKind: 'something-new' }), 'Notice dated 12 Sep 2026');
assert.equal(noticeDateLabel({ noticeDate: '2026-09-12T00:00:00Z' }), 'Notice dated 12 Sep 2026');
assert.equal(noticeDateLabel({ noticeDate: null, noticeKind: 'award' }), null);
assert.equal(noticeDateLabel({}), null);
console.log('notice-date checks passed');
