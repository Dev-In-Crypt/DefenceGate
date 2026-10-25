/**
 * Self-check of the sentence about Ukraine on a call page (V2-C U3, V2-B2, V2-B9). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { ukraineSentence } from './ukraine';

// The EDF: conditional on the association agreement, not confirmed; the same words as the readiness card and the tracker.
const edf = ukraineSentence(null, 'edf_association_unconfirmed')!;
assert.match(edf, /^Conditional on the association agreement, not confirmed\./);
assert.match(edf, /pending the signature of that agreement/);
assert.ok(!/^Unknown/.test(edf));
// EDIP: not for the recipient types the document names, with the reason; not "does not list Ukraine among the countries whose entities may take part".
const edip = ukraineSentence(false, 'programme_rule')!;
assert.match(edip, /^Not for the recipient types this call names\./);
assert.match(edip, /Ukraine is not an associated country of the Programme/);
assert.match(edip, /designating a procurement agent or as a member of a SEAP/);
// A call document that lists the eligible countries one by one without Ukraine.
assert.match(ukraineSentence(false, 'call_document_closed_list')!, /Ukraine is not on the list/);
// An EDIP Programme call (V3-A): the Regulation limits the recipients, the document is silent about Ukrainian entities, so the flag is unknown.
// WP-132 (round-7 audit, 116 and 117): the block said "Not decided" while the eligibility check on the same page blocks a Ukrainian company under
// that Regulation. One answer: the Regulation's, with its articles, and the other roles the documents give Ukraine.
const edipUnknown = ukraineSentence(null, 'programme_rule')!;
assert.match(edipUnknown, /^Entities established in Ukraine cannot receive EDIP funding under this call/);
assert.match(edipUnknown, /Regulation \(EU\) 2025\/2643, Articles 9\(1\) and 2/);
assert.match(edipUnknown, /The eligibility check on this page applies that rule/);
assert.match(edipUnknown, /as a member of a SEAP or as a state that designates a procurement agent/);
assert.doesNotMatch(edipUnknown, /Not decided|do not mark this call open or closed/);
assert.equal(ukraineSentence(true, 'topic_text_associated'), 'Ukrainian entities may take part in this call.');
assert.equal(ukraineSentence(null, 'not_stated'), null);
console.log('ukraine checks passed');
