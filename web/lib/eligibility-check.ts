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
  /**
   * Where it was read: the call document, the work programme's general annexes (a rule the topic may change), the topic's own text, or
   * (WP-93) `programme`: the EIC work programme's section for this scheme, read for this topic, which is the scheme's own call text.
   */
  scope?: 'call_document' | 'general' | 'topic' | 'programme';
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

/** WP-93: what the organisation is, from the saved profile (the form of the call page has its own `orgType`). */
export type OrgKind = 'company' | 'university' | 'research' | 'public' | '';
/** WP-93: who controls a company that is controlled from outside the EU: Ukraine, an EEA EFTA state, China, Russia or Belarus, another country. */
export type Controller = 'ua' | 'eea' | 'cn' | 'ru_by' | 'other_non_eu' | '';
/** WP-93: the staff count the size rules read, as a range: the group's where the company is part of one, open above while that is not known. */
export interface Headcount { min: number; max: number }

export interface Profile {
  country: string;            // ISO 3166-1 alpha-2, '' when not chosen
  orgType: OrgType | '';
  hasPartners: Tri | '';
  controlledAbroad: Tri | '';
  more?: More;
  /** WP-93, from the saved profile only (absent on the form of the call page, which then reads as before). */
  kind?: OrgKind;
  size?: Headcount;
  controller?: Controller;
  /** A pre-commitment of a qualified investor for at least 20 % of the funding round (EIC STEP). */
  investor?: Tri | '';
}

/** WP-93: the call a check is for, so that "countries associated to the programme" can be read (lib/fit.ts `programmesOfCall` words). */
export interface CallContext { programme: string; topic: string }

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
  // WP-93: read deterministically from the stored text (backend/dgate/rule_readings.py), or moved from "Who may apply" (eligibility.py)
  designated_applicants: 'Only these may apply',
  required_partners: 'Required in the consortium',
  investor_precommitment: 'Investor pre-commitment required',
  max_group_headcount: 'Largest staff count (with the group)',
  staff_nationality: 'Nationality of the staff',
};

// ---------------------------------------------------------------- WP-93: countries, association, size, control

const EU_WORDS = /member states?|\bunion\b|\bEU\b/i;
/** Words that open a list of countries beyond the ones it names: such a list is not closed. */
const OPEN_LIST = /associated|third[- ]countr|any (?:legal )?(?:entity|entities|country|countries)|regardless|other countries|middle[- ]income|international organi/i;
/** Countries a list may name one by one (the EIC, Bridging and EDIP lists of 2026), as the documents write them. */
const NAMED: [RegExp, string][] = [
  [/\bnorway\b/i, 'NO'], [/\biceland\b/i, 'IS'], [/\bliechtenstein\b/i, 'LI'], [/\bukrain/i, 'UA'], [/\bswitzerland\b/i, 'CH'],
  [/united kingdom/i, 'GB'], [/\bcanada\b/i, 'CA'], [/\bisrael\b/i, 'IL'], [/\bkorea\b/i, 'KR'], [/new[- ]zealand/i, 'NZ'], [/\bjapan\b/i, 'JP'],
  [/t[üu]rkiye|\bturkey\b/i, 'TR'], [/\bmoldova\b/i, 'MD'], [/\balbania\b/i, 'AL'], [/\bserbia\b/i, 'RS'], [/\bmontenegro\b/i, 'ME'],
  [/north macedonia/i, 'MK'], [/\bgeorgia\b/i, 'GE'], [/\barmenia\b/i, 'AM'], [/\btunisia\b/i, 'TN'], [/faroe/i, 'FO'], [/bosnia/i, 'BA'], [/kosovo/i, 'XK'],
];
/** The countries an eligible-country text names one by one (an EU Member State is not listed here). */
export function namedCountries(text: string): Set<string> {
  return new Set(NAMED.filter(([re]) => re.test(text)).map(([, code]) => code));
}

