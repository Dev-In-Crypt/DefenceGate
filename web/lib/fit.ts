/**
 * "Does this call fit my profile?" (WP-32): the saved profile of the readiness check (`lib/profile.ts`, in the
 * browser) against the facts read from a call's document (`lib/eligibility-check.ts`). Pure: no DOM, no network.
 *
 * Rules of the verdict, all conservative and the same as the "Can you apply?" form on the call page:
 *   - "no" only where a document plainly excludes the profile (an SME-only call and a large company, an
 *     ownership restriction and a company controlled from outside);
 *   - "yes" only where every fact the document states that concerns the profile is met, none carries a condition,
 *     none comes from the work programme's general annexes, and the profile answers what the facts ask (size
 *     class, control);
 *   - "unknown" where there is nothing to compare: the call's rules were not read, or none of the facts
 *     read concerns what the profile says. Never a guess.
 * The profile does not say whether the company has partners. A consortium requirement therefore does not decide
 * the verdict (it asks the same of every applicant); it is listed as a condition that comes with the verdict, in the
 * badge's tooltip and on the call page.
 */
import { check, type EligibilityFacts, type Line, type Profile as CheckProfile, type Result, type Verdict } from './eligibility-check';
import type { Profile } from './profile';
import type { Assessment, ProgrammeAssessment, RoadmapStep } from './readiness-types';

export type Fit = Verdict | 'unknown';

export const FIT_WORD: Record<Fit, string> = { yes: 'Eligible', check: 'Check', no: 'Not eligible', unknown: 'Unknown' };
export const FIT_MEANING: Record<Fit, string> = {
  yes: 'Your saved profile meets every rule read from the call’s document that concerns it. Other conditions may apply: open the call.',
  check: 'Some rule needs a closer look, something must be obtained first, or it depends on an answer. Open the call to see what.',
  no: 'A rule of the call’s document or of its programme excludes your saved profile.',
  unknown: 'No rule that can be compared with your profile has been read for this call.',
};

/** What the form of the call page asks, from the saved profile. Null while the country is not chosen. */
export function checkProfileOf(p: Profile): CheckProfile | null {
  if (!p.country) return null;
  return {
    country: p.country,
    orgType: p.sizeClass === 'large' ? 'large' : p.sizeClass === '' ? '' : 'sme',
    // The profile has no question about partners: left unanswered, the consortium is a condition (see `fitOf`).
    hasPartners: '',
    // "Controlled from outside the EU or associated countries": only an explicit "no" settles it. Control by
    // Ukraine or the EEA is associated for some calls and not for others, so it is a question for the document.
    controlledAbroad: p.control === 'no' ? 'no' : p.control === 'other' ? 'yes' : 'unsure',
  };
}

export interface FitResult {
  fit: Fit;
  result: Result | null;
  /** What the call asks of every applicant and the profile cannot answer: shown beside the verdict, never hidden by it. */
  conditions: string[];
}

/** The fit of one call: its facts against the saved profile. `facts` null or empty: the rules were not read. */
export function fitOf(facts: EligibilityFacts | null | undefined, profile: Profile | null): FitResult {
  const cp = profile ? checkProfileOf(profile) : null;
  if (!facts || !cp || Object.values(facts).every((f) => f === undefined)) return { fit: 'unknown', result: null, conditions: [] };
  const result = check(facts, cp);
  const lines: Line[] = [...result.lines];
  // What the form leaves out when the profile has no answer: an SME-only call and an unknown size.
  const sme = facts.sme_only;
  if (sme && sme.value === true && !cp.orgType) {
    lines.push({ key: 'sme', label: 'Organisation size', verdict: 'check', reason: 'The call is reserved for SMEs and your profile does not give a size class.', quote: sme.quote });
  }
  if (lines.length === 0) return { fit: 'unknown', result: null, conditions: [] };
  const verdict = lines.reduce<Verdict>((v, l) => (v === 'no' || l.verdict === 'no' ? 'no' : v === 'check' || l.verdict === 'check' ? 'check' : 'yes'), 'yes');
  const conditions: string[] = [];
  if (facts.consortium_required?.value === true) {
    const n = facts.min_entities?.value;
    const k = facts.min_countries?.value;
    conditions.push(`A consortium is required: ${typeof n === 'number' ? `at least ${n} legal entities` : 'several legal entities'}${typeof k === 'number' ? ` from at least ${k} countries` : ''}. Your profile does not say whether you have partners.`);
  }
  return { fit: verdict, result: { verdict, lines }, conditions };
}

