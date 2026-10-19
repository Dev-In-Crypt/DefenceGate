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
 * A consortium requirement does not decide the verdict (it asks the same of every applicant); it is listed as a condition that
 * comes with the verdict, in the badge's tooltip and on the call page. Since WP-53 the profile can say two things about the partners
 * (a legal entity established in Ukraine, a SEAP): a condition of exactly those two kinds is met by the answer, and only then is the
 * line "yes". Without the answer, or with another condition on partners, it stays "check".
 */
import { EU27, check, consortiumUnclear, partnerLine, unclearConsortiumText, type EligibilityFacts, type Line, type OrgType, type Profile as CheckProfile, type Result, type Verdict } from './eligibility-check';
import { managementCountryOf, type ApplicantKind, type Profile } from './profile';
import type { Assessment, ProgrammeAssessment, RoadmapStep } from './readiness-types';

export type Fit = Verdict | 'unknown';

export const FIT_WORD: Record<Fit, string> = { yes: 'Eligible', check: 'Conditions to check', no: 'Blocked', unknown: 'Rules not read' };
export const FIT_MEANING: Record<Fit, string> = {
  yes: 'Your saved profile meets every rule read from the call’s document that concerns it, and none carries a condition. Other conditions may apply: open the call.',
  check: 'No rule read excludes your saved profile, but something needs a closer look, must be obtained first, or depends on an answer. Open the call to see what.',
  no: 'A rule of the call’s document or of its programme excludes your saved profile.',
  unknown: 'No rule that can be compared with your profile has been read for this call.',
};

/**
 * The kind of organisation the form compares with a call's named kinds: a natural person is an individual, a public buyer, an
 * international organisation, a SEAP or the EDA are public bodies, a company or research body goes by its size class (the profile
 * cannot tell a university from a company, so "universities only" stays a "check").
 */
export function orgTypeOf(p: Profile): OrgType | '' {
  if (p.legalForm === 'natural_person') return 'individual';
  if (p.applicantKind === 'contracting_authority' || p.applicantKind === 'international_organisation' || p.applicantKind === 'seap' || p.applicantKind === 'eda') return 'public';
  return p.sizeClass === 'large' ? 'large' : p.sizeClass === '' ? '' : 'sme';
}

/** What the form of the call page asks, from the saved profile. Null while the country is not chosen. */
export function checkProfileOf(p: Profile): CheckProfile | null {
  if (!p.country) return null;
  return {
    country: p.country,
    orgType: orgTypeOf(p),
    // The profile says nothing about a consortium in general: a requirement of one is a condition (see `fitOf`). What it says about
    // partners (a Ukrainian entity, a SEAP) is in `more`.
    hasPartners: '',
    // "Controlled from outside the EU or associated countries": only an explicit "no" settles it. Control by
    // Ukraine or the EEA is associated for some calls and not for others, so it is a question for the document.
    controlledAbroad: p.control === 'no' ? 'no' : p.control === 'other' ? 'yes' : 'unsure',
    more: {
      legalPerson: p.legalForm === 'legal_person', company: p.applicantKind === 'company_or_research', managementCountry: managementCountryOf(p) ?? '',
      uaOccupied: p.uaOccupied, uaPartner: p.uaPartner, seapPartner: p.seapPartner,
    },
  };
}

export interface FitResult {
  fit: Fit;
  result: Result | null;
  /** What the call asks of every applicant and the profile cannot answer: shown beside the verdict, never hidden by it. */
  conditions: string[];
  /** The rules that exclude the profile (`fit` is `no`), in words. */
  blockedBy: string[];
}

