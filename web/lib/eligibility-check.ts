/**
 * "Can you apply?" for one call: the facts read from its call document (API `documentEligibility`)
 * against a few answers typed in the browser. Nothing here leaves the page.
 *
 * Rules of the verdict, all conservative: a "no" only where the document plainly excludes the
 * answer; a "yes" only where every applicable fact allows it and carries no condition; everything
 * else is "check", with the reason and the document's own sentence beside it. A fact that was
 * not read, or whose quote was not found in the document, is never in the data (the API drops it).
 */
import { plural } from './format';

export interface EligibilityFact {
  value: unknown; note?: string | null; quote: string; confidence: number;
  /** Where it was read: the call document, the work programme's general annexes (a rule the topic may change), or the topic's own text. */
  scope?: 'call_document' | 'general' | 'topic';
}
export type EligibilityFacts = Record<string, EligibilityFact | undefined>;

export type OrgType = 'sme' | 'large' | 'public' | 'university' | 'individual';
export type Tri = 'yes' | 'no' | 'unsure';
/**
 * What only the saved profile of the readiness check knows (WP-53, T21). The form on the call page leaves it out, and every line then
 * reads as before: a note stays a condition, and a condition on partners stays a "check".
 */
export interface More {
  /** The legal form was answered "a legal person". */
  legalPerson: boolean;
  /** The applicant kind was answered "a company or a research body". */
  company: boolean;
  /** Where the executive management is, '' while not answered. */
  managementCountry: string;
  uaOccupied: Tri | '';
  /** A legal entity established in Ukraine takes part in the planned consortium. */
  uaPartner: Tri | '';
  /** A SEAP takes part in the planned consortium. */
  seapPartner: Tri | '';
}