/**
 * The countries associated to a programme, where a text we hold says so (WP-93, fix 1). `yes`: associated; `no`: stated not to be; any
 * other country stays a question for the document. Sources: Horizon Europe, the general annexes of the 2026-2027 work programme (Annex A,
 * the countries associated; the EEA EFTA states Iceland and Norway, and Ukraine: backend/dgate/ukraine.py HORIZON_ANNEX); the EDIP
 * Programme, the call documents of 2026 ("EDIP associated countries (i.e. Norway)", call EDF-EDIP-P-2027-FNLC-CPA) and Regulation (EU)
 * 2025/2643, Articles 9(1) and 2 for Ukraine (ukraine.py EDIP_RECIPIENTS); the EDF, Regulation (EU) 2021/697, Article 5 (the EEA EFTA
 * state Norway; Ukraine pending its agreement, ukraine.py EDF_PENDING, so not listed either way).
 */
export const ASSOCIATED: Record<string, { name: string; yes: string[]; no: string[] }> = {
  HORIZON: { name: 'Horizon Europe', yes: ['IS', 'NO', 'UA'], no: [] },
  EDIP: { name: 'the EDIP Programme', yes: ['NO'], no: ['UA'] },
  EDF: { name: 'the European Defence Fund', yes: ['NO'], no: [] },
};

/** The programme whose association a call's country text refers to: named in the text itself, else the call's own. */
export function associationOf(text: string, ctx?: CallContext): string | null {
  if (/associated to (?:the )?horizon/i.test(text)) return 'HORIZON';
  if (/associated to the EDIP|EDIP associated/i.test(text)) return 'EDIP';
  if (!ctx) return null;
  const t = ctx.topic.toUpperCase().split('-');
  if (t.includes('EDIP')) return t[t.indexOf('EDIP') + 1] === 'USI' ? null : 'EDIP';
  return ASSOCIATED[ctx.programme] ? ctx.programme : null;
}

/**
 * Whether a country is eligible under a call's eligible-country text: 'yes', 'no' or 'check', with the reason (WP-93, fix 1). A list is
 * closed, and a country outside it is a "no", only when it is the call's own (not the general annexes'), names the Member States and some
 * other country or the EEA one by one, and says nothing that opens it (associated or third countries, any country): the Digital Europe
 * cybersecurity calls, the Ukraine Support Instrument, the Bridging topic of Horizon Europe. A list of the Member States alone may be a
 * model's short reading of a longer one, so it stays a "check" for any other country, as before.
 */
export function countryStatus(fact: EligibilityFact, country: string, ctx?: CallContext): { verdict: Verdict; reason: string } {
  const text = String(fact.value);
  const eu = EU_WORDS.test(text);
  const named = namedCountries(text);
  const eeaAssociatedOnly = /EEA (?:member|countr\w*|state\w*) associated/i.test(text);
  const eeaAll = /\bEEA\b/.test(text) && !eeaAssociatedOnly;
  const assoc = associationOf(text, ctx);
  const list = assoc ? ASSOCIATED[assoc] : null;
  const opensToAssociated = /(?<!non-)associated/i.test(text);
  if (eu && EU27.has(country)) return { verdict: 'yes', reason: 'An EU Member State is eligible under this call.' };
  if (EEA_EXTRA.has(country) && eeaAll) return { verdict: 'yes', reason: 'EEA countries are eligible under this call.' };
  if (named.has(country)) return { verdict: 'yes', reason: `Your country is named among the eligible countries.` };
  if (opensToAssociated && list?.yes.includes(country)) return { verdict: 'yes', reason: `Your country is associated to ${list.name}, and the call is open to the associated countries.` };
  if (opensToAssociated && list?.no.includes(country)) return { verdict: 'no', reason: `Your country is not associated to ${list.name}, and the call is open only to the Member States and the associated countries it names.` };
  if (fact.scope !== 'general' && eu && !OPEN_LIST.test(text) && (named.size > 0 || /\bEEA\b/.test(text))) {
    return { verdict: 'no', reason: `The call lists the countries where applicants must be established (${text}), and your country is not among them.` };
  }
  if (EU27.has(country)) return { verdict: 'check', reason: 'The document lists the eligible countries in its own words, and they are not simply the Member States. Check that your country is among them.' };
  if (opensToAssociated && list) return { verdict: 'check', reason: `Your country is not an EU Member State. The call is open to countries associated to ${list.name}: check whether yours is one.` };
  return { verdict: 'check', reason: 'Your country is not an EU Member State. Check the list of eligible and associated countries in the document.' };
}