/** The fit of one call: its facts against the saved profile. `facts` null or empty: the rules were not read. */
export function fitOf(facts: EligibilityFacts | null | undefined, profile: Profile | null): FitResult {
  const cp = profile ? checkProfileOf(profile) : null;
  if (!facts || !cp || Object.values(facts).every((f) => f === undefined)) return { fit: 'unknown', result: null, conditions: [], blockedBy: [] };
  const result = check(facts, cp);
  const lines: Line[] = [...result.lines];
  // What the form leaves out when the profile has no answer: an SME-only call and an unknown size.
  const sme = facts.sme_only;
  if (sme && sme.value === true && !cp.orgType) {
    lines.push({ key: 'sme', label: 'Organisation size', verdict: 'check', reason: 'The call is reserved for SMEs and your profile does not give a size class.', quote: sme.quote });
  }
  // A condition the document attaches to the consortium or to a single applicant (call 78: the proposal must use one of the specified
  // mechanisms; call 118: a single applicant must be Ukrainian; call 14: specific conditions on the composition) keeps the badge from
  // saying "Eligible" (V2-B10), unless it is one the profile answers and meets (WP-53, T21: `partnerLine`).
  const partner = partnerLine(facts, cp);
  if (partner && !lines.some((l) => l.key === 'consortium')) lines.push(partner);
  if (lines.length === 0) return { fit: 'unknown', result: null, conditions: [], blockedBy: [] };
  const verdict = lines.reduce<Verdict>((v, l) => (v === 'no' || l.verdict === 'no' ? 'no' : v === 'check' || l.verdict === 'check' ? 'check' : 'yes'), 'yes');
  const conditions: string[] = [];
  const n = facts.min_entities?.value;
  const k = facts.min_countries?.value;
  if (facts.consortium_required?.value === true) {
    conditions.push(`A consortium is required: ${typeof n === 'number' ? `at least ${n} legal entities` : 'several legal entities'}${typeof k === 'number' ? ` from at least ${k} countries` : ''}. Your profile does not say whether you have partners.`);
  } else if (consortiumUnclear(facts)) {
    conditions.push(`The document is unclear about a consortium: ${unclearConsortiumText(facts)} Read it.`);
  }
  return { fit: verdict, result: { verdict, lines }, conditions, blockedBy: lines.filter((l) => l.verdict === 'no').map((l) => l.label) };
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

/**
 * The kind of action of an EDIP call, from its topic code, as the API reads it (`action_of` in backend/dgate/regime.py; both are
 * tested against the same twelve topic codes). Null for any other call.
 */
export function actionOfCall(chip: string, topic: string): 'common_procurement' | 'seap_support' | 'edpci_preparation' | 'industrial_reinforcement' | null {
  const t = topic.toUpperCase().split('-');
  if ((chip !== 'EDF' && chip !== 'EDIP') || !t.includes('EDIP')) return null;
  if (t.includes('CPA')) return 'common_procurement';
  if (t.includes('SA') && t.includes('SEAP')) return 'seap_support';
  if (t.includes('CSA') && t.includes('PREP')) return 'edpci_preparation';
  if (t.includes('IRA')) return 'industrial_reinforcement';
  return null;
}

/**
 * Who may apply to the EDIP calls that are not open to a company (V2-B1): Regulation (EU) 2025/2643 Article 11(2) for common
 * procurement, and the call documents for the calls that support SEAPs and prepare projects of common interest. The API judges the same
 * with the rules EDIP-CPA-APPLICANT, EDIP-SEAP-APPLICANT and EDIP-PREP-APPLICANT; this mirror serves the badges of a list, where one
 * request per call would be too many.
 */
const APPLICANTS: Record<string, { title: string; plain: ApplicantKind[]; maybe: ApplicantKind[] }> = {
  common_procurement: {
    title: 'Who may apply: contracting authorities, international organisations, SEAPs and the EDA',
    plain: ['international_organisation', 'seap', 'eda'], maybe: ['contracting_authority'],
  },
  seap_support: { title: 'Who may apply: an established SEAP', plain: ['seap'], maybe: [] },
  edpci_preparation: { title: 'Who may apply: a SEAP or a group of Member States', plain: ['seap'], maybe: ['contracting_authority'] },
};

/** What the kind of applicant says about a call of one of those actions. Null where every kind may apply. */
export function applicantFit(chip: string, topic: string, profile: Profile | null): ProgrammeFit | null {
  const action = actionOfCall(chip, topic);
  const rule = action ? APPLICANTS[action] : undefined;
  if (!rule || !profile || !profile.country) return null;
  const kind = profile.applicantKind;
  if (kind === '') return { fit: 'check', because: [`${rule.title}: say what kind of organisation you are`] };
  if (rule.plain.includes(kind)) return { fit: 'yes', because: [] };
  // A contracting authority of a Member State is plainly one of those Article 11(2) names; of an EEA EFTA state or a group, a check.
  if (rule.maybe.includes(kind)) {
    return action === 'common_procurement' && EU27.has(profile.country) ? { fit: 'yes', because: [] } : { fit: 'check', because: [`${rule.title}: check that your organisation meets it`] };
  }
  return { fit: 'no', because: [rule.title] };
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
  if (prog.fit === 'no') return { ...doc, fit: 'no', conditions: [...prog.because, ...doc.conditions], blockedBy: [...prog.because, ...doc.blockedBy] };
  if (doc.fit === 'unknown') return doc;
  const fit: Fit = prog.fit === 'check' && doc.fit === 'yes' ? 'check' : doc.fit;
  return { ...doc, fit, conditions: [...prog.because, ...doc.conditions] };
}

// ---------------------------------------------------------------- what the badge says (UX walk-through U4)

/**
 * The verdict as shown. A "yes" that comes with a condition (a consortium to form, an unclear passage, a step the programme
 * asks first) is shown as "conditions to check", never as "eligible": the sorting of the list and the filter do not change,
 * both keep "yes" and "check" together.
 */
export function shownFit(r: FitResult): Fit {
  return r.fit === 'yes' && r.conditions.length > 0 ? 'check' : r.fit;
}

/** How many things the visitor still has to look at: the lines of the document that say "check" and the conditions. */
export function conditionCount(r: FitResult): number {
  return (r.result?.lines.filter((l) => l.verdict === 'check').length ?? 0) + r.conditions.length;
}

/**
 * The badge in words, informative without deciding more than the data allows. `word` is short enough for a card;
 * `detail` is the same with the reasons, for the tooltip and for a screen reader.
 */
export function fitLabel(r: FitResult): { word: string; detail: string } {
  const fit = shownFit(r);
  if (fit === 'no') {
    // "European Defence Industry Programme (EDIP): the Programme: Established in the Union ..." is the programme and the rule; the card has room for the rule.
    const rule = (b: string) => (b.includes(': ') ? b.slice(b.lastIndexOf(': ') + 2) : b);
    const first = rule(r.blockedBy[0] ?? 'a rule of the call');
    const more = r.blockedBy.length - 1;
    return { word: `Blocked by: ${first}${more > 0 ? ` and ${more} more` : ''}`, detail: `${FIT_MEANING.no} Blocked by: ${r.blockedBy.join('; ') || first}.` };
  }
  if (fit === 'check') {
    const n = conditionCount(r);
    const word = n > 0 ? `Nothing known blocks you, ${n} ${n === 1 ? 'condition' : 'conditions'} to check` : 'Nothing known blocks you';
    return { word, detail: [FIT_MEANING.check, ...r.conditions].join(' ') };
  }
  if (fit === 'yes') return { word: FIT_WORD.yes, detail: FIT_MEANING.yes };
  return { word: FIT_WORD.unknown, detail: FIT_MEANING.unknown };
}

/** One sentence above a list of lines: how many need a look, and whether any is a plain no (UX walk-through U4). */
export function linesSummary(lines: Line[]): string {
  const n = lines.length;
  const no = lines.filter((l) => l.verdict === 'no').length;
  const check = lines.filter((l) => l.verdict === 'check').length;
  if (n === 0) return '';
  if (n === 1) return no ? 'The one line is a no on your answers: read it first.' : check ? 'The one line needs your check; it is not a no.' : 'The one line is allowed on your answers. The call’s other conditions still apply.';
  if (no > 0) return `${no} of ${n} lines ${no === 1 ? 'is a no' : 'are a no'} on your answers: read ${no === 1 ? 'it' : 'them'} first.`;
  if (check > 0) return `${check} of ${n} lines ${check === 1 ? 'needs' : 'need'} your check; none is a no.`;
  return `All ${n} lines are allowed on your answers. The call’s other conditions still apply.`;
}
