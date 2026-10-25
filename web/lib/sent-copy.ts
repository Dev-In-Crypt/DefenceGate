/**
 * WP-131 (round-7 legal-content audit: /readiness said "the company name and size ... are never sent" and "those codes alone are also
 * sent", while the request carries the staff counts and the demand map also sends countries): what leaves the browser, in words, from
 * the two request builders themselves. Every field of `toRequest` (lib/profile.ts) and of `demandRequest` (lib/demand.ts) has its words
 * here; lib/wp131.check.ts fails when a field is sent that no words name, or words name a field that is never sent.
 * Pure, so the check runs it on its own.
 */
import { DE_QUESTIONS, DUAL_USE_QUESTION, ES_QUESTIONS, EU_QUESTION } from './profile';
import { DEMAND_COUNTRIES } from './demand';

/** The supplier page's country questions the rules read (Spain, Germany, an EU country, dual use), by engine field. */
export const COUNTRY_QUESTION_FIELDS: readonly string[] = [...ES_QUESTIONS, ...DE_QUESTIONS, DUAL_USE_QUESTION].map((q) => q.field).concat(EU_QUESTION);

/** The verdict request (`POST /api/readiness/assess`): each group of words and the request fields it names (`statuses` is the top-level key). */
export const VERDICT_WORDS: readonly { words: string; fields: readonly string[] }[] = [
  { words: 'the country where your company is established', fields: ['country', 'ua_non_government_controlled_area'] },
  { words: 'its kind and legal form', fields: ['applicant_kind', 'org_kind', 'legal_form', 'offering'] },
  { words: 'the staff count of your organisation and, for a group, of the whole group', fields: ['headcount', 'in_group', 'group_headcount'] },
  { words: 'where it is managed and who owns or controls it', fields: ['executive_management_country', 'third_country_control', 'control_country', 'investor_precommitment', 'foreign_capital'] },
  { words: 'where its components come from', fields: ['non_eu_component_cost_pct', 'restricted_third_country_component', 'components_from_ua', 'components_from_eea_efta', 'us_components'] },
  { words: 'your consortium partners and SAFE role, classified work, the export regime and export plans', fields: ['ua_partner', 'safe_role', 'handles_classified', 'product_regime', 'export_intent'] },
  { words: 'your answers to the supplier page’s questions for your country', fields: COUNTRY_QUESTION_FIELDS },
  { words: 'which certificates and registrations you hold', fields: ['statuses'] },
];

/** The demand map's request (`POST /api/readiness/demand`), field by field. */
export const DEMAND_WORDS: Readonly<Record<string, string>> = {
  cpv: 'those codes',
  countries: `the ${DEMAND_COUNTRIES.length === 7 ? 'seven' : String(DEMAND_COUNTRIES.length)} countries of the map`,
  home: 'your own country when it is one of them',
};

/** What the browser keeps and never sends (the check asserts none of it is in either request). */
export const NEVER_SENT = 'The company name is never sent, and neither are the processes, region, NACE code, investor country or topics you may enter.';

const list = (parts: readonly string[]) => `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;

/** The verdict request, one sentence. */
export const VERDICT_SENTENCE = `The request that computes the verdict carries ${list(VERDICT_WORDS.map((g) => g.words))}, only as far as you answered, and on a call page the call it is for.`;

/** The demand map's request, one sentence. */
export const DEMAND_SENTENCE = `The request for the map of who buys what you make, sent only once you chose CPV codes on the supplier page, carries ${list(Object.values(DEMAND_WORDS))}.`;

/** The whole statement, for /readiness, the supplier profile and the Spain automotive page. */
export const WHAT_IS_SENT = `Two requests leave your browser. ${VERDICT_SENTENCE} ${DEMAND_SENTENCE} ${NEVER_SENT} The server keeps no copy of either request and does not log them.`;