/** A headcount band of the profile as a range (lib/profile.ts `HEADCOUNT_BANDS`). */
export const BAND_RANGE: Record<string, Headcount> = {
  lt50: { min: 0, max: 49 }, '50_249': { min: 50, max: 249 }, '250_499': { min: 250, max: 499 },
  '500_1999': { min: 500, max: 1999 }, '2000plus': { min: 2000, max: Infinity },
};

/**
 * The size limit a call sets (WP-93, fix 2): SMEs (fewer than 250 staff), or SMEs and small mid-caps (up to 499), counted as the SME
 * definition counts them, with linked enterprises (Commission Recommendation 2003/361/EC, Articles 3 to 6; EIC work programme 2026,
 * footnote 39). `midcap`: a reserved-for-SMEs call that lets a small mid-cap apply on a condition, in the call's words.
 */
export function sizeRule(facts: EligibilityFacts): { limit: 249 | 499; midcap: string | null; fact: EligibilityFact; words: string } | null {
  const sme = facts.sme_only;
  if (sme?.value === true) {
    const note = ownNote(sme);
    return { limit: 249, midcap: /mid-?\s?caps?/i.test(note) ? note : null, fact: sme, words: 'SMEs' };
  }
  const kinds = smallKindsOnly(facts);
  if (kinds && facts.entity_types) {
    const mid = kinds.some((k) => /mid-?\s?caps?/i.test(k));
    return { limit: mid ? 499 : 249, midcap: null, fact: facts.entity_types, words: mid ? 'SMEs and small mid-caps (up to 499 staff)' : 'SMEs' };
  }
  return null;
}

const staff = (h: Headcount) => (h.max === Infinity ? `${h.min} or more` : `${h.min} to ${h.max}`);

/** The staff-count line of a size limit, from the profile's range; null where the profile gives none (the form of the call page). */
function sizeLine(rule: NonNullable<ReturnType<typeof sizeRule>>, h: Headcount): Line {
  const base = { key: 'sme', label: 'Organisation size', quote: rule.fact.quote };
  const limit = rule.limit;
  if (h.max <= 249) return withNote({ ...base, verdict: 'yes', reason: `The call is for ${rule.words}, and your staff count, counted with your group, is under 250.` }, rule.fact);
  if (limit === 499 && h.max <= 499) return { ...base, verdict: 'yes', reason: `The call is for ${rule.words}, and your staff count, counted with your group, is at most 499.` };
  if (limit === 249 && rule.midcap && h.min >= 250 && h.max <= 499) {
    return { ...base, verdict: 'check', reason: `The call is reserved for SMEs; a company of 250 to 499 staff is a small mid-cap, which may apply only on a condition: ${rule.midcap}` };
  }
  if (h.min > (rule.midcap ? 499 : limit)) {
    return { ...base, verdict: 'no', reason: `The call is for ${rule.words}${rule.midcap ? ' (small mid-caps up to 499 staff on a condition)' : ''}, counted with the staff of linked enterprises, and your answers give ${staff(h)} staff.` };
  }
  return { ...base, verdict: 'check', reason: `The call is for ${rule.words}, counted with the staff of linked enterprises. Your answers do not settle it (${staff(h)} staff): say whether you are part of a group, and its staff count.` };
}

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

