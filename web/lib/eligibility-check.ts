/**
 * "Can you apply?" for one call: the facts read from its call document (API `documentEligibility`)
 * against a few answers typed in the browser. Nothing here leaves the page.
 *
 * Rules of the verdict, all conservative: a "no" only where the document plainly excludes the
 * answer; a "yes" only where every applicable fact allows it and carries no condition; everything
 * else is "check", with the reason and the document's own sentence beside it. A fact that was
 * not read, or whose quote was not found in the document, is never in the data (the API drops it).
 */

export interface EligibilityFact { value: unknown; note?: string | null; quote: string; confidence: number }
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

export function check(facts: EligibilityFacts, p: Profile): Result {
  const lines: Line[] = [];

  const c = facts.eligible_countries;
  if (c && p.country) {
    const text = String(c.value);
    const eu = /member states/i.test(text);
    let line: Line;
    if (eu && EU27.has(p.country)) line = { key: 'country', label: 'Country', verdict: 'yes', reason: 'An EU Member State is eligible under this call.', quote: c.quote };
    else if (eu && EEA_EXTRA.has(p.country) && /EEA/i.test(text)) line = { key: 'country', label: 'Country', verdict: 'yes', reason: 'EEA countries are eligible under this call.', quote: c.quote };
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
    else lines.push(withNote({ key: 'consortium', label: 'Partners', verdict: 'yes', reason: 'No consortium is required.', quote: cons.quote }, cons));
  }

  const own = facts.ownership_control_restriction;
  if (own && p.controlledAbroad) {
    if (own.value !== true) lines.push(withNote({ key: 'control', label: 'Ownership control', verdict: 'yes', reason: 'No ownership control restriction is stated.', quote: own.quote }, own));
    else if (p.controlledAbroad === 'yes') lines.push({ key: 'control', label: 'Ownership control', verdict: 'no', reason: 'Entities controlled from outside the eligible countries are excluded, unless the document allows a guarantee.', quote: own.quote });
    else if (p.controlledAbroad === 'unsure') lines.push({ key: 'control', label: 'Ownership control', verdict: 'check', reason: 'Entities controlled from outside the eligible countries are excluded. Find out who controls your company.', quote: own.quote });
    else lines.push(withNote({ key: 'control', label: 'Ownership control', verdict: 'yes', reason: 'The restriction applies, and your company is not controlled from outside the eligible countries.', quote: own.quote }, own));
  }

  return { verdict: lines.reduce<Verdict>((v, l) => worst(v, l.verdict), 'yes'), lines };
}
