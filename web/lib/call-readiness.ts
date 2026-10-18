/**
 * "Your readiness for this call" (WP-32): the one sentence that puts the two answers together, the facts read from
 * the call's document (lib/fit.ts) and the programme's rules with the time left (POST /v1/readiness/assess with the
 * call id). Pure; lib/call-readiness.check.ts runs it on its own.
 *
 * It never says more than the weaker of the two: the programme's rules can allow a company that the call's document
 * excludes, and the other way round. A "yes" is always followed by the sentence that the call's own conditions apply.
 */
import type { CallTiming } from './readiness-types';
import type { Fit } from './fit';

/** From the best case to the worst: the headline follows the best part of the programme that applies. */
const RANK: CallTiming['realistic'][] = ['yes', 'maybe', 'depends', 'unknown', 'no', 'not_possible', 'closed'];

export const READ_THE_CALL = 'The call’s own conditions and the official text decide; this is not legal advice.';

export function bestTiming(timings: CallTiming[]): CallTiming | null {
  return [...timings].sort((a, b) => RANK.indexOf(a.realistic) - RANK.indexOf(b.realistic))[0] ?? null;
}

/**
 * @param fit the fit to the call's document, or null when there is no profile answer to compare
 * @param timings what the assessment says for the programmes the call belongs to (empty: none is encoded)
 */
export function callSummary(fit: Fit | null, timings: CallTiming[]): string {
  const best = bestTiming(timings);
  if (best?.realistic === 'closed') return 'The deadline of this call has passed.';
  if (fit === 'no') return `The rules read from the call’s document exclude your saved profile. ${READ_THE_CALL}`;
  const doc = fit === 'check' ? ' The call’s document also asks you to check something, shown below.' : '';
  if (best === null) {
    if (fit === 'yes') return `Nothing read from the call’s document excludes you. No readiness rules are encoded for the programme of this call, so its own conditions may still apply. ${READ_THE_CALL}`;
    if (fit === 'check') return `Some rule read from the call’s document needs a closer look, shown below. No readiness rules are encoded for the programme of this call. ${READ_THE_CALL}`;
    return `We cannot say: no rule of this call could be compared with your profile, and no readiness rules are encoded for its programme. ${READ_THE_CALL}`;
  }
  switch (best.realistic) {
    case 'yes':
      return best.verdict === 'eligible'
        ? `No rule of the programme blocks you on your answers.${doc} ${READ_THE_CALL}`
        : `The programme’s rules allow you once the missing steps are done, and they fit before the deadline.${doc} ${READ_THE_CALL}`;
    case 'maybe':
      return `It works only if every missing step goes at the fast end.${doc} ${READ_THE_CALL}`;
    case 'depends':
      return `No certificate is missing, but a guarantee or an answer is still needed.${doc} ${READ_THE_CALL}`;
    case 'no':
      return `The missing steps take longer than the time left before the deadline.${doc} ${READ_THE_CALL}`;
    case 'not_possible':
      return `A rule of the programme that no certificate can fix is not met. ${READ_THE_CALL}`;
    default:
      return `The call states no deadline, so the time cannot be compared.${doc} ${READ_THE_CALL}`;
  }
}