export interface Profile {
  country: string;            // ISO 3166-1 alpha-2, '' when not chosen
  orgType: OrgType | '';
  hasPartners: Tri | '';
  controlledAbroad: Tri | '';
  more?: More;
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

/**
 * "No consortium is required" next to a smallest number of entities or countries above one contradicts itself (call 193 of
 * 18 October 2026: "No" and "at least 4 countries"; the note says a single applicant is allowed only in one case). The page
 * must not print the bare "No": it says the document is unclear and where the numbers are.
 */
export function consortiumUnclear(facts: EligibilityFacts): boolean {
  if (facts.consortium_required?.value !== false) return false;
  const n = facts.min_entities?.value;
  const k = facts.min_countries?.value;
  return (typeof n === 'number' && n >= 2) || (typeof k === 'number' && k >= 2);
}

export function unclearConsortiumText(facts: EligibilityFacts): string {
  const n = facts.min_entities?.value;
  const k = facts.min_countries?.value;
  const asks = [typeof n === 'number' && n >= 2 ? `at least ${n} legal entities` : null, typeof k === 'number' && k >= 2 ? `at least ${k} countries` : null].filter(Boolean).join(' and ');
  return `it says no consortium is required and also asks for ${asks}.`;
}

/** The value of a fact as the page prints it: the bare words, except where they would mislead (see `consortiumUnclear`). */
export function factDisplay(key: string, facts: EligibilityFacts): string {
  const f = facts[key];
  if (!f) return '';
  if (key === 'consortium_required' && consortiumUnclear(facts)) return `The document is unclear, read it: ${unclearConsortiumText(facts)}`;
  // WP-91 (UX audit 6): never a bare "No" when a single applicant must meet a condition or a partner from one country is asked
  // (the Ukraine Support Instrument: a single applicant must be Ukrainian, so from Poland a Ukrainian partner is needed).
  if (key === 'consortium_required' && f.value === false) {
    const single = singleApplicantCondition(facts);
    if (single) return `Not for every applicant. ${single}`;
    if (partnerNeeds(facts).ukraine) return `Not for every applicant: ${ownNote(f)}`;
  }
  return factText(f);
}

const worst = (a: Verdict, b: Verdict): Verdict => (a === 'no' || b === 'no' ? 'no' : a === 'check' || b === 'check' ? 'check' : 'yes');

function withNote(line: Line, fact: EligibilityFact | undefined, note: string = ownNote(fact)): Line {
  // The note without the words that only say where the fact was read (`ownNote`): "Stated in this topic's own conditions." is no condition (V3-B: it
  // turned every "yes" read from a topic's own text into a "check"; 59 of the 185 stored readings are of that kind).
  if (line.verdict === 'yes' && note) return { ...line, verdict: 'check', reason: `${line.reason} A condition applies: ${note}` };
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

/** The kinds a call names when every one of them is a size class below "large" (call 131: "SME company", "Small mid-cap company (up to 499 employees)"), else null. */
export function smallKindsOnly(facts: EligibilityFacts): string[] | null {
  const v = facts.entity_types?.value;
  if (!Array.isArray(v) || v.length === 0) return null;
  const kinds = v.map(String);
  return kinds.every((k) => SMALL_ONLY.test(k) && !/\blarge\b/i.test(k)) ? kinds : null;
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

// ---------------------------------------------------------------- notes that do not concern the profile, and conditions on partners (WP-53, T21)

/** The sentences of a note. */
const sentencesOf = (note: string): string[] => (note.match(/[^.;!?]+[.;!?]*/g) ?? []).map((s) => s.trim()).filter(Boolean);

/**
 * The note of a "Who may apply" fact without the sentences that are exceptions for kinds of applicant the saved profile is plainly not
 * (call 118: "Entities without legal personality may exceptionally participate ... International organisations are eligible only if ...").
 * A sentence goes only when it names such kinds and every kind it names is one the profile excludes; anything else stays a condition.
 */
export function entityNote(fact: EligibilityFact | undefined, more: More | undefined): string {
  const note = ownNote(fact);
  if (!more) return note;
  return sentencesOf(note).filter((s) => {
    if (s.length > 260 || /companies|company (?:must|shall|with|that|of|has)\b|enterprise|\bSMEs?\b|employee|turnover|private|your/i.test(s)) return true;
    const kinds = [
      /natural persons?|sole traders?|self-employed|without (?:a )?(?:separate )?legal personality/i.test(s) ? more.legalPerson : null,
      /international organisations?/i.test(s) ? more.company : null,
      /\bSEAPs?\b/.test(s) ? more.company : null,
    ].filter((k) => k !== null);
    return kinds.length === 0 || kinds.includes(false);
  }).join(' ');
}

/**
 * The note of an "Eligible countries" fact without what the saved profile answers: the non-government-controlled areas of Ukraine (nothing for
 * a company established elsewhere, or that said it is not in one), and "executive management established in an eligible country" (met when
 * the executive management is in a country the fact names).
 */
export function countryNote(fact: EligibilityFact | undefined, country: string, more: More | undefined): string {
  const note = ownNote(fact);
  if (!more || !fact) return note;
  const text = String(fact.value);
  const m = more.managementCountry;
  const named = m !== '' && ((/member states|\bunion\b|\bEU\b/i.test(text) && EU27.has(m)) || (EEA_EXTRA.has(m) && /EEA/i.test(text)) || (m === 'UA' && /ukrain/i.test(text)));
  return sentencesOf(note).filter((s) => {
    if (/non-government[- ]controlled areas? of Ukraine/i.test(s)) return !(country !== '' && (country !== 'UA' || more.uaOccupied === 'no'));
    if (/executive management structures? (?:\w+ ){0,4}established in an eligible country/i.test(s)) return !named;
    return true;
  }).join(' ');
}

type PartnerKind = 'ukraine' | 'seap' | 'harmless' | 'other';

/** What one sentence of a note on the consortium or the single applicant asks of the partners, when it is one of the two conditions the profile can answer. */
export function partnerKind(sentence: string): PartnerKind {
  if (/^this is the minimum for the topic[.;]?$/i.test(sentence)) return 'harmless';
  if (/\bukrain/i.test(sentence) && /single applicant|consorti|must include/i.test(sentence) && /established|executive management/i.test(sentence)) return 'ukraine';
  if (/\bSEAPs?\b/.test(sentence) && /(?:no|without a) SEAP (?:participates|takes part)|unless a SEAP (?:participates|takes part)/i.test(sentence)) return 'seap';
  return 'other';
}

/**
 * The conditions on partners that a call's notes state: an entity established in Ukraine (calls 118, 113), or a SEAP unless three independent
 * entities take part (calls 116, 117, 118). `other`: a note on the single applicant or the consortium says something else, which the profile cannot answer.
 */
export function partnerNeeds(facts: EligibilityFacts): { ukraine: boolean; seap: boolean; other: boolean } {
  const out = { ukraine: false, seap: false, other: false };
  for (const key of ['single_applicant_allowed', 'consortium_required', 'min_entities', 'min_countries'] as const) {
    for (const s of sentencesOf(ownNote(facts[key]))) {
      const k = partnerKind(s);
      if (k === 'ukraine' || k === 'seap') out[k] = true;
      else if (k === 'other' && (key === 'single_applicant_allowed' || key === 'consortium_required')) out.other = true;
    }
  }
  return out;
}

/**
 * The "Partners" line for a call whose document attaches a condition to who applies with whom (`consortiumCondition`). "Check", as before, unless
 * every condition is one of the two the saved profile can answer and its answers meet it: then "yes", and the line says which answers did.
 * Never "no": a partner can be found.
 */
export function partnerLine(facts: EligibilityFacts, p: Profile): Line | null {
  const base = consortiumCondition(facts);
  if (!base) return null;
  const quote = (facts.consortium_required ?? facts.single_applicant_allowed)?.quote;
  const needs = partnerNeeds(facts);
  const more = p.more;
  if (!more || needs.other || (!needs.ukraine && !needs.seap)) return { key: 'consortium', label: 'Partners', verdict: 'check', reason: base, quote };
  const met: string[] = [];
  const unmet: string[] = [];
  if (needs.ukraine) {
    // the call asks for an entity established in Ukraine with its executive management structure there: a Ukrainian company is that entity only if it says so
    if (p.country === 'UA' && more.managementCountry === 'UA') met.push('your company is established in Ukraine, with its executive management there');
    else if (more.uaPartner === 'yes' && p.country !== 'UA') met.push('you said a legal entity established in Ukraine takes part in your consortium');
    else if (p.country === 'UA') unmet.push('Your answers do not place your executive management in Ukraine.');
    else unmet.push(more.uaPartner === 'no' ? 'You said no legal entity established in Ukraine takes part in your consortium.' : 'Your answers do not say whether a legal entity established in Ukraine takes part in your consortium.');
  }
  if (needs.seap) {
    if (more.seapPartner === 'yes') met.push('you said a SEAP takes part in your consortium');
    else unmet.push(more.seapPartner === 'no' ? 'You said no SEAP takes part in your consortium.' : 'Your answers do not say whether a SEAP takes part in your consortium.');
  }
  if (unmet.length > 0) return { key: 'consortium', label: 'Partners', verdict: 'check', reason: `${base} ${unmet.join(' ')}`, quote };
  return { key: 'consortium', label: 'Partners', verdict: 'yes', reason: `The call attaches conditions to who applies with whom, and your answers meet them: ${met.join('; ')}.`, quote };
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
    else lines.push(withNote({ key: 'entity', label: 'Who may apply', verdict: 'yes', reason: `The call names who may apply (${kinds.join('; ')}) and your organisation is covered by it.`, quote: types.quote }, types, entityNote(types, p.more)));
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
    lines.push(withNote(line, c, countryNote(c, p.country, p.more)));
  }

  const sme = facts.sme_only;
  if (sme && p.orgType) {
    if (sme.value === true && p.orgType !== 'sme') lines.push({ key: 'sme', label: 'Organisation size', verdict: 'no', reason: 'The call is reserved for SMEs.', quote: sme.quote });
    else if (sme.value === true) lines.push(withNote({ key: 'sme', label: 'Organisation size', verdict: 'yes', reason: 'The call is reserved for SMEs and you are one.', quote: sme.quote }, sme));
    else if (p.orgType === 'large' && smallKindsOnly(facts)) {
      // The flag says "not reserved for SMEs" (small mid-caps are also eligible), but the call names no kind bigger than that: the same
      // "check" as the "Who may apply" line, in words that do not contradict it (V3-B, call 131).
      lines.push({ key: 'sme', label: 'Organisation size', verdict: 'check', reason: `The call names only these kinds of applicant: ${smallKindsOnly(facts)!.join('; ')}. It does not name a large company, so check your size class against the document before you go on.`, quote: sme.quote });
    } else lines.push(withNote({ key: 'sme', label: 'Organisation size', verdict: 'yes', reason: 'The call is not reserved for SMEs.', quote: sme.quote }, sme));
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
    const need = `${typeof n === 'number' ? `at least ${n} ${plural(n, 'legal entity', 'legal entities')}` : 'a consortium'}${typeof k === 'number' ? ` from at least ${k} ${plural(k, 'country', 'countries')}` : ''}`;
    if (cons.value === true && p.hasPartners === 'yes') lines.push(withNote({ key: 'consortium', label: 'Partners', verdict: 'yes', reason: `A consortium is required: ${need}.`, quote: cons.quote }, cons));
    else if (cons.value === true) lines.push({ key: 'consortium', label: 'Partners', verdict: 'check', reason: `A consortium is required: ${need}. You would need to find partners first.`, quote: cons.quote });
    else if (consortiumUnclear(facts)) lines.push({ key: 'consortium', label: 'Partners', verdict: 'check', reason: `The document is unclear: ${unclearConsortiumText(facts)} Check the document before you go on.${cons.note ? ` ${cons.note}` : ''}`, quote: cons.quote });
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
    else {
      // A note that describes a way round the restriction (a guarantee, an exemption, a screening) is about entities that are controlled from
      // outside: it is no condition on a company that says it is not (V3-B: 4 of the 14 "check" lines of the four EDIP/USI calls open to a company).
      const line: Line = { key: 'control', label: 'Ownership control', verdict: 'yes', reason: 'The restriction applies, and your company is not controlled from outside the eligible countries.', quote: own.quote };
      lines.push(EXCEPTION.test(ownNote(own)) ? line : withNote(line, own));
    }
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
