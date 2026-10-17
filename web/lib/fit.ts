/**
 * "Does this call fit my profile?" (WP-32): the saved profile of the readiness check (`lib/profile.ts`, in the
 * browser) against the facts read from a call's document (`lib/eligibility-check.ts`). Pure: no DOM, no network.
 *
 * Rules of the verdict, all conservative and the same as the "Can you apply?" form on the call page:
 *   - "no" only where a document plainly excludes the profile (an SME-only call and a large company, an
 *     ownership restriction and a company controlled from outside);
 *   - "yes" only where every fact the document states is met and none carries a condition, none comes from
 *     the work programme's general annexes, a consortium is not required, and the profile answers what the
 *     facts ask (size class, control);
 *   - "unknown" where there is nothing to compare: the call's rules were not read, or none of the facts
 *     read concerns what the profile says. Never a guess.
 * The profile does not say whether the company has partners, so a call that needs a consortium is at best
 * "check".
 */
import { check, type EligibilityFacts, type Line, type Profile as CheckProfile, type Result, type Verdict } from './eligibility-check';
import type { Profile } from './profile';

export type Fit = Verdict | 'unknown';

export const FIT_WORD: Record<Fit, string> = { yes: 'Eligible', check: 'Check', no: 'Not eligible', unknown: 'Unknown' };
export const FIT_MEANING: Record<Fit, string> = {
  yes: 'Your saved profile meets every rule read from the call’s document. Conditions the document does not state may still apply.',
  check: 'Some rule needs a closer look, or depends on an answer or on partners. Open the call to see which.',
  no: 'A rule read from the call’s document excludes your saved profile.',
  unknown: 'No rule that can be compared with your profile has been read for this call.',
};

/** What the form of the call page asks, from the saved profile. Null while the country is not chosen. */
export function checkProfileOf(p: Profile): CheckProfile | null {
  if (!p.country) return null;
  return {
    country: p.country,
    orgType: p.sizeClass === 'large' ? 'large' : p.sizeClass === '' ? '' : 'sme',
    // The profile has no question about partners: a consortium call is "check", never "yes".
    hasPartners: 'unsure',
    // "Controlled from outside the EU or associated countries": only an explicit "no" settles it. Control by
    // Ukraine or the EEA is associated for some calls and not for others, so it is a question for the document.
    controlledAbroad: p.control === 'no' ? 'no' : p.control === 'other' ? 'yes' : 'unsure',
  };
}

export interface FitResult { fit: Fit; result: Result | null }

/** The fit of one call: its facts against the saved profile. `facts` null or empty: the rules were not read. */
export function fitOf(facts: EligibilityFacts | null | undefined, profile: Profile | null): FitResult {
  const cp = profile ? checkProfileOf(profile) : null;
  if (!facts || !cp || Object.values(facts).every((f) => f === undefined)) return { fit: 'unknown', result: null };
  const result = check(facts, cp);
  const lines: Line[] = [...result.lines];
  // What the form leaves out when the profile has no answer: an SME-only call and an unknown size.
  const sme = facts.sme_only;
  if (sme && sme.value === true && !cp.orgType) {
    lines.push({ key: 'sme', label: 'Organisation size', verdict: 'check', reason: 'The call is reserved for SMEs and your profile does not give a size class.', quote: sme.quote });
  }
  if (lines.length === 0) return { fit: 'unknown', result: null };
  const verdict = lines.reduce<Verdict>((v, l) => (v === 'no' || l.verdict === 'no' ? 'no' : v === 'check' || l.verdict === 'check' ? 'check' : 'yes'), 'yes');
  return { fit: verdict, result: { verdict, lines } };
}

/** The calls of a list that the filter "Fits my profile" keeps: eligible, or worth a look. */
export const fitsProfile = (fit: Fit | undefined): boolean => fit === 'yes' || fit === 'check';
