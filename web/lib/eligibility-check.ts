/**
 * "Can you apply?" for one call: the facts read from its call document (API `documentEligibility`)
 * against a few answers typed in the browser. Nothing here leaves the page.
 *
 * Rules of the verdict, all conservative: a "no" only where the document plainly excludes the
 * answer; a "yes" only where every applicable fact allows it and carries no condition; everything
 * else is "check", with the reason and the document's own sentence beside it. A fact that was
 * not read, or whose quote was not found in the document, is never in the data (the API drops it).
 */

export interface EligibilityFact {
  value: unknown; note?: string | null; quote: string; confidence: number;
  /** Where it was read: the call document, the work programme's general annexes (a rule the topic may change), or the topic's own text. */
  scope?: 'call_document' | 'general' | 'topic';
}
export type EligibilityFacts = Record<string, EligibilityFact | undefined>;

export type OrgType = 'sme' | 'large' | 'public' | 'university' | 'individual';
export type Tri = 'yes' | 'no' | 'unsure';
export interface Profile {
  country: string;            // ISO 3166-1 alpha-2, '' when not chosen
  orgType: OrgType | '';
  hasPartners: Tri | '';
  controlledAbroad: Tri | '';
}

export type Verdict = 'yes' | 'check' | 'no';
export interface Line { key: string; label: string; verdict: Verdict; reason: string; quote?: string }
export interface Result { verdict: Verdict; lines: Line[] }

export const EU27 = new Set(['AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE']);
export const EEA_EXTRA = new Set(['IS', 'LI', 'NO']);

export const FACT_LABELS: Record<string, string> = {
  eligible_countries: 'Where applicants must be established',
  entity_types: 'Who may apply',
  consortium_required: 'Consortium required',
  min_entities: 'Smallest consortium (legal entities)',
  min_countries: 'Smallest number of countries',
  single_applicant_allowed: 'A single applicant may apply',
  sme_only: 'Reserved for SMEs',
  natural_persons_allowed: 'Natural persons may apply',
  ownership_control_restriction: 'Ownership control restriction',
  funding_rate: 'Funding rate',
  cascade_funding: 'Financial support to third parties (cascade)',
};

export function factText(f: EligibilityFact): string {
  const v = f.value;
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (Array.isArray(v)) return v.join('; ');
  return String(v);
}

const worst = (a: Verdict, b: Verdict): Verdict => (a === 'no' || b === 'no' ? 'no' : a === 'check' || b === 'check' ? 'check' : 'yes');

function withNote(line: Line, fact: EligibilityFact | undefined): Line {
  if (line.verdict === 'yes' && fact?.note) return { ...line, verdict: 'check', reason: `${line.reason} A condition applies: ${fact.note}` };
  return line;
}

/** Words in a fact's note or quote that name a way round a restriction: a guarantee, a screening, an exemption, a narrower scope. */
const EXCEPTION = /guarantee|exempt|exception|unless|screening|derogat|approved by|china|high[- ]risk|only (?:applies|if|for)|limited to/i;

/** Applicant kinds a company (or other profile) is plainly covered by, when a call lists the kinds that may apply. */
const COVERS: Record<OrgType, RegExp> = {
  sme: /legal entit|private|compan|enterprise|business|firm|industr|\bsmes?\b|start-?up|mid-?cap/i,
  large: /legal entit|private|compan|enterprise|business|firm|industr/i,
  public: /legal entit|public|authorit|ministr|agenc|bod(?:y|ies)/i,
  university: /legal entit|universit|research|academi|\brtos?\b/i,
  individual: /natural person|individual|sole trader/i,
};

