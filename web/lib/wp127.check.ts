/**
 * Self-check of WP-127 (the tender page waited 1.5 s on every view for a scope count that answered 503). Not part of the app and
 * not imported by it. Run with `npm run check` (scripts/run-checks.mjs), or from web/:
 *   npx tsc lib/wp127.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop --resolveJsonModule && node /tmp/dgchk/wp127.check.js
 */
import assert from 'node:assert/strict';
import { SCOPE_COUNTS_GRACE_MS, within } from './list-count';

const after = <T>(ms: number, v: T) => new Promise<T>((r) => setTimeout(() => r(v), ms));

(async () => {
  assert.ok(SCOPE_COUNTS_GRACE_MS > 0 && SCOPE_COUNTS_GRACE_MS <= 500, 'a moment, not a second');
  // an answer in time is kept
  assert.deepEqual(await within(after(10, { relevant: 3 }), 200), { relevant: 3 });
  // a late answer is left out, and the wait is the bound, not the answer's time
  const t0 = Date.now();
  assert.equal(await within(after(3000, { relevant: 3 }), 100), null);
  const waited = Date.now() - t0;
  assert.ok(waited < 1000, `waited ${waited} ms`);
  // a failure is no numbers, not an error
  assert.equal(await within(Promise.reject(new Error('503')), 100), null);
  // an answer already there is kept even with no time left
  assert.equal(await within(Promise.resolve(7), 0), 7);
  console.log('wp127 ok');
})().catch((e) => { console.error(e); process.exit(1); });
