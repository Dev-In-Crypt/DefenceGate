// WP-103 self-check (run by scripts/run-checks.mjs): the three tender-page lines of award and value correctness.
import assert from 'node:assert/strict';
import { setAsideNote, versionCountLine, winnersNotReadLine } from './award-lines';

// winners not read: a core award not read yet, an award outside the core scope, and every case that says nothing
const base = { statusNative: 'awarded', scope: 'core' as const, winnersRead: false, awardedTo: [], awardedPersons: 0 };
assert.equal(winnersNotReadLine(base), 'not read yet by DefenceGate; the original notice names the winners');
const supply = winnersNotReadLine({ ...base, scope: 'supply' });            // 728479-2026, kept by its buyer alone
assert.ok(supply?.startsWith('not read by DefenceGate: winners are read for the notices of the defence core scope'));
assert.equal(winnersNotReadLine({ ...base, winnersRead: true }), null);
assert.equal(winnersNotReadLine({ ...base, winnersRead: undefined }), null);   // an older API: nothing claimed
assert.equal(winnersNotReadLine({ ...base, statusNative: 'open' }), null);
assert.equal(winnersNotReadLine({ ...base, awardedPersons: 1 }), null);
assert.equal(winnersNotReadLine({ ...base, awardedTo: [{ name: 'X', slug: null, country: 'ES', valueAmount: null, valueCurrency: null, valueKind: null }] }), null);

// the set-aside figure (220199-2026): said, and only on an estimate that carries one
const note = setAsideNote({ kind: 'estimate', currency: 'EUR', setAside: 7274615930 });
assert.ok(note?.includes('7,274,615,930') && note.includes('over a hundred times the buyer’s estimate'), note ?? '');
assert.equal(setAsideNote({ kind: 'estimate', currency: 'EUR' }), null);
assert.equal(setAsideNote({ kind: 'contract', currency: 'EUR', setAside: 5 }), null);
assert.equal(setAsideNote(null), null);

// the version count: the versions listed, DefenceGate's corrections (remapped re-reads) apart
assert.equal(versionCountLine(1, 2), 'One version observed so far, and 2 corrections by DefenceGate (below).');
assert.equal(versionCountLine(3, 0), '3 versions observed.');
assert.equal(versionCountLine(2, 1), '2 versions observed, and 1 correction by DefenceGate (below).');

console.log('wp103 checks passed');
