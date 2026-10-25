/**
 * Self-check of WP-121 (verification round 6, 25 October 2026): the closing-soon order, the eligibility box's one verdict, the removal token
 * in names, the citation line and the scope note's words. The calls are what production served on 24 October (data/wp109-calls.json).
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { getCallDeadline, getTenderDeadline, soonestOpen } from './deadline';
import { answersFit, boxLines, callFit, fitLabel, linesSummary, shownFit, verdictLines, type Answers, type PageCall } from './fit';
import { displayName, shownVariants, withoutRemovedToken } from './display-name';
import { citeLine } from './market';
import { countPlus } from './format';
import { overlapNote } from './list-count';
import { emptyProfile, type Profile } from './profile';
import { SCOPE_CHOICES } from './taxonomy';
import type { Call, Tender } from './types';

// ---------------------------------------------------------------- 1. the closing lists: soonest still open first, by when each closes

const ref = new Date('2026-10-26T10:00:00Z');
const t = (id: string, deadline: string | null, deadlineIsDate?: boolean) =>
  ({ id, status: 'open', statusNative: 'open', deadline, deadlineIsDate }) as unknown as Tender;
// the API's order (a date-only 26 Oct at 00:00 sorts first) and one that passed this morning
const tenders = [t('passed', '2026-10-26T06:00:00Z'), t('day', '2026-10-26T00:00:00Z', true), t('noon', '2026-10-26T12:00:00Z'),
  t('later', '2026-10-27T09:00:00Z'), t('none', null), t('next', '2026-10-26T15:00:00Z')];
const soon = soonestOpen<Tender>(tenders, getTenderDeadline, 3, ref);
assert.deepEqual(soon.map((s) => s.item.id), ['noon', 'next', 'day'], 'passed and undated left out; a date-only deadline closes at the end of its day');
assert.ok(soon.every((s) => s.deadline.state !== 'closed'), 'a list never shows a deadline already passed');
assert.equal(soon[0].deadline.countdown, 'Today');
// every row is read against the one reference time: the same answer twice
assert.deepEqual(soonestOpen<Tender>(tenders, getTenderDeadline, 3, ref).map((s) => s.deadline.countdown), soon.map((s) => s.deadline.countdown));
const c = (id: string, deadline: string | null, extra: Partial<Call> = {}) => ({ id, status: 'open', deadline, ...extra }) as unknown as Call;
const calls = [c('rolling', '2026-10-20T17:00:00Z', { rolling: true }), c('date', '2026-10-28T00:00:00Z'), c('timed', '2026-10-27T17:00:00Z'), c('closed', '2026-10-25T17:00:00Z')];
assert.deepEqual(soonestOpen<Call>(calls, (x, r) => getCallDeadline(x, r), 3, ref).map((s) => s.item.id), ['timed', 'date'], 'a rolling call past its cut-off and a passed one are not "closing soon"');

// ---------------------------------------------------------------- 12. one verdict in the box: the summary and its lines agree

const data = JSON.parse(readFileSync('lib/data/wp109-calls.json', 'utf8'));
const page = (id: string): PageCall => ({ facts: data.calls[id].facts, programme: data.calls[id].programme, topic: data.calls[id].topicId, rulesApply: data.calls[id].rulesApply });
const ask = (a: Partial<Answers>): Answers => ({ country: '', orgType: '', hasPartners: '', controlledAbroad: '', ...a });
for (const orgType of ['sme', 'large', 'university'] as const) {
  // SEAP 114, Spain: "Blocked by: Who may apply" and "1 of 4 lines is a no" stood over the line "Who may apply: Check"
  const r = answersFit(page('114'), ask({ country: 'ES', orgType, hasPartners: 'no', controlledAbroad: 'no' }));
  const lines = verdictLines(r);
  const who = lines.filter((l) => l.label === 'Who may apply');
  assert.equal(who.length, 1, `114 ${orgType}: one line named "Who may apply"`);
  assert.equal(who[0].verdict, 'no', `114 ${orgType}: the line that blocks says no`);
  assert.equal(fitLabel(r).word, 'Blocked by: Who may apply');
  assert.match(linesSummary(lines), /is a no/);
  // every name in "Blocked by" is a line that says no
  for (const b of r.blockedBy) assert.ok(lines.some((l) => l.label === b && l.verdict === 'no'), `114 ${orgType}: ${b}`);
}
// a public body (a SEAP answers so) is a check, and its line says check
const pub = answersFit(page('114'), ask({ country: 'ES', orgType: 'public' }));
assert.equal(shownFit(pub), 'check');
assert.ok(verdictLines(pub).filter((l) => l.label === 'Who may apply').every((l) => l.verdict === 'check'));
// the saved profile's box: a call the programme's rules block lists that rule among its lines, never "none is a no" under "Blocked"
const sme: Profile = { ...emptyProfile(), country: 'ES', legalForm: 'legal_person', applicantKind: 'company_or_research', orgKind: 'company', control: 'no' };
const raw = data.calls['114'];
const fit = callFit({ state: 'read', facts: raw.facts, programme: raw.programme, topic: raw.topicId }, sme, null);
assert.equal(shownFit(fit), 'no');
const box = boxLines(fit);
assert.ok(box.lines.some((l) => l.verdict === 'no'), 'a blocking rule is a line of the box');
assert.doesNotMatch(linesSummary(box.lines), /none is a no/);
assert.ok(box.asked.every((a) => !fit.blockedBy.includes(a)), 'a rule that blocks is not also "asked of every applicant"');

// ---------------------------------------------------------------- 13. the removal token is never shown in a name

assert.equal(withoutRemovedToken('Agencja Uzbrojenia, [email removed]'), 'Agencja Uzbrojenia');
assert.equal(withoutRemovedToken('Agencja Uzbrojenia ([email removed])'), 'Agencja Uzbrojenia');
assert.equal(withoutRemovedToken('[email removed] - Agencja Uzbrojenia'), 'Agencja Uzbrojenia');
assert.equal(withoutRemovedToken('Skarb Panstwa - Agencja Uzbrojenia'), 'Skarb Panstwa - Agencja Uzbrojenia', 'a name without it is untouched');
assert.equal(displayName('AGENCJA UZBROJENIA, [email removed]', 'title').includes('[email removed]'), false);
assert.deepEqual(shownVariants(['Agencja Uzbrojenia, [email removed]', 'Agencja Uzbrojenia', 'Skarb Panstwa - Agencja Uzbrojenia', '[email removed]'], 'Skarb Państwa Agencja Uzbrojenia'),
  ['Agencja Uzbrojenia', 'Skarb Panstwa - Agencja Uzbrojenia'], 'each once, none empty, none with the token');
assert.deepEqual(shownVariants(['AGENCJA UZBROJENIA'], 'Agencja Uzbrojenia'), [], 'not the name the page shows');

// ---------------------------------------------------------------- 14. "See all 26+ open tenders", never "at least 26"

assert.equal(countPlus(26, true), '26+');
assert.equal(countPlus(1526, true), '1,526+');
assert.equal(countPlus(26, false), '26');

// ---------------------------------------------------------------- 15. how to cite a figure (terms, 12: DefenceGate, the source, the date)

assert.equal(citeLine(['TED', 'PLACSP'], '25 Oct 2026, 10:28 UTC', 'https://defencegatehub.com/market'),
  'DefenceGate (https://defencegatehub.com/market), from TED and PLACSP, figures as of 25 Oct 2026, 10:28 UTC.');
assert.equal(citeLine(['TED'], '25 Oct 2026', 'https://x.test/market'), 'DefenceGate (https://x.test/market), from TED, figures as of 25 Oct 2026.');
assert.match(citeLine([], '25 Oct 2026', 'https://x.test/market'), /from TED and national portals/);

// ---------------------------------------------------------------- 17. the scope note in the labels' words

const note = overlapNote({ overlap: 47 }) ?? '';
for (const k of ['relevant', 'core', 'supply'] as const) assert.ok(note.toLowerCase().includes(SCOPE_CHOICES[k].label.toLowerCase()), k);
assert.doesNotMatch(note, /Core and supplies|first count/);

console.log('wp121 checks passed');
