/**
 * Self-check of the visit counter's pure parts and of the identifier shapes (review of 13 October 2026, H1 and
 * LOW). Not part of the app and not imported by it.
 * Run from web/:  npx tsc lib/hits.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop && node /tmp/dgchk/hits.check.js
 */
import assert from 'node:assert/strict';
import { clientIp, country, HitBuffer, IpLimiter, MAX_KEYS, PAGE_KEYS, referrerHost, routeKey, VIEWS_PER_MINUTE } from './hits';
import { followRef, ID_RE, isUuid, numericRef } from './refs';

// ---- a page, not a record; an unknown path cannot grow the table ----
assert.equal(routeKey('/tenders/123-armoured-vehicles'), '/tenders/[slug]');
assert.equal(routeKey('/tenders'), '/tenders');
assert.equal(routeKey('/'), '/');
assert.equal(routeKey('/funding/edf-2026-x'), '/funding/[slug]');
assert.equal(routeKey('/wp-login.php'), '/other');
assert.equal(routeKey('/auth/verify'), '/other');
assert.equal(routeKey('/tenders/[slug]'), '/tenders/[slug]');       // already a key: stays one
assert.equal(routeKey('/suppliers/406963-indra/competitors'), '/suppliers/[slug]');   // WP-169: newer pages are pages
assert.equal(routeKey('/signals'), '/signals');

// ---- referrer: a host or nothing; the site itself is 'internal' (WP-169: was '', the API still stores it as '' with the detail off) ----
assert.equal(referrerHost('https://www.google.com/search?q=secret+words', 'defencegatehub.com'), 'www.google.com');
assert.equal(referrerHost('https://defencegatehub.com/tenders', 'defencegatehub.com'), 'internal');
assert.equal(referrerHost('https://www.defencegatehub.com/', 'defencegatehub.com'), 'internal');
assert.equal(referrerHost('not a url', 'defencegatehub.com'), '');
assert.equal(referrerHost(null, 'x'), '');
assert.equal(referrerHost(`https://${'a'.repeat(90)}.example/`, 'x'), '');

// ---- country: Cloudflare's two characters or nothing (WP-169) ----
assert.equal(country('DE'), 'DE');
assert.equal(country('T1'), 'T1');
assert.equal(country('de'), '');
assert.equal(country('DEU'), '');
assert.equal(country(null), '');

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
  assert.ok(MAX_KEYS + PAGE_KEYS * 2 <= 200);                      // WP-169: more pages, so fewer ordinary keys (was 19 and 150)
}
{
  // WP-169: exact paths, hosts and countries vary freely; beyond the cap each is folded to its page key, `other` and no country
  const b = new HitBuffer();
  for (let n = 0; n < 5000; n++) b.add(`/tenders/${n}-x`, `host${n}.example`, n % 3 === 0, n % 2 ? 'DE' : 'FR');
  const out = b.drain();
  assert.ok(out.length <= 200, `batch of ${out.length}`);
  assert.equal(out.reduce((n, h) => n + h.count, 0), 5000);
  assert.ok(out.some((h) => h.route === '/tenders/[slug]' && h.referrer === 'other' && h.country === ''));
  assert.ok(out.some((h) => h.route === '/tenders/0-x' && h.country === 'FR'));
  const one = new HitBuffer();
  one.add(`/funding/${'x'.repeat(300)}`, '', false, '');           // longer than the API takes: its page key
  assert.equal(one.drain()[0].route, '/funding/[slug]');
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
