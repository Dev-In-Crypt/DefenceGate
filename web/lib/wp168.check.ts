// WP-168 self-check: the call page's note after the programme name says where the portal files an EDIP or USI topic, once, and
// names the EDF (it read "European Defence Industry Programme (filed here by the portal; the call is under European Defence Industry
// Programme)" on /funding/116). Run: node scripts/run-checks.mjs
import assert from 'node:assert/strict';
import { portalFilingNote, programmeNameOf } from './format';

const usi = { programme: 'EDIP-USI', programmeName: 'EDIP Ukraine Support Instrument', topicId: 'EDF-EDIP-USI-2027-LS-IRA-CUXS' };
const kec = { programme: 'EDIP', programmeName: 'European Defence Industry Programme', topicId: 'EDF-EDIP-P-2027-LS-IRA-KEC' };
for (const c of [usi, kec]) {
  const note = portalFilingNote(c)!;
  assert.match(note, /European Defence Fund/);
  assert.ok(!note.includes(programmeNameOf(c)), 'the name is not said twice');
}
// an EDIP call the portal files under EDIP itself, and an EDF call: no note
assert.equal(portalFilingNote({ programme: 'EDIP', topicId: 'EDIP-2027-X' }), null);
assert.equal(portalFilingNote({ programme: 'EDF', topicId: 'EDF-2027-DA-X' }), null);
assert.equal(portalFilingNote({ programme: 'EDIP-USI', topicId: null }), null);
console.log('wp168 checks passed');