/** What the API puts before the note of a fact read from the annexes or from a topic's own text (`SCOPE_NOTES` in eligibility.py): it says where, not a condition. */
const SCOPE_PREFIX = /^(?:General rule of the work programme annexes; the topic or the type of action may add or change it\.|Stated in this topic[’']s own conditions\.)\s*/;
function ownNote(f: EligibilityFact | undefined): string {
  return (f?.note ?? '').replace(SCOPE_PREFIX, '').trim();
}

/** Words that name a size class below "large": a list of kinds that only has these does not cover a large company (V2-C U2, call 131). */
const SMALL_ONLY = /\bsmes?\b|\bsmall\b|\bmicro\b|\bmedium\b|mid-?\s?caps?/i;

/** Whether one kind of applicant named by a call plainly covers a profile (V2-C U2: "SME company" and "Small mid-cap company (up to 499 employees)" do not cover a large company). */
export function covers(org: OrgType, kind: string): boolean {
  if (org === 'large' && SMALL_ONLY.test(kind) && !/\blarge\b/i.test(kind)) return false;
  return COVERS[org].test(kind);
}

/**
 * A condition the document attaches to who applies together with whom, as one sentence, or null. A consortium that is "not required" is still
 * not "no consortium is required" when a single applicant must meet a condition (call 118: a single applicant must be Ukrainian), and a
 * consortium whose composition is left to specific conditions is not a plain "yes" (call 14).
 */
export function singleApplicantCondition(facts: EligibilityFacts): string | null {
  const single = facts.single_applicant_allowed;
  const note = ownNote(single);
  return single?.value === true && note ? `A single applicant may apply under a condition: ${note}` : null;
}

export function consortiumCondition(facts: EligibilityFacts): string | null {
  const cons = facts.consortium_required;
  const consNote = ownNote(cons);
  const single = singleApplicantCondition(facts);
  if (single) return single;
  if (consNote) return `The call attaches a condition to the consortium: ${consNote}`;
  if (cons?.value === true && /specific conditions|conditions for the consortium|composition/i.test(cons.quote)) {
    return 'The call sets specific conditions on who may form the consortium that are not read here; check its section on consortium composition.';
  }
  return null;
}

export function check(facts: EligibilityFacts, p: Profile): Result {
  const lines: Line[] = [];

  // Who may apply: a call that names the kinds of applicant it is open to is not open to a profile that is not
  // plainly one of them (call 78 of 17 October 2026: an EDIC or a government-appointed mechanism only). A list is read
  // as possibly partial, so the verdict is "check", never "no".
  const types = facts.entity_types;
  if (types && Array.isArray(types.value) && types.value.length > 0) {
    const kinds = types.value.map(String);
    if (!p.orgType) lines.push({ key: 'entity', label: 'Who may apply', verdict: 'check', reason: `The call names who may apply: ${kinds.join('; ')}. Check that your organisation is one of them.`, quote: types.quote });
    else if (!kinds.some((k) => covers(p.orgType as OrgType, k))) lines.push({ key: 'entity', label: 'Who may apply', verdict: 'check', reason: `The call names who may apply: ${kinds.join('; ')}. Nothing in that list says a company like yours may. Check the document before you go on.`, quote: types.quote });
    else lines.push(withNote({ key: 'entity', label: 'Who may apply', verdict: 'yes', reason: `The call names who may apply (${kinds.join('; ')}) and your organisation is covered by it.`, quote: types.quote }, types));
  }

  const c = facts.eligible_countries;
  if (c && p.country) {
    const text = String(c.value);
    const eu = /member states|\bunion\b|\bEU\b/i.test(text);
    let line: Line;
    if (eu && EU27.has(p.country)) line = { key: 'country', label: 'Country', verdict: 'yes', reason: 'An EU Member State is eligible under this call.', quote: c.quote };
    else if (eu && EEA_EXTRA.has(p.country) && /EEA/i.test(text)) line = { key: 'country', label: 'Country', verdict: 'yes', reason: 'EEA countries are eligible under this call.', quote: c.quote };
    else if (EU27.has(p.country)) line = { key: 'country', label: 'Country', verdict: 'check', reason: 'The document lists the eligible countries in its own words, and they are not simply the Member States. Check that your country is among them.', quote: c.quote };
    else line = { key: 'country', label: 'Country', verdict: 'check', reason: 'Your country is not an EU Member State. Check the list of eligible and associated countries in the document.', quote: c.quote };
    lines.push(withNote(line, c));
  }

  const sme = facts.sme_only;
  if (sme && p.orgType) {
    if (sme.value === true && p.orgType !== 'sme') lines.push({ key: 'sme', label: 'Organisation size', verdict: 'no', reason: 'The call is reserved for SMEs.', quote: sme.quote });
    else if (sme.value === true) lines.push(withNote({ key: 'sme', label: 'Organisation size', verdict: 'yes', reason: 'The call is reserved for SMEs and you are one.', quote: sme.quote }, sme));
    else lines.push(withNote({ key: 'sme', label: 'Organisation size', verdict: 'yes', reason: 'The call is not reserved for SMEs.', quote: sme.quote }, sme));
  }

  const np = facts.natural_persons_allowed;
  if (np && p.orgType === 'individual') {
    if (np.value === false) {
      lines.push({ key: 'person', label: 'Natural person', verdict: np.note ? 'check' : 'no', reason: np.note ? `Natural persons are not eligible, with an exception: ${np.note}` : 'Natural persons are not eligible.', quote: np.quote });
    } else lines.push(withNote({ key: 'person', label: 'Natural person', verdict: 'yes', reason: 'Natural persons may apply.', quote: np.quote }, np));
  }

  const cons = facts.consortium_required;
  if (cons && p.hasPartners) {
    const n = facts.min_entities?.value;
    const k = facts.min_countries?.value;
    const need = `${typeof n === 'number' ? `at least ${n} legal entities` : 'a consortium'}${typeof k === 'number' ? ` from at least ${k} countries` : ''}`;
    if (cons.value === true && p.hasPartners === 'yes') lines.push(withNote({ key: 'consortium', label: 'Partners', verdict: 'yes', reason: `A consortium is required: ${need}.`, quote: cons.quote }, cons));
    else if (cons.value === true) lines.push({ key: 'consortium', label: 'Partners', verdict: 'check', reason: `A consortium is required: ${need}. You would need to find partners first.`, quote: cons.quote });
    else if (typeof n === 'number' && n >= 2) lines.push({ key: 'consortium', label: 'Partners', verdict: 'check', reason: `The call says no consortium is required, and also asks for at least ${n} legal entities${typeof k === 'number' ? ` from at least ${k} countries` : ''}. Check the document before you go on.${cons.note ? ` ${cons.note}` : ''}`, quote: cons.quote });
    else {
      const condition = singleApplicantCondition(facts);       // a note on the consortium fact itself is shown by `withNote`
      lines.push(condition
        ? { key: 'consortium', label: 'Partners', verdict: 'check', reason: `No consortium is required, but ${condition.charAt(0).toLowerCase()}${condition.slice(1)}`, quote: cons.quote }
        : withNote({ key: 'consortium', label: 'Partners', verdict: 'yes', reason: 'No consortium is required.', quote: cons.quote }, cons));
    }
  }

  const own = facts.ownership_control_restriction;
  if (own && p.controlledAbroad) {
    if (own.value !== true) lines.push(withNote({ key: 'control', label: 'Ownership control', verdict: 'yes', reason: 'No ownership control restriction is stated.', quote: own.quote }, own));
    else if (p.controlledAbroad === 'yes') {
      // "No" only for a restriction the document states without a way round it. A guarantee, a screening, an exemption or a
      // narrower scope in its note or sentence makes it "check", with that wording shown.
      const way = `${own.note ?? ''} ${own.quote}`;
      lines.push(EXCEPTION.test(way)
        ? { key: 'control', label: 'Ownership control', verdict: 'check', reason: `The call restricts entities controlled from outside the eligible countries, but the document allows a way round or narrows the restriction${own.note ? `: ${own.note}` : ''}. Read it before you decide.`, quote: own.quote }
        : { key: 'control', label: 'Ownership control', verdict: 'no', reason: 'Entities controlled from outside the eligible countries are excluded, and the document names no exception.', quote: own.quote });
    }
    else if (p.controlledAbroad === 'unsure') lines.push({ key: 'control', label: 'Ownership control', verdict: 'check', reason: 'Entities controlled from outside the eligible countries are excluded. Find out who controls your company.', quote: own.quote });
    else lines.push(withNote({ key: 'control', label: 'Ownership control', verdict: 'yes', reason: 'The restriction applies, and your company is not controlled from outside the eligible countries.', quote: own.quote }, own));
  }

  // A general rule of the work programme annexes is neither a firm "no" nor a plain "yes": the topic may change it.
  const settled = lines.map((l): Line => {
    if (facts[LINE_FACT[l.key] ?? '']?.scope !== 'general') return l;
    if (l.verdict === 'no') return { ...l, verdict: 'check', reason: `${l.reason} This is the work programme's general rule; the topic may differ, so check its own conditions.` };
    if (l.verdict === 'yes') return { ...l, verdict: 'check', reason: `${l.reason} This is the work programme's general rule, and the topic may add conditions: check its own.` };
    return l;
  });
  return { verdict: settled.reduce<Verdict>((v, l) => worst(v, l.verdict), 'yes'), lines: settled };
}

/** The fact each line of the verdict rests on. */
export const LINE_FACT: Record<string, string> = {
  country: 'eligible_countries', sme: 'sme_only', person: 'natural_persons_allowed',
  consortium: 'consortium_required', control: 'ownership_control_restriction', entity: 'entity_types',
};

export const SCOPE_WORDS = { call_document: 'Call document', general: 'General rule (work programme annexes)', topic: 'This topic' } as const;