export function check(facts: EligibilityFacts, p: Profile, ctx?: CallContext): Result {
  const lines: Line[] = [];
  const midcapCovered = (k: string) => p.orgType === 'large' && p.size !== undefined && p.size.max <= 499 && /mid-?\s?caps?/i.test(k);

  // Who may apply: a call that names the kinds of applicant it is open to is not open to a profile that is not
  // plainly one of them (call 78 of 17 October 2026: an EDIC or a government-appointed mechanism only). A list is read
  // as possibly partial, so the verdict is "check", never "no".
  const types = facts.entity_types;
  if (types && Array.isArray(types.value) && types.value.length > 0) {
    const kinds = types.value.map(String);
    if (!p.orgType) lines.push({ key: 'entity', label: 'Who may apply', verdict: 'check', reason: `The call names who may apply: ${kinds.join('; ')}. Check that your organisation is one of them.`, quote: types.quote });
    else if (!kinds.some((k) => covers(p.orgType as OrgType, k) || midcapCovered(k))) lines.push({ key: 'entity', label: 'Who may apply', verdict: 'check', reason: `The call names who may apply: ${kinds.join('; ')}. Nothing in that list says a company like yours may. Check the document before you go on.`, quote: types.quote });
    else lines.push(withNote({ key: 'entity', label: 'Who may apply', verdict: 'yes', reason: `The call names who may apply (${kinds.join('; ')}) and your organisation is covered by it.`, quote: types.quote }, types, entityNote(types, p.more)));
  }

  // WP-93 (fix 4): a call open only to designated bodies (National Cyber Hubs, National Coordination Centres) is a "no" for anybody who is
  // not one, unless the document lets others join a consortium with them: then it is the condition to check.
  const designated = facts.designated_applicants;
  if (designated && p.country) {
    const who = String(designated.value);
    const note = ownNote(designated);
    const partners = /partners?|in (?:a )?consortium with|may (?:also )?join/i.test(note);
    lines.push(partners
      ? { key: 'designated', label: 'Only these may apply', verdict: 'check', reason: `Only ${who} may apply; anybody else can take part only as a partner in a consortium with one. ${note}`, quote: designated.quote }
      : { key: 'designated', label: 'Only these may apply', verdict: p.kind === 'public' || p.orgType === 'public' ? 'check' : 'no', reason: `Only ${who} may apply. You are not eligible unless your organisation is one.`, quote: designated.quote });
  }
  // WP-93 (fix 9): "at least 2 Border or Coast Guard Authorities as beneficiaries" is who must be in the consortium, not who may apply.
  const required = facts.required_partners;
  if (required && p.country) {
    lines.push({ key: 'required', label: 'Required in the consortium', verdict: 'check', reason: `The consortium must include ${String(required.value)}. You can take part together with them.`, quote: required.quote });
  }

  const c = facts.eligible_countries;
  if (c && p.country) {
    const s = countryStatus(c, p.country, ctx);
    const line: Line = { key: 'country', label: 'Country', verdict: s.verdict, reason: s.reason, quote: c.quote };
    lines.push(s.verdict === 'no' ? line : withNote(line, c, countryNote(c, p.country, p.more)));
  }
  // WP-99: the Ukraine Support Instrument excludes the non-government controlled areas of Ukraine (Regulation (EU) 2025/2643, Article 26(1));
  // for Horizon Europe (and its EIC) no text we hold says whether Ukraine's association covers them. Said, not left in silence.
  if (p.country === 'UA' && p.more?.uaOccupied === 'yes' && ctx?.programme === 'HORIZON') {
    lines.push({ key: 'territory', label: 'Non-government controlled areas', verdict: 'check',
      reason: 'You said your company is established in a non-government controlled area of Ukraine. Whether the association of Ukraine to Horizon Europe covers those areas is not checked here: no text we hold says so. Ask the National Contact Point or the call’s helpdesk before you apply.' });
  }

  const rule = sizeRule(facts);
  const sme = facts.sme_only;
  // WP-93 (fix 2): SMEs and small mid-caps are companies; a university or a public body is not one.
  if (rule && (p.kind === 'university' || p.kind === 'public' || (p.kind === undefined && p.orgType === 'public'))) {
    lines.push({ key: 'sme', label: 'Organisation size', verdict: 'no', reason: `The call is for companies: ${rule.words}. ${p.kind === 'university' ? 'A university' : 'A public body'} is not one.`, quote: rule.fact.quote });
  } else if (rule && p.kind === 'research') {
    lines.push({ key: 'sme', label: 'Organisation size', verdict: 'check', reason: `The call is for companies: ${rule.words}. A research organisation may apply only if it is such an enterprise.`, quote: rule.fact.quote });
  } else if (rule && p.size) {
    lines.push(sizeLine(rule, p.size));
  } else if (sme && p.orgType) {
    if (sme.value === true && p.orgType !== 'sme' && rule?.midcap && p.orgType === 'large') lines.push({ key: 'sme', label: 'Organisation size', verdict: 'check', reason: `The call is reserved for SMEs; a small mid-cap (up to 499 staff) may apply only on a condition: ${rule.midcap}`, quote: sme.quote });
    else if (sme.value === true && p.orgType !== 'sme') lines.push({ key: 'sme', label: 'Organisation size', verdict: 'no', reason: 'The call is reserved for SMEs.', quote: sme.quote });
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
      const ctl = p.controller ?? '';
      const kind = controlKind(way);
      const fromEligible = controllerEligible(c, ctl, ctx);
      const line = (verdict: Verdict, reason: string): Line => ({ key: 'control', label: 'Ownership control', verdict, reason, quote: own.quote });
      // WP-93 (fixes 3 and 8): who controls the company decides a restriction that names one country, or that the controlling country meets.
      if (fromEligible) lines.push(line('yes', `The call restricts control from outside the eligible countries, and your company is controlled from ${ctl === 'ua' ? 'Ukraine' : 'an EEA EFTA state'}, which is eligible under it.`));
      else if (kind === 'china_only' && ctl === 'cn') lines.push(line('no', 'Entities controlled by China, or by a legal entity established in China, are not eligible under this call, and you said your company is controlled from China.'));
      else if (kind === 'china_only' && ctl !== '') lines.push(line('yes', 'The restriction concerns control by China only, and you said your company is controlled from another country.'));
      else if (kind === 'china_no_guarantee' && ctl === 'cn') lines.push(line('no', 'Entities controlled from outside the eligible countries may take part only with guarantees, and the call says entities controlled by China cannot submit guarantees.'));
      else lines.push(EXCEPTION.test(way)
        ? line('check', `The call restricts entities controlled from outside the eligible countries, but the document allows a way round or narrows the restriction${own.note ? `: ${own.note}` : ''}. Read it before you decide.`)
        : line('no', 'Entities controlled from outside the eligible countries are excluded, and the document names no exception.'));
    }
    else if (p.controlledAbroad === 'unsure') lines.push({ key: 'control', label: 'Ownership control', verdict: 'check', reason: 'Entities controlled from outside the eligible countries are excluded. Find out who controls your company.', quote: own.quote });
    else {
      // A note that describes a way round the restriction (a guarantee, an exemption, a screening) is about entities that are controlled from
      // outside: it is no condition on a company that says it is not (V3-B: 4 of the 14 "check" lines of the four EDIP/USI calls open to a company).
      const line: Line = { key: 'control', label: 'Ownership control', verdict: 'yes', reason: 'The restriction applies, and your company is not controlled from outside the eligible countries.', quote: own.quote };
      lines.push(EXCEPTION.test(ownNote(own)) ? line : withNote(line, own));
    }
  }

  // WP-93 (fix 2, EIC STEP): an equity pre-commitment of one qualified investor for at least 20 % of the round is a condition of eligibility.
  const investor = facts.investor_precommitment;
  if (investor?.value === true && p.country) {
    const line = (verdict: Verdict, reason: string): Line => ({ key: 'investor', label: 'Investor pre-commitment', verdict, reason, quote: investor.quote });
    if (p.investor === 'yes') lines.push(line('yes', 'The call requires a pre-commitment of a qualified investor for at least 20 % of the funding round, and you said you have one.'));
    else if (p.investor === 'no') lines.push(line('no', 'The call requires a pre-commitment of a qualified investor for at least 20 % of the funding round, and you said you do not have one.'));
    else lines.push(line('check', 'The call requires a pre-commitment of a single qualified investor for at least 20 % of the funding round you aim to raise. Check that you have one.'));
  }
  // WP-93 (fix 6): rules the agency's own call page states (backend/dgate/rule_readings.py: RAPID, the Cyber Defense Factory).
  const most = facts.max_group_headcount;
  if (typeof most?.value === 'number' && p.country) {
    const n = most.value;
    const line = (verdict: Verdict, reason: string): Line => ({ key: 'group', label: 'Staff count with the group', verdict, reason, quote: most.quote });
    const h = p.size;
    if (h && h.max <= n) lines.push(line('yes', `The call is for companies with fewer than ${n + 1} staff, counted with the group, and yours is within that.`));
    else if (h && h.min > n) lines.push(line('no', `The call is for companies with fewer than ${n + 1} staff, counted with the group, and your answers give ${staff(h)}.`));
    else lines.push(line('check', `The call is for companies with fewer than ${n + 1} staff, counted with the whole group. Check your group's consolidated staff count.`));
  }
  const nationality = facts.staff_nationality;
  if (nationality && p.country) {
    lines.push({ key: 'nationality', label: 'Nationality of the staff', verdict: 'check', reason: `Only staff of ${String(nationality.value)} nationality may submit the application and work on the project. Check that yours are.`, quote: nationality.quote });
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
  designated: 'designated_applicants', required: 'required_partners', investor: 'investor_precommitment',
  group: 'max_group_headcount', nationality: 'staff_nationality',
};

