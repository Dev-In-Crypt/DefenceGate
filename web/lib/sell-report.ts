/**
 * WP-162: the "Who to sell to" supplier report (backend/dgate/sell_report.py): its answer's shape and every label of the page, in one
 * place (`L`) so that Spanish can be added beside English. Pure: no DOM, no network.
 */
import type { ValueSum, ValueTotals } from './value-totals';
import { formatMoney } from './format';

export interface NoticeLink { href: string; sourceUrl: string | null; noticeId: string; publishedAt: string | null; source: string }
export interface BuyerRow { name: string; core: boolean; procurements: number; awardedValue: ValueSum[]; href: string; notice: NoticeLink | null }
export interface BuyerCountry { country: string; procurements: number; directive: number; buyers: number; coreBuyers: number; href: string; rows: BuyerRow[] }
export interface WinnerRow {
  name: string; country: string | null; contracts: number; countries: string[]; values: ValueTotals;
  prime: { group: string; source: string; sourceUrl: string } | null; large: boolean; edfProjects: number; byOtherCodeOnly: boolean;
  href: string; notice: NoticeLink | null;
}
export interface NotNamed { country: string | null; companies: number; contracts: number }
export interface Market {
  available: boolean; reason?: 'no_codes' | 'too_broad'; message?: string;
  since?: string; until?: string; countries?: string[];
  codes?: { code: string; prefix: string; procurements: number }[];
  total?: { procurements: number; directive: number; buyers: number; awarded: number; winners: number };
  buyers?: BuyerCountry[];
  winners?: { rows: WinnerRow[]; notNamed: NotNamed[]; listed: number; total: number; names: boolean; mosaicMin: number; href: string; ownContracts?: number | null };
  coverage?: string; winnersFrom?: string;
}
export type TenderFlag = 'clearance' | 'clearance_held' | 'not_read';
export type CallFlag = 'companies' | 'public_only' | 'sme_only' | 'sme_only_large' | 'not_stated';
export interface OpenTender { title: string; buyer: string; country: string | null; deadline: string | null; deadlineKnown: boolean; href: string; sourceUrl: string | null; legalBasis: string | null; flag: TenderFlag }
export interface OpenCall { title: string; programme: string; deadline: string | null; rolling: boolean; href: string; sourceUrl: string | null; flag: CallFlag; word: string }
export interface Quote { ref: string; url: string; text: string }
export type ItemStatus = 'have' | 'missing' | 'consultant';
export type Applies = 'prime' | 'both' | 'contract' | 'not_stated' | 'exporter' | 'us_origin';
export interface QualifyItem { key: string; name: string; applies: Applies; status: ItemStatus; cost: string | null; time: string | null; quotes: Quote[] }
export interface Verdict { programme: string; name: string; kind: string; verdict: 'eligible' | 'obtain' | 'conditional' | 'blocked'; blocking: number; toObtain: number; missing: number; sourceUrl: string }
export interface EndingRow { title: string; buyer: string | null; country: string | null; end: string; endStated: boolean; winner: string | null; href: string; sourceUrl: string | null }
export interface SellReport {
  generatedAt: string; sample: boolean; brand: { name: string | null; logo: string | null } | null;
  profile: {
    mode: 'A' | 'B'; name: string | null; slug: string | null; href: string | null; country: string | null; cpv: string[]; cpvTitles: Record<string, string>; cpvFrom: 'request' | 'awards' | null;
    nace: string | null; size: 'sme' | 'large' | null; held: string[]; classified: string | null; exports: string | null; usComponents: string | null;
    awards: number | null; projects: { programme: string; projects: number }[];
  };
  market: Market;
  open: { tenders: { rows: OpenTender[]; total: number; totalCapped?: boolean; href: string | null }; calls: { rows: OpenCall[]; words: string[]; matched: number } };
  ending: { rows: EndingRow[] } | null;
  qualify: { available: boolean; items: QualifyItem[]; verdicts: Verdict[]; notSourced: { key: string; name: string; why: string }[]; rulesReviewed?: string };
  steps: { key: string; window: string; text: string }[];
  sources: { coverage: string; winnersFrom: string | null; notes: { code: string; name: string; attribution: string }[]; projects: string | null; rules: string; disclaimer: string };
  quota?: { used: number; limit: number | null; left: number | null; per: 'month' | 'year'; counted: boolean };
}

/** Whether a body is a report the page can show (a live answer is checked before use). */
export function isSellReport(x: unknown): x is SellReport {
  const r = x as SellReport | null;
  return typeof r === 'object' && r !== null && typeof r.generatedAt === 'string' && typeof r.profile === 'object' && r.profile !== null
    && Array.isArray(r.profile.cpv) && typeof r.market === 'object' && r.market !== null && typeof r.open === 'object' && r.open !== null
    && Array.isArray(r.steps) && typeof r.sources?.disclaimer === 'string';
}

