/**
 * WP-116 self-check of the sign-in return path (no open redirect). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (or tsc this file alone, as the other checks)
 */
import assert from 'node:assert/strict';
import { bindValue, readBind, safeReturnPath } from './safe-url';

for (const ok of ['/app', '/app/', '/app/shortlist', '/app/searches?tab=2', '/app/settings/', '/app/following?kind=buyer&x=a%20b'])
  assert.equal(safeReturnPath(ok), ok, ok);

for (const bad of [
  null, undefined, 42, '', 'app', '/', '/tenders', '/application', '/apps/x', '//evil.example', '/app//evil.example',
  'https://evil.example/app', '/\\evil.example', '/app\\evil', '/app/../tenders', '/app/./x', '/app/%2e%2e/tenders', '/app/%2F%2Fevil',
  '/app/%5cevil', '/app/x#frag', '/app/x y', '/app/\nx', 'javascript:alert(1)', `/app/${'a'.repeat(400)}`, '/app/x?next=//evil"',
]) assert.equal(safeReturnPath(bad), null, String(bad));

// across the mailed link, in the bind cookie
const binder = 'A'.repeat(43);
assert.equal(bindValue(binder, null), binder);
assert.equal(bindValue(binder, 'https://evil.example'), binder);
assert.deepEqual(readBind(bindValue(binder, '/app/shortlist?x=1')), { binder, next: '/app/shortlist?x=1' });
assert.deepEqual(readBind(binder), { binder, next: null });
assert.deepEqual(readBind(`${binder}.${encodeURIComponent('//evil.example')}`), { binder, next: null });
assert.deepEqual(readBind(`${binder}.%E0%A4%A`), { binder, next: null });
assert.deepEqual(readBind(undefined), { binder: undefined, next: null });

console.log('safe-url.check: ok');
