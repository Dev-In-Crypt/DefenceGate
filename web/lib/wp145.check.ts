/**
 * Self-check of WP-145: an EDIP call whose own document says Ukrainian entities cannot receive funding (backend/dgate/ukraine.py
 * no_funding_sentence; reason `call_document_no_funding`) blocks a Ukrainian applicant with that sentence as the evidence, and nobody
 * else; a call whose document is silent is judged as before. Call 117 and the profiles P1 (ES) and P5 (UA) are the verified set
 * (data/wp93-pairs.json); the sentence is made up: no stored EDIP document says it (26 October 2026). The words of the page line, the
 * filter's URL key and the API's twin (backend/tests/unit/test_wp145.py) are checked too.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { UA_NO_FUNDING, UA_NO_FUNDING_REASON, type EligibilityFacts } from './eligibility-check';
import { callFit, fitLabel } from './fit';
import { parseProfile } from './profile';
import { parseCallFilters, toQuery } from './filters';
import { ukraineSentence } from './ukraine';

const SAID = 'Entities established in Ukraine are not eligible to receive funding under this call.';
const data = JSON.parse(readFileSync('lib/data/wp93-pairs.json', 'utf8'));
const c = data.after['117'] as { programme: string; topic: string; state: 'read'; facts: Record<string, object> };
const facts = Object.fromEntries(Object.entries(c.facts).map(([k, f]) => [k, { ...f, confidence: 1 }])) as unknown as EligibilityFacts;
const profile = (key: string) => parseProfile({ ...data.profiles[key].stored, ...data.profiles[key].answers, version: 4 });
const fit = (key: string, said: string | null) =>
  callFit({ state: c.state, programme: c.programme, topic: c.topic, facts, ukraineNoFunding: said }, profile(key), data.assessments[key]);

// a Ukrainian applicant: blocked by the document's sentence, which is the line's evidence
const ua = fit('P5', SAID);
assert.equal(ua.fit, 'no');
assert.ok(ua.blockedBy.includes(UA_NO_FUNDING), ua.blockedBy.join(' | '));
const line = ua.result!.lines.find((l) => l.key === 'ukraine_funding')!;
assert.deepEqual([line.label, line.verdict, line.reason, line.quote], [UA_NO_FUNDING, 'no', UA_NO_FUNDING_REASON, SAID]);
assert.match(fitLabel(ua).word, /^Blocked by: /);
// the same call without the sentence: no such line (the verified pair is unchanged)
assert.ok(!fit('P5', null).result!.lines.some((l) => l.key === 'ukraine_funding'));
// a Spanish company is not concerned
assert.ok(!fit('P1', SAID).result!.lines.some((l) => l.key === 'ukraine_funding'));
assert.ok(!fit('P1', SAID).blockedBy.includes(UA_NO_FUNDING));

// the API's words, word for word (backend/dgate/verdict.py)
const py = readFileSync('../backend/dgate/verdict.py', 'utf8').replace(/"\s*\n\s*"/g, '');
assert.ok(py.includes(`UA_NO_FUNDING = "${UA_NO_FUNDING}"`), 'verdict.py UA_NO_FUNDING');
assert.ok(py.includes(UA_NO_FUNDING_REASON), 'verdict.py UA_NO_FUNDING_REASON');

// the page line, and nothing for the other reasons it does not concern
assert.equal(ukraineSentence(null, 'call_document_no_funding'), 'Ukrainian entities cannot receive funding under this call: the call document says so.');
assert.ok(!/cannot receive funding under this call: the call document/.test(ukraineSentence(null, 'programme_rule') ?? ''));

// the filter's URL key goes to the API as it came
const f = parseCallFilters({ uaNoFunding: 'true' });
assert.equal(f.uaNoFunding, true);
assert.match(toQuery(f), /uaNoFunding=true/);
assert.equal(parseCallFilters({ uaNoFunding: 'yes' }).uaNoFunding, undefined);

console.log('wp145 checks passed');