/** The calls of a list that the filter "Fits my profile" keeps: eligible, or worth a look. */
export const fitsProfile = (fit: Fit | undefined): boolean => fit === 'yes' || fit === 'check';

// ---------------------------------------------------------------- the programme's rules (EDF, EDIP)

/**
 * The programmes whose rules judge a call, as the API judges it (`programmes_of_call` in backend/dgate/readiness/api.py):
 * the portal files the EDIP calls under the EDF, so the topic code decides. Other programmes have no rules encoded.
 */
export function programmesOfCall(chip: string, topic: string): string[] {
  const t = topic.toUpperCase().split('-');
  if ((chip === 'EDF' || chip === 'EDIP') && t.includes('EDIP')) {
    const after = t[t.indexOf('EDIP') + 1];
    return after === 'USI' ? ['EDIP-USI'] : after === 'P' ? ['EDIP'] : ['EDIP', 'EDIP-USI'];
  }
  return chip === 'EDF' ? ['EDF'] : [];
}

export interface ProgrammeFit {
  fit: Verdict;
  /** The rules that no certificate fixes, or the steps that would, in words. */
  because: string[];
}

function oneProgramme(a: ProgrammeAssessment, steps: RoadmapStep[]): ProgrammeFit {
  const fixable = new Set(steps.filter((s) => s.blockingFor.includes(a.programme)).map((s) => s.code));
  const blocking = a.rules.filter((r) => a.blocking.includes(r.rule));
  // The same split as the API's `call_timing`: a blocking rule is fixable only when a step of the roadmap removes it.
  const structural = blocking.filter((r) => !r.requirement || !fixable.has(r.requirement));
  if (structural.length > 0) return { fit: 'no', because: [...new Set(structural.map((r) => `${a.name}: ${r.title}`))] };
  if (a.verdict === 'blocked') return { fit: 'check', because: steps.filter((s) => fixable.has(s.code)).map((s) => `Needs first: ${s.name}`) };
  if (a.verdict === 'conditional') return { fit: 'check', because: [`${a.name}: a condition or an answer is still open`] };
  return { fit: 'yes', because: [] };
}

/**
 * What the programme's rules say about the profile for a call of these programmes: `no` where a rule that no certificate
 * fixes is not met (a Ukrainian company and the EDIP Programme), `check` where something must be obtained first or a
 * condition is open, `yes` otherwise. Where a call may belong to two parts of a programme, the better one counts.
 * Null: no rules are encoded for the call's programme.
 */
export function programmeFit(assessment: Pick<Assessment, 'assessments' | 'roadmap'> | null, codes: string[]): ProgrammeFit | null {
  if (!assessment || codes.length === 0) return null;
  const found = assessment.assessments.filter((a) => codes.includes(a.programme));
  if (found.length === 0) return null;
  const rank: Record<Verdict, number> = { yes: 0, check: 1, no: 2 };
  return found.map((a) => oneProgramme(a, assessment.roadmap.steps)).sort((x, y) => rank[x.fit] - rank[y.fit])[0];
}

/**
 * The document's verdict and the programme's together. Never better than the worse of the two, and a call whose own rules
 * were not read stays `unknown` unless the programme rules out the profile for certain.
 */
export function withProgramme(doc: FitResult, prog: ProgrammeFit | null): FitResult {
  if (!prog) return doc;
  if (prog.fit === 'no') return { ...doc, fit: 'no', conditions: [...prog.because, ...doc.conditions] };
  if (doc.fit === 'unknown') return doc;
  const fit: Fit = prog.fit === 'check' && doc.fit === 'yes' ? 'check' : doc.fit;
  return { ...doc, fit, conditions: [...prog.because, ...doc.conditions] };
}
