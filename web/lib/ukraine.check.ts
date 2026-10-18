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
// An EDIP Programme call (V3-A): the Regulation limits the recipients, the document is silent about Ukrainian entities: not decided, and no claim of "closed".
assert.match(ukraineSentence(null, 'programme_rule')!, /^Not decided\. Recipients of EDIP funding/);
assert.match(ukraineSentence(null, 'programme_rule')!, /No sentence we hold says whether entities established in Ukraine may apply/);
assert.match(ukraineSentence(null, 'programme_rule')!, /We do not mark this call open or closed/);
assert.equal(ukraineSentence(true, 'topic_text_associated'), 'Ukrainian entities may take part in this call.');
assert.equal(ukraineSentence(null, 'not_stated'), null);
console.log('ukraine checks passed');