export const SCOPE_WORDS = {
  call_document: 'Call document', general: 'General rule (work programme annexes)', topic: 'This topic',
  programme: 'EIC work programme (the call text of this scheme)',
} as const;

/**
 * What an ownership-control restriction is about, from its note and sentence (WP-93, fix 3): `china_only` names control by China (or an
 * entity established there) and no route of guarantees (Horizon Europe CL3 2026 BM-01, BM-02, INFRA-03); `china_no_guarantee` lets
 * controlled entities in with guarantees but not the ones controlled by China (Bridging 2027-01-13); `other` anything else.
 */
export function controlKind(way: string): 'china_only' | 'china_no_guarantee' | 'other' {
  if (!/\bChin(?:a|ese)\b/i.test(way)) return 'other';
  if (/(?:cannot|can not|may not|not (?:be )?(?:allowed|able|eligible) to) (?:submit|provide) guarantees/i.test(way)) return 'china_no_guarantee';
  if (/guarantee|non-?eligible|non-associated|outside the (?:eligible|EU)|third countr/i.test(way)) return 'other';
  return 'china_only';
}

/** Whether the country that controls a company is itself eligible under the call (control from Ukraine, or from every EEA EFTA state). */
export function controllerEligible(c: EligibilityFact | undefined, ctl: Controller, ctx?: CallContext): boolean {
  if (!c || (ctl !== 'ua' && ctl !== 'eea')) return false;
  const codes = ctl === 'ua' ? ['UA'] : ['IS', 'LI', 'NO'];
  return codes.every((code) => countryStatus(c, code, ctx).verdict === 'yes');
}
