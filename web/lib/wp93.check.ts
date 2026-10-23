/**
 * Self-check of WP-93: the 60 (profile, call) pairs that two verifiers read against the official call documents on 23 October 2026
 * (data/wp93-pairs.json; D:/DEFENCEGATE TESTS/elig-check/FINDINGS.md). For every pair the one verdict (lib/fit.ts `callFit`) must be what the
 * document says: "cannot" is a "no"; "can only if" is a "check" that names the condition; "can" is a "yes" or a "check", never a "no".
 * And for every fixture call and every profile the browser's verdict is the API's (backend/dgate/verdict.py wrote `expected`), line by line,
 * from the facts as the list badge receives them (`GET /v1/fit/facts`) and as the call page receives them: one function, one answer.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 *
 * WP93_WRITE=1 writes `requests` (each profile's assessment request, lib/profile.ts toRequest) for backend/tests/wp93_golden.py.
 */
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import type { EligibilityFacts } from './eligibility-check';
import { callFit, fitLabel, shownFit, type CallFacts, type FitResult } from './fit';
import { HEADCOUNT_BANDS, parseProfile, toRequest, unanswered, type Profile } from './profile';

const PATH = 'lib/data/wp93-pairs.json';
const data = JSON.parse(readFileSync(PATH, 'utf8'));
type RawCall = { programme: string; topic: string; state: CallFacts['state']; facts: Record<string, { value: unknown; note: string | null; quote: string; scope: string }> };

const profileOf = (key: string): Profile => parseProfile({ ...data.profiles[key].stored, ...data.profiles[key].answers, version: 4 });

if (process.env.WP93_WRITE) {
  data.requests = Object.fromEntries(Object.keys(data.profiles).map((k) => [k, toRequest(profileOf(k))]));
  writeFileSync(PATH, `${JSON.stringify(data, null, 1)}\n`);
  console.log('wp93 requests written');
  process.exit(0);
}

// 1. The requests the golden file was built from are the ones the browser sends for these answers.
for (const key of Object.keys(data.profiles)) assert.deepEqual(toRequest(profileOf(key)), data.requests[key], `${key}: the request`);

// 2. The call as the list receives it (no confidence) and as the call page does: the same verdict, and the API's.
const asList = (c: RawCall): CallFacts => ({ state: c.state, programme: c.programme, topic: c.topic,
  facts: Object.fromEntries(Object.entries(c.facts).map(([k, f]) => [k, { value: f.value, note: f.note, quote: f.quote ?? '', confidence: 1, scope: f.scope as never }])) as EligibilityFacts });
const asPage = (c: RawCall): CallFacts => ({ ...asList(c), facts: Object.fromEntries(Object.entries(c.facts).map(([k, f]) => [k, { ...f, confidence: 0.9 }])) as unknown as EligibilityFacts });
const shape = (r: FitResult) => ({ fit: r.fit, shown: shownFit(r), word: fitLabel(r).word, conditions: r.conditions,
  lines: (r.result?.lines ?? []).map((l) => ({ key: l.key, verdict: l.verdict, reason: l.reason })) });
let compared = 0;
for (const key of Object.keys(data.profiles)) {
  for (const [id, call] of Object.entries(data.after as Record<string, RawCall>)) {
    const list = shape(callFit(asList(call), profileOf(key), data.assessments[key]));
    assert.deepEqual(shape(callFit(asPage(call), profileOf(key), data.assessments[key])), list, `${key} x call ${id}: list and call page`);
    assert.deepEqual(list, data.expected[`${key}|${id}`], `${key} x call ${id}: the browser and the API`);
    compared += 1;
  }
}

// 3. The 60 verified pairs: every one CORRECT.
const classify = (doc: string, mention: string | null, r: FitResult): boolean => {
  const shown = shownFit(r);
  const words = [...(r.result?.lines ?? []).map((l) => `${l.label} ${l.reason}`), ...r.conditions].join(' ');
  if (doc === 'cannot') return shown === 'no' && (!mention || words.includes(mention));
  if (doc === 'can_if') return shown === 'check' && (!mention || words.includes(mention));
  return shown === 'yes' || shown === 'check';
};
const wrong: string[] = [];
for (const p of data.pairs as { n: number; profile: string; call: string; document: string; mention: string | null }[]) {
  const r = callFit(asList(data.after[p.call]), profileOf(p.profile), data.assessments[p.profile]);
  if (process.env.WP93_PRINT) console.log(`${p.n} ${p.profile} ${p.call} ${p.document}: ${fitLabel(r).word} | ${(r.result?.lines ?? []).filter((l) => l.verdict !== 'yes').map((l) => `${l.key}=${l.verdict}`).join(' ')} | ${r.conditions.join(' / ').slice(0, 120)}`);
  if (!classify(p.document, p.mention, r)) wrong.push(`pair ${p.n} (${p.profile}, call ${p.call}): document ${p.document}${p.mention ? ` naming "${p.mention}"` : ''}, verdict ${shownFit(r)}: ${fitLabel(r).word}`);
}
assert.deepEqual(wrong, [], `the verified pairs:\n${wrong.join('\n')}`);
// The same pairs with the answers of version 3 only (a visitor who has not answered the new questions): no pair may turn into a false
// "can" or a false "cannot"; a "cannot" that needs a new answer may stay a "check" (the safe side), and is counted.
let oldOk = 0;
for (const p of data.pairs as { n: number; profile: string; call: string; document: string; mention: string | null }[]) {
  const r = callFit(asList(data.after[p.call]), parseProfile(data.profiles[p.profile].stored), data.assessments[p.profile]);
  const shown = shownFit(r);
  assert.ok(!(p.document === 'cannot' && shown === 'yes') && !(p.document !== 'cannot' && shown === 'no') && !(p.document === 'can_if' && shown === 'yes'),
    `pair ${p.n} with version 3 answers: ${fitLabel(r).word}`);
  if (classify(p.document, p.mention, r)) oldOk += 1;
}
if (process.env.WP93_PRINT) console.log(`with version 3 answers only: ${oldOk}/60 correct, none a false "can" or a false "cannot"`);

// 4. Old profiles keep working; an unanswered new question is a "check", never "eligible" (P10 without its WP-93 answers on the SME-only Accelerator).
const old = parseProfile(data.profiles.P10.stored);
assert.equal(old.version, 4);
assert.equal(old.headcount, '', 'a version 3 block has no staff count');
assert.equal(old.sizeClass, 'small', 'its size class is kept and still read');
assert.ok(unanswered(old).some((u) => /part of a group/.test(u.question)), 'the group question is listed as unanswered');
const acc = callFit(asList(data.after['24']), old, data.assessments.P10);
assert.equal(shownFit(acc), 'check', 'unanswered group: never "eligible"');
assert.equal(shownFit(callFit(asList(data.after['24']), profileOf('P10'), data.assessments.P10)), 'check', 'answered: a check still (the small mid-cap note)');
assert.deepEqual(HEADCOUNT_BANDS.map((b) => b.value), ['lt50', '50_249', '250_499', '500_1999', '2000plus']);
console.log(`wp93 checks passed: 60 pairs correct, ${compared} call x profile verdicts equal to the API's`);