/** Every label of the report, English (v1). A second language is a second object of the same keys. */
export const L = {
  title: 'Who to sell to',
  kicker: 'Supplier report',
  sampleNote: 'A sample report for a fictitious demo company. Generating your own report comes with a paid plan.',
  preparedBy: 'Prepared by',
  generated: 'Generated',
  disclaimer: 'Indicative information, not legal advice, not an eligibility decision.',
  question: 'Who in European defence buys what we already make, who wins those contracts, what is open now, what do we lack to qualify, and what to do in the next 90 days.',
  s1: '1 · Profile', s2: '2 · Who buys this', s3: '3 · Who wins these contracts', s4: '4 · Open now', s5: '5 · Contracts ending soon',
  s6: '6 · What is missing to qualify', s7: '7 · Next steps for 90 days', s8: '8 · Sources and coverage',
  company: 'Company', country: 'Country', codes: 'What it makes (CPV)', nace: 'NACE code', size: 'Size', held: 'Certificates and registrations declared',
  awards: 'Contracts won in our data, last three years', projects: 'EU-funded projects', notAnswered: 'Not stated', none: 'None declared',
  codesFromAwards: 'The CPV classes of the contracts it won (its main codes).', codesFromRequest: 'As entered.',
  sizeSme: 'Small or medium enterprise', sizeLarge: 'Large enterprise',
  buyer: 'Buyer', procurements: 'Procurements', value: 'Awarded contract value', newest: 'Newest notice', source: 'Source',
  buyersLead: (n: number, since: string, until: string) => `Contracting authorities and entities that bought under these codes from ${since} to ${until}: ${n.toLocaleString('en-GB')} defence-scope procurements. The largest five in the first country and three in each of the next three, the other countries by their counts; each row links to the buyer's page under these codes and to its newest notice at the source.`,
  countryLine: (procurements: number, buyers: number, core: number) => `${procurements.toLocaleString('en-GB')} procurements · ${buyers} buyers, ${core} of them defence buyers`,
  noValue: 'No contract value stated',
  otherCountries: 'Also bought in',
  winner: 'Company', contracts: 'Contracts', countries: 'Buyer countries',
  winnersLead: 'The companies named as winners of these contracts: potential customers to approach as a sub-supplier. The list says who wins; what a winner buys from others is not published.',
  mosaic: (k: number) => `A small or medium company is named only when, in its country of registration and under a CPV code of this report, at least ${k} companies won these contracts; otherwise it is counted, not named. Companies on the SIPRI Top 100 of arms producers are always named: each is far above the EU ceiling of a medium-sized enterprise (Commission Recommendation 2003/361/EC).`,
  notNamed: (n: NotNamed) => `${n.companies} ${n.companies === 1 ? 'company' : 'companies'} registered in ${n.country ?? 'a country not stated'}, ${n.contracts} ${n.contracts === 1 ? 'contract' : 'contracts'}: counted, not named (mosaic rule).`,
  signInForNames: 'Company names are shown to signed-in accounts only; here the winners are counted by country.',
  prime: 'Large defence group',
  ownContracts: (n: number) => (n ? `The company itself won ${n.toLocaleString('en-GB')} of these contracts; it is left out of the list.` : 'The company itself won none of these contracts in what we hold.'),
  allWinners: (n: number) => `All ${n.toLocaleString('en-GB')} winners under these codes on the supplier map`,
  tenders: 'Open tenders', calls: 'Open funding calls', deadline: 'Deadline', flag: 'Eligibility',
  noTenders: 'No open tender under these codes today.', noCalls: 'No open funding call holds a product word of these codes.',
  moreTenders: (n: number, capped: boolean) => `${capped ? 'At least ' : ''}${n.toLocaleString('en-GB')} open tenders under these codes on the tender list`,
  callWords: (w: string[]) => (w.length ? `Calls searched for: ${w.join(', ')} (the product words of the codes, from our product-word map).` : 'No product word of our map matches these codes, so no call was searched.'),
  tenderFlag: { clearance: 'The notice names a security clearance or confidentiality condition', clearance_held: 'A security clearance is named; you said you work with classified information', not_read: 'No condition read: check the notice' } as Record<TenderFlag, string>,
  callFlag: { companies: 'Companies may apply', public_only: 'Public bodies only', sme_only: 'Reserved for SMEs', sme_only_large: 'Reserved for SMEs: not for a large enterprise', not_stated: 'Who may apply: not stated in what we hold' } as Record<CallFlag, string>,
  rolling: 'Rolling', notStated: 'Not stated',
  endingLead: 'Contracts under these codes ending in the next 12 months: when a contract ends, the buyer usually tenders again.', noEnding: 'No contract under these codes ends in the next 12 months in what we hold.',
  end: 'Ends', computed: 'computed from start and duration',
  requirement: 'Requirement', appliesTo: 'Applies to', status: 'Status', costTime: 'Cost and time',
  applies: { prime: 'The direct supplier (prime)', both: 'Prime and every sub-supplier concerned', contract: 'Whoever the contract names', not_stated: 'Not stated by the source', exporter: 'Whoever exports the item', us_origin: 'Whoever holds US-origin items' } as Record<Applies, string>,
  statusWord: { have: 'Have', missing: 'Missing', consultant: 'Needs a consultant' } as Record<ItemStatus, string>,
  statusNote: 'Have: declared as held. Missing: not declared as held. Needs a consultant: export classification, US rules and security clearances are never decided here.',
  noCostTime: 'No primary source states them',
  verdicts: 'The readiness rules on these answers', verdictWord: { eligible: 'Eligible', obtain: 'Obtain first', conditional: 'Conditional', blocked: 'Blocked' } as Record<Verdict['verdict'], string>,
  notSourcedHead: 'Not covered: no primary source, so no rule',
  window: 'When', step: 'Step',
  coverageHead: 'Data coverage', sourcesHead: 'Sources',
  printButton: 'Print or save as PDF',
} as const;

/** "EUR 1,200,000 over 3 contracts; PLN 40,000 over 1"; null for none (contract values only, never converted). */
export function valueLine(xs: readonly ValueSum[]): string | null {
  if (!xs.length) return null;
  return xs.map((s) => `${formatMoney({ currency: s.currency, amount: Math.round(s.amount) })} over ${s.count} ${s.count === 1 ? 'contract' : 'contracts'}`).join('; ');
}

/** The certificate and registration keys of the form (web/lib/profile.ts CERTIFICATES, REGISTRATIONS), by their labels. */
export function heldLabel(key: string, labels: Record<string, string>): string {
  return labels[key] ?? key;
}
