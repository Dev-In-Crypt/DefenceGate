// WP-157 self-check: the client profile form values. Run: node scripts/run-checks.mjs
import assert from 'node:assert/strict';
import { parseCountry, parseCpvList, switchBack } from './client-profile';

assert.deepEqual(parseCpvList('35400000, 35;35400000\n34'), ['35400000', '35', '34']);
assert.deepEqual(parseCpvList(''), []);
assert.equal(parseCpvList('35400000-1'), null);                           // the check digit is not part of the code here
assert.equal(parseCpvList('3'), null);
assert.equal(parseCpvList(Array.from({ length: 21 }, (_, i) => String(10 + i)).join(',')), null);

assert.equal(parseCountry(' de '), 'DE');
assert.equal(parseCountry(''), null);
assert.equal(parseCountry('Germany'), undefined);

assert.equal(switchBack('/app/shortlist'), '/app/shortlist');
assert.equal(switchBack('https://evil.example/app/shortlist'), '/app/clients');   // never another site
assert.equal(switchBack('/app/settings'), '/app/clients');

console.log('client-profile checks ok');
