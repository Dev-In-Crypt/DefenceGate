/**
 * Self-check of the sentence that puts the document's rules and the programme's timing together (WP-32).
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { bestTiming, callSummary, READ_THE_CALL } from './call-readiness';
import type { CallTiming } from './readiness-types';

const t = (realistic: CallTiming['realistic'], verdict: CallTiming['verdict'] = 'blocked', programme = 'EDF'): CallTiming => ({
  programme, name: programme, verdict, deadline: null, daysLeft: 40, steps: [], fastestPathDays: { min: 0, max: 0 }, notFixable: [], realistic, text: '',
});

// The best part of the programme that applies speaks.
assert.equal(bestTiming([]), null);
assert.equal(bestTiming([t('not_possible', 'blocked', 'EDIP'), t('yes', 'eligible', 'EDIP-USI')])!.programme, 'EDIP-USI');
assert.equal(bestTiming([t('closed'), t('no')])!.realistic, 'no');

// A closed call is closed, whatever else is known.
assert.match(callSummary('yes', [t('closed')]), /deadline of this call has passed/);
// The document excluding the profile wins over a programme that would allow it.
assert.match(callSummary('no', [t('yes', 'eligible')]), /exclude your saved profile/);
// No programme rules: the document speaks alone, and says what is missing.
assert.match(callSummary('yes', []), /No readiness rules are encoded/);
assert.match(callSummary('check', []), /closer look/);
assert.match(callSummary('unknown', []), /We cannot say/);
assert.match(callSummary(null, []), /We cannot say/);
// Programme rules.
assert.match(callSummary('yes', [t('yes', 'eligible')]), /^No rule of the programme blocks you/);
assert.match(callSummary('yes', [t('yes', 'blocked')]), /once the missing steps are done/);
assert.match(callSummary('check', [t('yes', 'eligible')]), /document also asks you to check/);
assert.match(callSummary('yes', [t('maybe')]), /fast end/);
assert.match(callSummary('yes', [t('no')]), /longer than the time left/);
assert.match(callSummary('yes', [t('not_possible')]), /no certificate can fix/);
assert.match(callSummary('yes', [t('depends')]), /guarantee or an answer/);
assert.match(callSummary('yes', [t('unknown')]), /no deadline/);

// No sentence promises eligibility without the caveat.
for (const fit of ['yes', 'check', 'unknown', null] as const) {
  for (const timings of [[], [t('yes', 'eligible')], [t('maybe')], [t('no')], [t('not_possible')], [t('depends')], [t('unknown')]]) {
    assert.ok(callSummary(fit, timings).includes(READ_THE_CALL), `${fit} ${timings[0]?.realistic}`);
  }
}
console.log('call-readiness checks passed');
