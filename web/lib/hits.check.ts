/**
 * Self-check of the visit counter's pure parts and of the identifier shapes (review of 13 October 2026, H1 and
 * LOW). Not part of the app and not imported by it.
 * Run from web/:  npx tsc lib/hits.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop && node /tmp/dgchk/hits.check.js
 */
import assert from 'node:assert/strict';
import { clientIp, HitBuffer, IpLimiter, MAX_KEYS, referrerHost, routeKey, VIEWS_PER_MINUTE } from './hits';
import { followRef, ID_RE, isUuid, numericRef } from './refs';

// ---- a page, not a record; an unknown path cannot grow the table ----
assert.equal(routeKey('/tenders/123-armoured-vehicles'), '/tenders/[slug]');
assert.equal(routeKey('/tenders'), '/tenders');
assert.equal(routeKey('/'), '/');
assert.equal(routeKey('/funding/edf-2026-x'), '/funding/[slug]');
assert.equal(routeKey('/wp-login.php'), '/other');
assert.equal(routeKey('/auth/verify'), '/other');
assert.equal(routeKey('/tenders/[slug]'), '/tenders/[slug]');       // already a key: stays one

// ---- referrer: a host or nothing; the site itself is nothing ----
assert.equal(referrerHost('https://www.google.com/search?q=secret+words', 'defencegatehub.com'), 'www.google.com');
assert.equal(referrerHost('https://defencegatehub.com/tenders', 'defencegatehub.com'), '');
assert.equal(referrerHost('https://www.defencegatehub.com/', 'defencegatehub.com'), '');
assert.equal(referrerHost('not a url', 'defencegatehub.com'), '');
assert.equal(referrerHost(null, 'x'), '');
assert.equal(referrerHost(`https://${'a'.repeat(90)}.example/`, 'x'), '');

// ---- address: the first X-Forwarded-For entry, nothing else ----
assert.equal(clientIp('203.0.113.7, 10.0.0.1'), '203.0.113.7');
assert.equal(clientIp('2001:db8::1'), '2001:db8::1');
assert.equal(clientIp('<script>'), 'unknown');
assert.equal(clientIp(null), 'unknown');

// ---- buffer: sums per key, drains once, folds beyond the cap and never exceeds what a batch may hold ----
{
  const b = new HitBuffer();
  b.add('/tenders/[slug]', 'www.google.com', false);
  b.add('/tenders/[slug]', 'www.google.com', false);
  b.add('/tenders/[slug]', 'www.google.com', true);
  b.add('/', '', false);
  assert.equal(b.size, 3);
  const out = b.drain();
  assert.equal(b.size, 0);
  assert.deepEqual(b.drain(), []);
  const google = out.find((h) => h.route === '/tenders/[slug]' && !h.mobile);
  assert.equal(google?.count, 2);
  assert.equal(out.reduce((n, h) => n + h.count, 0), 4);
}
{
  const b = new HitBuffer();
  for (let n = 0; n < 5000; n++) b.add(n % 2 ? '/tenders/[slug]' : '/funding', `host${n}.example`, n % 3 === 0);
  const out = b.drain();
  assert.ok(out.length <= 200, `batch of ${out.length}`);          // the API's own cap per batch
  assert.equal(out.reduce((n, h) => n + h.count, 0), 5000);        // folded into `other`, none lost
  assert.ok(out.some((h) => h.referrer === 'other'));
  assert.ok(MAX_KEYS + 19 * 2 <= 200);
}
{
  const b = new HitBuffer();
  for (let n = 0; n < 20_000; n++) b.add('/', '', false);
  assert.equal(b.drain()[0].count, 10_000);                        // clamped to what one batch may carry
}

// ---- one address counts at most 120 page views a minute ----
{
  const l = new IpLimiter();
  let allowed = 0;
  for (let i = 0; i < 500; i++) if (l.allow('203.0.113.7', 1_000 + i)) allowed++;
  assert.equal(allowed, VIEWS_PER_MINUTE);
  assert.equal(l.allow('203.0.113.8', 1_000), true);               // another address is its own count
  assert.equal(l.allow('203.0.113.7', 1_000 + 60_000), true);      // the next minute starts again
}
{
  const l = new IpLimiter(120, 60_000, 50);
  for (let i = 0; i < 5_000; i++) l.allow(`ip-${i}`, 5);           // a flood of addresses stays bounded
  // @ts-expect-error private on purpose: the check is that it never grows past its cap
  assert.ok(l.windows.size <= 50);
}

// ---- identifiers ----
for (const ok of ['EDF', 'HORIZON', 'a', '12', 'EDF_2026', 'x.y-z']) assert.ok(ID_RE.test(ok), ok);
for (const bad of ['', '.hidden', '-x', '_x', '..', 'a b', 'a/b', 'a'.repeat(65), '../x']) assert.ok(!ID_RE.test(bad), bad);
assert.ok(isUuid('3f2b8c1e-5a4d-4c0e-9b7a-1d2e3f4a5b6c'));
for (const bad of ['', '123', '3f2b8c1e', 'g'.repeat(36), '3f2b8c1e-5a4d-4c0e-9b7a-1d2e3f4a5b6c0']) assert.ok(!isUuid(bad), bad);
assert.equal(numericRef('7'), '7');
assert.equal(numericRef('007'), '7');
assert.equal(numericRef('0'), '0');
assert.equal(numericRef('000'), '0');
for (const bad of ['', 'abc', '12a', '-1', '1.5', ' 7', '1'.repeat(19)]) assert.equal(numericRef(bad), null, bad);
assert.equal(followRef('buyer', '0042'), '42');
assert.equal(followRef('buyer', 'EDF'), null);
assert.equal(followRef('programme', 'EDF'), 'EDF');
assert.equal(followRef('programme', '.x'), null);

console.log('hits checks passed');
