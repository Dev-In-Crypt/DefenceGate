/**
 * The company profile of the readiness check (WP-29). It lives in the visitor's browser only, in
 * localStorage under `dg.profile.v1` (the key keeps its name; the block inside carries a `version`); the server never stores it.
 * Other pages may read it:
 *
 *   import { loadProfile } from '@/lib/profile';
 *   const p = loadProfile();            // null before the wizard has been started
 *   p?.country                          // 'UA', 'ES', ... or 'XX' for a country that is not listed
 *
 * What leaves the browser is `toRequest(profile)`: the answers the rules read (fifteen fields, plus the supplier page's answers that rules read) and the
 * status of each requirement, sent to POST /api/readiness/assess to compute the verdict. The company
 * name and the size class are kept here for the page and are never part of that request.
 *
 * Pure of React and of the DOM except `loadProfile`/`saveProfile`/`clearProfile`, which touch
 * localStorage inside try/catch (a private window or blocked storage must not break the page).
 * lib/profile.check.ts runs the rest on its own.
 */

export const PROFILE_KEY = 'dg.profile.v1';
/**
 * Version 2 (WP-53) replaced the pre-selected "executive management is in the same country" with an answer that starts empty, and added the
 * two partner questions. A version 1 block is still read (`parseProfile`): its executive-management answer is kept only when it said
 * "another country", because a stored "same country" cannot be told from the radio that was ticked for the visitor.
 *
 * Version 3 (WP-65) added the supplier profile (`supplier`: what a parts or materials maker answers on /readiness/supplier). A version 1 or 2
 * block is read with an empty supplier profile and every other answer kept; the block is written back as version 3 at the first change.
 */
export const PROFILE_VERSION = 5;
const LEGACY_VERSIONS = [1, 2, 3, 4];
/**
 * Version 4 (WP-93, the eligibility check of 23 October 2026): what the size, control and EIC rules read. The kind of organisation
 * (`orgKind`), the staff count (`headcount`), whether the company is part of a group and the group's staff count, which country controls
 * a company controlled from outside the EU (`controlCountry`), an investor's pre-commitment (`investor`) and the share of non-EU components
 * as a choice (`componentBand`). A block of version 1 to 3 is read with these empty; while the staff count is unanswered the size rules
 * read the old size class instead (lib/fit.ts `headcountOf`: micro and small, fewer than 50; medium, 50 to 249; large, 250 or more), and
 * the request it sends stays what it was. An unanswered one is unknown: the rules that read it say "check", never "eligible".
 *
 * Version 5 (WP-99, persona round of 23 October 2026): Ukraine and the EEA EFTA states apart, because the Ukraine Support Instrument
 * counts Ukraine as inside and an EEA EFTA state as outside. The control question offers "only by Ukraine" and "only by an EEA EFTA state"
 * as two answers (kept as `control: 'ua_eea_only'` with `controlCountry` 'ua' or 'eea'), and the joint component question is two questions
 * (`uaComponents`, `eeaComponents`). A version 1 to 4 block is read so: "only by Ukraine or an EEA EFTA state" without the country is
 * unanswered again; a joint "no" (or "not sure") about components answers both questions, a joint "yes" neither (it does not say which).
 */

export type Tri = 'yes' | 'no' | 'unsure' | '';
/** An answer of a supplier-page question: yes / no / not sure, or one of the choices of a question with its own (`EsQuestion.options`). */
export type Answer = Tri | 'part_i_a' | 'part_i_b' | 'neither';
/** Where the executive management is: the answer starts empty (WP-53, T5), and an empty answer is unknown, never "same country". */
export type Management = 'same' | 'other' | '';
export type Control = 'no' | 'ua_eea_only' | 'other' | 'unsure' | '';
export type Regime = 'none' | 'dual_use' | 'military' | 'unknown' | '';
export type ExportIntent = 'none' | 'within_eu' | 'outside_eu' | 'unsure' | '';
export type LegalForm = 'legal_person' | 'natural_person' | 'no_legal_personality' | '';
export type SafeRole = 'contractor' | 'subcontractor_involved' | 'other_supplier' | 'unsure' | '';
/** What the applicant is. Only some EDIP calls care: common procurement is open to the last four kinds, not to a company (V2-B1). */
export type ApplicantKind = 'company_or_research' | 'contracting_authority' | 'international_organisation' | 'seap' | 'eda' | '';
export type Status = 'held' | 'in_progress' | 'not_held' | 'not_applicable';
export type SizeClass = 'micro' | 'small' | 'medium' | 'large' | '';
/**
 * WP-91 (UX audit 6): what the company offers. `software_services`: the questions on the components of an end product (their origin, a
 * restricted third country, components from Ukraine or the EEA EFTA states) are not asked. The rules that read them are not "not
 * applicable": their text is about the end product of the action, which a software or services company may be part of, so they stay
 * open ("check") in the results, and say why. Additive to version 3: a block without it reads ''.
 */
export type Offering = 'products' | 'software_services' | '';
/** WP-93: the kind of a company or research body (the applicant kind says whether it is a public buyer). */
export type OrgKind = 'company' | 'university' | 'research' | '';
/** WP-93: staff count bands, as the SME definition and the EIC small mid-cap count them (and RAPID's 2,000 for a group). */
export type HeadcountBand = 'lt50' | '50_249' | '250_499' | '500_1999' | '2000plus' | '';
export const HEADCOUNT_BANDS: { value: Exclude<HeadcountBand, ''>; label: string }[] = [
  { value: 'lt50', label: 'Fewer than 50' }, { value: '50_249', label: '50 to 249' }, { value: '250_499', label: '250 to 499' },
  { value: '500_1999', label: '500 to 1,999' }, { value: '2000plus', label: '2,000 or more' },
];
/** WP-93: who controls a company controlled from outside the EU (asked after the control question). */
export type ControlCountry = 'ua' | 'eea' | 'cn' | 'ru_by' | 'other_non_eu' | 'unsure' | '';
/** WP-93: the share of non-EU component cost as a choice; an exact share typed in `componentPct` wins. */
export type ComponentBand = 'le35' | 'gt35' | 'unsure' | '';
/** The answers about components a software or services company is not asked (see `Offering`). */
export const COMPONENT_FIELDS = ['non_eu_component_cost_pct', 'restricted_third_country_component', 'components_from_ua', 'components_from_eea_efta'] as const;
/** The fields of the rules left open because the company makes software or services, for the results to say so. */
export const skippedFields = (p: Profile): string[] => (p.offering === 'software_services' ? [...COMPONENT_FIELDS] : []);
const TOPICS_MAX = 300;

/** A process the supplier runs (kept for its own summary and the demand map; no rule reads it). */
export const PROCESSES = [
  { value: 'casting', label: 'Casting' }, { value: 'forging', label: 'Forging' }, { value: 'machining', label: 'Machining' },
  { value: 'welding', label: 'Welding' }, { value: 'electronics', label: 'Electronics' }, { value: 'plastics_composites', label: 'Plastics and composites' },
  { value: 'coatings', label: 'Coatings' }, { value: 'textiles', label: 'Textiles' }, { value: 'assembly', label: 'Assembly' },
  // WP-107 (p01): NACE 25.50 makers and harness makers did not find their process
  { value: 'stamping', label: 'Stamping and sheet metal forming' }, { value: 'harness', label: 'Cable and wiring harness assembly' },
] as const;
/** WP-97: what a services company runs instead (asked when it says it provides services; kept for its own summary, no rule reads it). */
export const SERVICE_PROCESSES = [
  { value: 'logistics', label: 'Logistics and warehousing' }, { value: 'transport', label: 'Transport' }, { value: 'fuel', label: 'Fuel supply' },
  { value: 'facility', label: 'Facility services (cleaning, building management)' }, { value: 'catering', label: 'Catering' },
  { value: 'maintenance', label: 'Maintenance and repair' }, { value: 'training', label: 'Training' }, { value: 'it_services', label: 'IT services' },
] as const;
const ALL_PROCESSES = [...PROCESSES, ...SERVICE_PROCESSES];
/** WP-97: a company that said it provides services (the wizard's "software or services" answer, `offering`). */
export const providesServices = (p: Profile): boolean => p.offering === 'software_services';

/**
 * Certificates and registrations of the supplier profile. With a `code`, holding it is the status of that requirement (the same answer as
 * step 4 of the wizard, or the roadmap's "mark as done"); without one, no rule reads it and it is kept in `supplier.held`. `esOnly`: asked of a
 * Spanish company only, as the requirement is.
 */
export interface Holding { key: string; label: string; code?: string; esOnly?: boolean }
export const CERTIFICATES: Holding[] = [
  { key: 'ISO9001', label: 'ISO 9001', code: 'REQ-ISO9001' }, { key: 'IATF16949', label: 'IATF 16949' }, { key: 'ISO27001', label: 'ISO/IEC 27001' },
  { key: 'EN9100', label: 'EN 9100', code: 'REQ-EN9100' }, { key: 'AQAP2110', label: 'AQAP 2110', code: 'REQ-AQAP2110' },
  { key: 'AQAP2310', label: 'AQAP 2310', code: 'REQ-AQAP2310' }, { key: 'PECAL', label: 'PECAL (Spanish Ministry of Defence quality certificate)', code: 'REQ-PECAL', esOnly: true },
  // WP-97: the certificates a services company is asked for (no rule of this check reads them; kept for its summary and report)
  { key: 'ISO14001', label: 'ISO 14001 (environmental management)' }, { key: 'ISO45001', label: 'ISO 45001 (occupational health and safety)' },
  { key: 'ISO50001', label: 'ISO 50001 (energy management)' }, { key: 'VCA', label: 'VCA (safety checklist for contractors)' },
  // WP-107 (p05): the French security qualifications a cyber firm holds (information only: no rule of this check reads them)
  { key: 'PASSI', label: 'ANSSI PASSI qualification (France, security audit providers)' },
  { key: 'SECNUMCLOUD', label: 'ANSSI SecNumCloud qualification (France, cloud services)' },
  { key: 'CSPN', label: 'ANSSI CSPN certification (France, first-level security certification of a product)' },
];
export const REGISTRATIONS: Holding[] = [
  { key: 'RID', label: 'RID (Registro de la Industria de Defensa)', code: 'REQ-RID', esOnly: true },
  { key: 'NCAGE', label: 'NCAGE code', code: 'REQ-NCAGE' }, { key: 'NSPA', label: 'NSPA Source File' },
];
const UNCODED = [...CERTIFICATES, ...REGISTRATIONS].filter((c) => !c.code).map((c) => c.key);
const CERT_KEYS = CERTIFICATES.map((c) => c.key);

/**
 * The questions of the Spanish defence supplier route (WP-64, `engine.SUPPLIER_FIELDS`), in the engine's words, asked of a Spanish company on
 * the supplier page. `when`: asked (and sent) only when the answer it depends on is given; a hidden answer is kept but not sent. An answer
 * "I am not sure" is sent as unknown (left out), so the rule keeps its question.
 */
export interface EsQuestion {
  field: string; label: string; kind?: 'enum'; when?: (p: Profile) => boolean;
  /** WP-97: the question whose answer makes this one appear: while it is hidden, a missing answer links there instead. */
  parent?: string;
  /** The choices, when they are not yes / no / not sure (sent as the value itself: `kind` is then 'enum'). */
  options?: readonly { value: Exclude<Answer, ''>; label: string }[];
}
const ans = (p: Profile, field: string): Answer => p.supplier.answers[field] ?? '';
/** WP-97: a follow-up is asked once its parent is answered yes or "I am not sure" (a "not sure" no longer hides the question the rule reads). */
const open_ = (v: string): boolean => v === 'yes' || v === 'unsure';
export const ES_QUESTIONS: EsQuestion[] = [
  { field: 'pecal_certificate_wanted', label: 'Do you want the PECAL certificate of your quality management system itself, and not only to meet PECAL requirements inside a contract?' },
  { field: 'pecal_system_9_months', parent: 'pecal_certificate_wanted', label: 'Has your PECAL quality system been in place, and audited by your management, for at least nine months?', when: (p) => open_(ans(p, 'pecal_certificate_wanted')) },
  { field: 'pecal_prior_contract', parent: 'pecal_certificate_wanted', label: 'In the last two years, have you had at least one Ministry of Defence contract with PECAL requirements, or a certificate of conformity signed by a DGAM quality representative (RAC)?', when: (p) => open_(ans(p, 'pecal_certificate_wanted')) },
  { field: 'pecal_2310_target', label: 'Do you target PECAL 2310 (aviation, space and defence)?' },
  { field: 'ncage_need_justified', label: 'Is a product of yours bought by the Ministry of Defence (so that it must be catalogued), or do you need an NCAGE code to register in the US System for Award Management (SAM)?', when: (p) => p.statuses['REQ-NCAGE'] !== 'held' },
  { field: 'specific_defence_use', label: 'Is your product for specific defence use (Article 346 of the Treaty on the Functioning of the EU), rather than a civilian product?' },
  { field: 'homologation_mandatory', parent: 'specific_defence_use', label: "Is your product on the Ministry of Defence's list of products for which homologation is mandatory?", when: (p) => open_(ans(p, 'specific_defence_use')) },
  { field: 'homologated', parent: 'homologation_mandatory', label: 'Is your product homologated by the Ministry of Defence?', when: (p) => open_(ans(p, 'specific_defence_use')) && open_(ans(p, 'homologation_mandatory')) },
  { field: 'es_defence_material_list', kind: 'enum', label: 'Is the item in Annex I of Real Decreto 679/2014 (the Spanish list of defence material, Relación de Material de Defensa)?', when: (p) => p.regime === 'military' },
  { field: 'stores_classified', parent: 'classified', label: 'Will classified information be stored on your own premises?', when: (p) => open_(p.classified) },
  // WP-107 (p01): asked only after a "yes" or "not sure" to classified work, as the rule now applies only then (ES-NSFCC)
  { field: 'nato_classified_contract', parent: 'classified', label: 'Does a NATO contract you target involve information classified NATO CONFIDENTIAL or higher?', when: (p) => open_(p.classified) },
  { field: 'nsfcc_held', parent: 'nato_classified_contract', label: 'Do you hold a NATO Facility Security Clearance Certificate (NSFCC)?', when: (p) => open_(p.classified) && open_(ans(p, 'nato_classified_contract')) },
  { field: 'nato_staff_cleared', parent: 'nato_classified_contract', label: 'Do the staff who need access hold NATO personnel security clearances?', when: (p) => open_(p.classified) && open_(ans(p, 'nato_classified_contract')) },
  { field: 'nato_icb_bid', label: 'Do you want to bid in a NATO international competitive bidding tender (NATO Security Investment Programme)?' },
  { field: 'rid_capabilities_declared', parent: 'nato_icb_bid', label: 'Have you declared your industrial capabilities in the Registro de la Industria de Defensa (RID)?', when: (p) => open_(ans(p, 'nato_icb_bid')) },
  { field: 'foreign_investor_authorised', parent: 'foreign_capital', label: 'Does the foreign investor hold an administrative authorisation of the Spanish Council of Ministers?', when: (p) => open_(p.supplier.foreignOwner) },
  { field: 'receives_eea_defence_products', label: 'Do you receive defence-related products from other EEA states?' },
  { field: 'certified_recipient', parent: 'receives_eea_defence_products', label: 'Are you certified by your national authority as a recipient of defence-related products under the general transfer licences of other member states?', when: (p) => open_(ans(p, 'receives_eea_defence_products')) },
];
const ES_FIELDS = new Set(ES_QUESTIONS.map((q) => q.field));

/**
 * WP-68: the questions of the German rules (WP-64: DE-GHB-ADMISSION, DE-SIBE, DE-VSNFD, DE-EXPORT-BAFA), in the engine's words, asked of a
 * company established in Germany: those rules apply only there (`country` is DE), so for a company elsewhere an answer would change nothing.
 * The security questions follow a "yes" to classified access. The personnel security checks (Ü1 to Ü3, DE-SUE) are information that reads
 * no answer of its own, so nothing is asked for them.
 */
export const DE_QUESTIONS: EsQuestion[] = [
  { field: 'de_vs_vertraulich', parent: 'classified', label: 'Will material classified VS-VERTRAULICH or higher be handed to you for processing and storage?', when: (p) => open_(p.classified) },
  { field: 'ghb_admitted', parent: 'de_vs_vertraulich', label: 'Is your company already under the BMWE Geheimschutzbetreuung (with a security notice)?', when: (p) => open_(p.classified) && open_(ans(p, 'de_vs_vertraulich')) },
  { field: 'sibe_appointed', parent: 'de_vs_vertraulich', label: 'Have you appointed a security officer (Sicherheitsbevollmächtigter, SiBe)?', when: (p) => open_(p.classified) && open_(ans(p, 'de_vs_vertraulich')) },
  { field: 'de_vs_nfd', parent: 'classified', label: 'Does the contract involve material classified VS-NUR FÜR DEN DIENSTGEBRAUCH (VS-NfD)?', when: (p) => open_(p.classified) },
  { field: 'vsnfd_declaration_signed', parent: 'de_vs_nfd', label: 'Have you signed the commitment declaration (Verpflichtungserklärung) for VS-NfD?', when: (p) => open_(p.classified) && open_(ans(p, 'de_vs_nfd')) },
  { field: 'vsnfd_merkblatt', parent: 'de_vs_nfd', label: 'Does your contract incorporate the VS-NfD-Merkblatt (GHB Anlage 4)?', when: (p) => open_(p.classified) && open_(ans(p, 'de_vs_nfd')) },
  { field: 'de_ausfuhrliste', kind: 'enum', label: 'Is the item in the German export list (Ausfuhrliste) Part I Section A (arms) or Section B (national dual-use list)?',
    when: (p) => p.exportIntent !== 'none',
    options: [{ value: 'part_i_a', label: 'Yes, Part I Section A (arms)' }, { value: 'part_i_b', label: 'Yes, Part I Section B (national dual-use list)' },
      { value: 'neither', label: 'Neither' }, { value: 'unsure', label: 'I am not sure' }] },
];
const DE_FIELDS = new Set(DE_QUESTIONS.map((q) => q.field));

/**
 * WP-68: the dual-use question of the EU rule EU-DUALUSE-EXPERT, asked of every company (the rule has no country condition). It is shown
 * while the rule can apply: the product is not said to be outside every regime or on a military list, and the company exports, or may
 * export, outside the EU. "I am not sure" is sent as such: the rule then says a classification is needed and flags a specialist.
 */
export const DUAL_USE_QUESTION: EsQuestion = {
  field: 'dualuse_annex_i', kind: 'enum', label: 'Is your item listed in Annex I of Regulation (EU) 2021/821 (dual-use items)?',
  when: (p) => !['none', 'military'].includes(p.regime) && !['none', 'within_eu'].includes(p.exportIntent),
};
const QUESTIONS = [...ES_QUESTIONS, ...DE_QUESTIONS, DUAL_USE_QUESTION];
const TRI_WORDS: Record<string, string> = { yes: 'Yes', no: 'No', unsure: 'Not sure', '': 'Not answered' };
/** An answer in words: the question's own choice, or yes / no / not sure (the report prints it). */
export const answerLabel = (q: EsQuestion, v: Answer): string => q.options?.find((o) => o.value === v)?.label ?? TRI_WORDS[v] ?? v;

/**
 * WP-73: the security clearances of the Spanish route, asked on the supplier page of a Spanish company that needs classified work (the HSES
 * only when classified information is stored on its premises). The answer is the requirement's status: yes is held, no is not held, and
 * "I am not sure" or no answer leaves it unknown, so the rule asks instead of reading "Not met". The answer itself is kept in `answers`.
 */
export interface StatusQuestion { code: string; label: string; when: (p: Profile) => boolean; parent?: string }
export const ES_CLEARANCES: StatusQuestion[] = [
  { code: 'REQ-FSC-ES', label: 'Does your company hold a company security clearance (HSEM, habilitación de seguridad de empresa)?', when: (p) => open_(p.classified) },
  { code: 'REQ-HSES-ES', parent: 'stores_classified', label: 'Does your company hold an establishment security clearance (HSES) for the premises where classified information is stored?',
    when: (p) => open_(p.classified) && open_(ans(p, 'stores_classified')) },
];
const CLEARANCE_CODES = new Set(ES_CLEARANCES.map((q) => q.code));

/**
 * WP-68: the export authorisation, asked on the supplier page once the item is, or may be, on the EU dual-use list or in Part I of the German
 * export list: the two export rules read it (EU-DUALUSE-EXPERT, DE-EXPORT-BAFA). It is the wizard's step 4 answer (`REQ-EXPORT`), answered as
 * the clearances are (`withClearance`): "I am not sure" leaves it unknown.
 */
export const EXPORT_HOLDING: StatusQuestion = {
  code: 'REQ-EXPORT', label: 'Do you hold an export authorisation for this item (dual-use or military)?',
  when: (p) => (DUAL_USE_QUESTION.when!(p) && ['yes', 'unsure'].includes(ans(p, DUAL_USE_QUESTION.field)))
    || (p.country === 'DE' && p.exportIntent !== 'none' && ['part_i_a', 'part_i_b', 'unsure'].includes(ans(p, 'de_ausfuhrliste'))),
};
const STATUS_ANSWER_CODES = new Set([...CLEARANCE_CODES, EXPORT_HOLDING.code]);

/** The answer shown for a clearance question: what the status says (the wizard's step 4 may have changed it), else "not sure" if that was the answer. */
export function clearanceAnswer(p: Profile, code: string): Tri {
  if (p.statuses[code] === 'held') return 'yes';
  if (p.statuses[code] === 'not_held') return 'no';
  return p.supplier.answers[code] === 'unsure' ? 'unsure' : '';
}

/** The profile with a clearance question answered: the status follows (yes held, no not held, not sure: no status). */
export function withClearance(p: Profile, code: string, v: Tri): Profile {
  const statuses = { ...p.statuses };
  if (v === 'yes') statuses[code] = 'held';
  else if (v === 'no') statuses[code] = 'not_held';
  else delete statuses[code];
  return { ...p, statuses, supplier: { ...p.supplier, answers: { ...p.supplier.answers, [code]: v } } };
}

/** The question of the supplier page that a company of any EU country is asked (WP-73): the general certified-recipient rule reads it. */
export const EU_QUESTION = 'receives_eea_defence_products';
const EU27 = new Set('AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE'.split(' '));
export const isEu = (country: string) => EU27.has(country);

/** The supplier profile (WP-65). Optional throughout: an empty answer is unknown, never "no". Only the answers the rules read leave the browser. */
export interface Supplier {
  /** ISO 3166-2 code of a Spanish autonomous community (ES-AN ...), or free text for another country. Not sent. */
  region: string;
  /** A foreign investor holds shares, directly or indirectly: the engine's `foreign_capital`. */
  foreignOwner: Tri;
  /** Country of that investor. Not sent (no rule reads it). */
  foreignCountry: string;
  /** NACE Rev. 2 code, optional. Not sent. */
  nace: string;
  /** Up to 15 CPV codes of what the company makes, from the official CPV vocabulary (5 to 15 recommended for the demand map). Not sent. */
  cpv: string[];
  processes: string[];
  /** Certificates and registrations no rule reads (IATF 16949, ISO/IEC 27001, NSPA Source File), held. The others are `statuses`. */
  held: string[];
  /** Expiry month (YYYY-MM) of a certificate held, by its key. Optional, not sent. */
  expiry: Record<string, string>;
  /** Components, technology or software of US origin in the product: the engine's `us_components`. */
  usComponents: Tri;
  /** The answers to `ES_QUESTIONS`, `DE_QUESTIONS`, `DUAL_USE_QUESTION` and the clearance questions, by engine field (or requirement code). */
  answers: Record<string, Answer>;
  /** WP-89: whether the company also wants EU funding (EDF, EDIP, SAFE); not sent, it decides what the results lead with (`wantsEuFunding`). */
  euFunding: Tri;
}

export function emptySupplier(): Supplier {
  return { region: '', foreignOwner: '', foreignCountry: '', nace: '', cpv: [], processes: [], held: [], expiry: {}, usComponents: '', answers: {}, euFunding: '' };
}

/** Recommended, not required (WP-73): no rule reads the codes; the demand map will. */
export const CPV_MIN = 5;
export const CPV_MAX = 15;
const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const NACE = /^[A-U]?\d{2}(\.\d{1,2})?$/;

/** Why the NACE code cannot be used, or null when it is empty or a NACE Rev. 2 code (25, 25.5, 25.50, C25.50). */
export function naceProblem(value: string): string | null {
  const v = value.trim().toUpperCase();
  return v === '' || NACE.test(v) ? null : 'Enter a NACE code such as 25.50 or C25.50, or leave it empty.';
}

/** Why the chosen CPV codes cannot be saved, or null for 0 to 15 (WP-73: none is required, since no rule reads them). */
export function cpvProblem(codes: string[]): string | null {
  return codes.length > CPV_MAX ? `Choose at most ${CPV_MAX} CPV codes.` : null;
}

/** Why an expiry month cannot be used, or null when it is empty or a month (YYYY-MM). */
export function monthProblem(value: string): string | null {
  return value === '' || MONTH.test(value) ? null : 'Enter the month as YYYY-MM, for example 2027-05, or leave it empty.';
}

/** Whether this profile holds a certificate or registration (a requirement's status, or the list of the others). */
export function holds(p: Profile, item: Holding): boolean {
  return item.code ? p.statuses[item.code] === 'held' : p.supplier.held.includes(item.key);
}

/** The profile with a certificate or registration ticked or unticked; unticking a requirement sets it to "not held" and drops its expiry month. */
export function withHeld(p: Profile, item: Holding, on: boolean): Profile {
  const expiry = { ...p.supplier.expiry };
  if (!on) delete expiry[item.key];
  const held = item.code ? p.supplier.held : on ? [...new Set([...p.supplier.held, item.key])] : p.supplier.held.filter((k) => k !== item.key);
  const statuses: Record<string, Status> = item.code ? { ...p.statuses, [item.code]: on ? 'held' : 'not_held' } : p.statuses;
  return { ...p, statuses, supplier: { ...p.supplier, held, expiry } };
}

/** Every problem of the supplier page, with the id of the field to focus, in the order of the page. Empty when the page can be saved. */
export function supplierProblems(p: Profile): { id: string; text: string }[] {
  const out: { id: string; text: string }[] = [];
  if (!p.country) out.push({ id: 'sp-country', text: 'Choose the country where your company is established.' });
  const nace = naceProblem(p.supplier.nace);
  if (nace) out.push({ id: 'sp-nace', text: nace });
  const cpv = cpvProblem(p.supplier.cpv);
  if (cpv) out.push({ id: 'sp-cpv-search', text: cpv });
  for (const c of CERTIFICATES) {
    const m = monthProblem(p.supplier.expiry[c.key] ?? '');
    if (m && holds(p, c)) out.push({ id: `sp-expiry-${c.key}`, text: `${c.label}: ${m}` });
  }
  return out;
}

/**
 * The profile as the supplier page saves it: a company that went through the page has said which of the certificates and registrations it
 * shows it holds ("an unticked one counts as not held"), so an unticked one is "not held" (sent), no longer unknown. What the page does not
 * show (the PIC, the export authorisation, a clearance not answered) stays unknown (WP-73).
 */
export function savedSupplier(p: Profile): Profile {
  const statuses = { ...p.statuses };
  for (const item of [...CERTIFICATES, ...REGISTRATIONS]) {
    if (item.code && (!item.esOnly || p.country === 'ES') && !statuses[item.code]) statuses[item.code] = 'not_held';
  }
  return { ...p, statuses };
}

/** Whether the supplier page has been used (some answer of its own is given). */
export function hasSupplier(p: Profile): boolean {
  const s = p.supplier;
  // WP-107: the wizard asks the EEA-recipient question (step 5) and the certificates no rule reads (step 4) too: they alone do not make a supplier
  return s.cpv.length > 0 || s.processes.length > 0 || s.nace !== '' || s.region !== '' || s.foreignOwner !== ''
    || s.usComponents !== '' || Object.keys(s.answers).some((k) => k !== EU_QUESTION) || s.euFunding !== '';
}

/** WP-89: the supply routes of the check (kind `route`): what a supplier's results and roadmap lead with. */
export const SUPPLY_ROUTES = ['ES-MOD', 'NATO-SUPPLY'] as const;
/** The EU funding programmes (kind `programme`). */
export const EU_PROGRAMMES = ['EDF', 'EDIP', 'EDIP-USI', 'SAFE'] as const;

/**
 * WP-89 (UX audit, section 4): whether the EU funding programmes are part of what this company wants. "Yes" on the supplier page says so,
 * "no" says not; unanswered or "not sure", a company that only filled in the supplier page is a supplier first (its results lead with the
 * Ministry of Defence and NATO routes, the funding programmes collapsed, and its roadmap leaves out what only they ask, the PIC), while one
 * that went through the readiness check (the EU funding questions) or never used the supplier page is not.
 */
export function wantsEuFunding(p: Profile): boolean {
  const e = p.supplier.euFunding;
  if (e === 'yes') return true;
  if (e === 'no') return false;
  return !hasSupplier(p) || p.step >= 6;
}

/** The programmes a roadmap request asks for: the supply routes only for a supplier that does not want EU funding, else every one (null). */
export function roadmapProgrammes(p: Profile): string[] | null {
  return wantsEuFunding(p) ? null : [...SUPPLY_ROUTES];
}

export interface Profile {
  version: 5;
  /** The furthest wizard step reached (1 to 5), 6 once the last step was finished. */
  step: number;
  updatedAt: string | null;
  // step 1: company basics
  name: string;
  sizeClass: SizeClass;
  country: string;
  legalForm: LegalForm;
  /** Optional: unanswered is unknown, never "a company". */
  applicantKind: ApplicantKind;
  /** WP-91: products, or software and services only (the component questions are then not asked). */
  offering: Offering;
  /** WP-91: the company's topics in its own words, comma-separated ("drone software, autonomy"): the order of "Fits my profile". Never sent. */
  topics: string;
  /** WP-93: company, university or research organisation (asked when the applicant kind is a company or research body, or unanswered). */
  orgKind: OrgKind;
  /** WP-93: the organisation's own staff count. */
  headcount: HeadcountBand;
  /** WP-93: part of a group (a parent, subsidiaries, or enterprises holding 25 % or more of each other): the SME definition counts them together. */
  inGroup: Tri;
  groupHeadcount: HeadcountBand;
  // step 2: ownership and control
  management: Management;
  managementCountry: string;
  control: Control;
  /** WP-93: which country controls the company, when it is controlled from outside the EU. */
  controlCountry: ControlCountry;
  /** WP-93: a pre-commitment of a single qualified investor for at least 20 % of a funding round you plan to raise (the EIC STEP calls ask for one). */
  investor: Tri;
  uaOccupied: Tri;
  // step 3: products and regime
  regime: Regime;
  componentPct: string;
  componentBand: ComponentBand;
  restricted: Tri;
  /** WP-99: any component from Ukraine (inside under the Ukraine Support Instrument, outside under EDIP). */
  uaComponents: Tri;
  /** WP-99: any component from an EEA EFTA state (outside under the Ukraine Support Instrument). */
  eeaComponents: Tri;
  // step 2 (WP-53, T21): the partners of the planned consortium. Unanswered is unknown, never "no".
  /** A legal entity established in Ukraine, with its executive management there, takes part: the Ukraine Support Instrument asks for one. */
  uaPartner: Tri;
  /** A SEAP takes part: some EDIP calls for industrial reinforcement ask for three independent entities unless one does. */
  seapPartner: Tri;
  /** The role in a SAFE-supported procurement: the SAFE rules on establishment and control bind the contractor and the subcontractors involved. */
  safeRole: SafeRole;
  // step 4: certifications held
  statuses: Record<string, Status>;
  // step 5: classified work and export intentions
  classified: Tri;
  exportIntent: ExportIntent;
  /** WP-65: the supplier profile of /readiness/supplier. */
  supplier: Supplier;
}

/**
 * The requirements the wizard asks about, in the order it shows them. `esOnly`: only for a Spanish company. `roadmapOnly` (WP-64): the
 * wizard does not ask it yet (the supplier profile is WP-65); it is kept when the roadmap marks it, and sent only once it has an answer,
 * so the rules read "unknown" for it and ask, instead of "not held".
 */
export const STATUS_ITEMS: { code: string; esOnly?: boolean; roadmapOnly?: boolean }[] = [
  { code: 'REQ-NCAGE' }, { code: 'REQ-PIC' }, { code: 'REQ-ISO9001' }, { code: 'REQ-EN9100' },
  { code: 'REQ-AQAP2110' }, { code: 'REQ-AQAP2310' }, { code: 'REQ-EXPORT' },
  { code: 'REQ-REOCE', esOnly: true }, { code: 'REQ-FSC-ES', esOnly: true },
  { code: 'REQ-RID', esOnly: true, roadmapOnly: true }, { code: 'REQ-PECAL', esOnly: true, roadmapOnly: true },
  { code: 'REQ-HSES-ES', esOnly: true, roadmapOnly: true },
];

export const STATUS_LABEL: Record<Status, string> = {
  held: 'We hold it', in_progress: 'In progress', not_held: 'We do not hold it', not_applicable: 'Not applicable to us',
};

/** WP-97: the country whose own route a requirement belongs to (Spain's RID, PECAL, REOCE, HSEM, HSES), or null for one of every country. */
export function requirementCountry(code: string): string | null {
  return STATUS_ITEMS.find((i) => i.code === code)?.esOnly ? 'ES' : null;
}

export function visibleCodes(country: string): string[] {
  return STATUS_ITEMS.filter((i) => !i.roadmapOnly && (!i.esOnly || country === 'ES')).map((i) => i.code);
}

/** The requirements only the roadmap can mark (see `STATUS_ITEMS`), for this country. */
export function roadmapOnlyCodes(country: string): string[] {
  return STATUS_ITEMS.filter((i) => i.roadmapOnly && (!i.esOnly || country === 'ES')).map((i) => i.code);
}

export function emptyProfile(): Profile {
  return {
    version: 5, step: 1, updatedAt: null, name: '', sizeClass: '', country: '', legalForm: '', applicantKind: '', offering: '', topics: '',
    orgKind: '', headcount: '', inGroup: '', groupHeadcount: '', management: '', managementCountry: '',
    control: '', controlCountry: '', investor: '', uaOccupied: '', uaPartner: '', seapPartner: '', regime: '', componentPct: '', componentBand: '', restricted: '',
    uaComponents: '', eeaComponents: '', safeRole: '', statuses: {}, classified: '', exportIntent: '',
    supplier: emptySupplier(),
  };
}

const oneOf = <T extends string>(value: unknown, allowed: readonly T[], fallback: T): T =>
  typeof value === 'string' && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
const text = (value: unknown, max: number): string => (typeof value === 'string' ? value.slice(0, max) : '');
const countryCode = (value: unknown): string => (typeof value === 'string' && /^[A-Z]{2}$/.test(value) ? value : '');
const triOf = (value: unknown): Tri => oneOf(value, ['yes', 'no', 'unsure', ''], '');
const strings = (value: unknown, allowed: (s: string) => boolean, max: number): string[] =>
  Array.isArray(value) ? [...new Set(value.filter((v): v is string => typeof v === 'string' && allowed(v)))].slice(0, max) : [];
const record = (value: unknown): Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

/** The supplier block of a stored profile, field by field; absent (a version 1 or 2 block) is empty. */
function parseSupplier(raw: unknown): Supplier {
  const r = record(raw);
  const expiry: Record<string, string> = {};
  for (const [k, v] of Object.entries(record(r.expiry))) if (CERT_KEYS.includes(k) && typeof v === 'string' && MONTH.test(v)) expiry[k] = v;
  const answers: Record<string, Answer> = {};
  for (const [k, v] of Object.entries(record(r.answers))) {
    const q = QUESTIONS.find((x) => x.field === k);
    // a question with choices of its own takes only those; every other one yes / no / not sure
    const t: Answer = q?.options ? oneOf(v, q.options.map((o) => o.value), '') : triOf(v);
    if ((q || STATUS_ANSWER_CODES.has(k)) && t) answers[k] = t;
  }
  return {
    region: text(r.region, 60),
    foreignOwner: triOf(r.foreignOwner),
    foreignCountry: countryCode(r.foreignCountry),
    nace: text(r.nace, 12),
    cpv: strings(r.cpv, (c) => /^\d{8}$/.test(c), CPV_MAX),
    processes: strings(r.processes, (v) => ALL_PROCESSES.some((x) => x.value === v), ALL_PROCESSES.length),
    held: strings(r.held, (v) => UNCODED.includes(v), UNCODED.length),
    expiry,
    usComponents: triOf(r.usComponents),
    answers,
    euFunding: triOf(r.euFunding),
  };
}

/** Read whatever is in storage as a profile: anything that is not one of ours is dropped field by field. */
export function parseProfile(raw: unknown): Profile {
  const base = emptyProfile();
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return base;
  const r = raw as Record<string, unknown>;
  if (r.version !== PROFILE_VERSION && !LEGACY_VERSIONS.includes(r.version as number)) return base;
  const statuses: Record<string, Status> = {};
  const given = typeof r.statuses === 'object' && r.statuses !== null && !Array.isArray(r.statuses) ? (r.statuses as Record<string, unknown>) : {};
  for (const { code } of STATUS_ITEMS) {
    const s = given[code];
    if (s === 'held' || s === 'in_progress' || s === 'not_held' || s === 'not_applicable') statuses[code] = s;
  }
  const sizeClass = oneOf(r.sizeClass, ['micro', 'small', 'medium', 'large', ''], '');
  const bands = HEADCOUNT_BANDS.map((b) => b.value);
  const controlCountry = oneOf(r.controlCountry, ['ua', 'eea', 'cn', 'ru_by', 'other_non_eu', 'unsure', ''], '');
  // WP-99: "only by Ukraine or an EEA EFTA state" is two answers now; without the country it says neither, and is asked again
  const asked = oneOf(r.control, ['no', 'ua_eea_only', 'other', 'unsure', ''], '');
  const control = asked === 'ua_eea_only' && controlCountry !== 'ua' && controlCountry !== 'eea' ? '' : asked;
  // WP-99: the joint component answer of a version 1 to 4 block answers both questions when it is "no" or "not sure"
  const joint = triOf(r.uaEeaComponents);
  const fromJoint = joint === 'yes' ? '' : joint;
  return {
    version: 5,
    step: typeof r.step === 'number' && Number.isInteger(r.step) && r.step >= 1 && r.step <= 6 ? r.step : 1,
    updatedAt: typeof r.updatedAt === 'string' ? r.updatedAt.slice(0, 40) : null,
    name: text(r.name, 120),
    sizeClass,
    country: countryCode(r.country),
    legalForm: oneOf(r.legalForm, ['legal_person', 'natural_person', 'no_legal_personality', ''], ''),
    applicantKind: oneOf(r.applicantKind, ['company_or_research', 'contracting_authority', 'international_organisation', 'seap', 'eda', ''], ''),
    offering: oneOf(r.offering, ['products', 'software_services', ''], ''),
    topics: text(r.topics, TOPICS_MAX),
    orgKind: oneOf(r.orgKind, ['company', 'university', 'research', ''], ''),
    headcount: oneOf(r.headcount, bands, ''),
    inGroup: triOf(r.inGroup),
    groupHeadcount: oneOf(r.groupHeadcount, bands, ''),
    management: r.version === 1 ? (r.managementSameCountry === false ? 'other' : '') : oneOf(r.management, ['same', 'other', ''], ''),
    managementCountry: countryCode(r.managementCountry),
    control,
    // the controlling country goes with the answer it belongs to: Ukraine or the EEA after "only by Ukraine or an EEA EFTA state", the others after "another country"
    controlCountry: control === 'ua_eea_only' ? controlCountry
      : control === 'other' ? (['cn', 'ru_by', 'other_non_eu', 'unsure'].includes(controlCountry) ? controlCountry : '') : '',
    investor: triOf(r.investor),
    uaOccupied: oneOf(r.uaOccupied, ['yes', 'no', 'unsure', ''], ''),
    uaPartner: oneOf(r.uaPartner, ['yes', 'no', 'unsure', ''], ''),
    seapPartner: oneOf(r.seapPartner, ['yes', 'no', 'unsure', ''], ''),
    regime: oneOf(r.regime, ['none', 'dual_use', 'military', 'unknown', ''], ''),
    // kept as typed (up to 12 characters): a value that is not a number from 0 to 100 is shown with its reason (`answerProblems`), not dropped here
    componentPct: text(r.componentPct, 12),
    componentBand: oneOf(r.componentBand, ['le35', 'gt35', 'unsure', ''], ''),
    restricted: oneOf(r.restricted, ['yes', 'no', 'unsure', ''], ''),
    uaComponents: r.uaComponents === undefined ? fromJoint : triOf(r.uaComponents),
    eeaComponents: r.eeaComponents === undefined ? fromJoint : triOf(r.eeaComponents),
    safeRole: oneOf(r.safeRole, ['contractor', 'subcontractor_involved', 'other_supplier', 'unsure', ''], ''),
    statuses,
    classified: oneOf(r.classified, ['yes', 'no', 'unsure', ''], ''),
    exportIntent: oneOf(r.exportIntent, ['none', 'within_eu', 'outside_eu', 'unsure', ''], ''),
    supplier: parseSupplier(r.supplier),
  };
}

// ---------------------------------------------------------------- what leaves the browser

export interface AssessRequest {
  profile: {
    country: string;
    legal_form: 'legal_person' | 'natural_person' | 'no_legal_personality' | null;
    applicant_kind: 'company_or_research' | 'contracting_authority' | 'international_organisation' | 'seap' | 'eda' | null;
    executive_management_country: string | null;
    third_country_control: 'no' | 'ua_eea_only' | 'other' | null;
    ua_non_government_controlled_area: boolean | null;
    non_eu_component_cost_pct: number | null;
    restricted_third_country_component: boolean | null;
    /** WP-99: the two places apart (the API still takes the joint `components_from_ua_or_eea_efta` of an older client). */
    components_from_ua: boolean | null;
    components_from_eea_efta: boolean | null;
    /** A legal entity established in Ukraine takes part in the planned consortium (null: not said). */
    ua_partner: boolean | null;
    safe_role: 'contractor' | 'subcontractor_involved' | 'other_supplier' | null;
    handles_classified: boolean | null;
    product_regime: 'none' | 'dual_use' | 'military' | 'unknown';
    export_intent: 'none' | 'within_eu' | 'outside_eu' | 'unsure' | null;
    /** WP-65, from the supplier page (`foreign_capital`, `us_components`, the `ES_QUESTIONS`): present only when answered (absent is unknown to the API). */
    [supplierField: string]: string | number | boolean | null;
  };
  /** `unknown` (WP-73): a requirement the visitor was not asked about (step 4 of the wizard not reached), so a rule on it asks instead of reading "not held". */
  statuses: Record<string, Status | 'unknown'>;
  /** A call of the funding list (its id), to also get the timing of the steps against its deadline (WP-32). */
  call?: number;
  /** WP-89: only these programmes (the supply routes of a supplier that does not want EU funding: its roadmap). */
  programmes?: string[];
}

const tri = (v: Tri): boolean | null => (v === 'yes' ? true : v === 'no' ? false : null);

const PCT = /^(?:\d{1,3}(?:[.,]\d{0,2})?|[.,]\d{1,2})$/;

/** The share as a number from 0 to 100, or null when the field is empty or not a number in that range. */
export function parsePct(value: string): number | null {
  const v = value.trim();
  if (!PCT.test(v)) return null;
  const n = Number(v.replace(',', '.'));
  return Number.isFinite(n) && n >= 0 && n <= 100 ? n : null;
}

/** Why the share cannot be used, or null when it is empty (not answered) or a number from 0 to 100. The wizard shows this next to the field. */
export function pctProblem(value: string): string | null {
  return value.trim() === '' || parsePct(value) !== null ? null : 'Enter a number from 0 to 100.';
}

/**
 * The share the 35 % rules read (WP-93, fix 7): the exact share typed, else the choice. The only rules on the field compare it with 35 % (`lte`
 * 35, seeds/requirements.json), so a choice is sent as a share on its side of the line: 35 for "35 % or less", 36 for "more than 35 %".
 * ponytail: a band, not a figure; a rule with another threshold would need the exact share asked.
 */
export function componentShare(p: Profile): number | null {
  const exact = parsePct(p.componentPct);
  if (exact !== null) return exact;
  return p.componentBand === 'le35' ? 35 : p.componentBand === 'gt35' ? 36 : null;
}

/** The executive-management country the rules read: the company's own country, the one chosen, or null while not answered. */
export function managementCountryOf(p: Profile): string | null {
  return p.management === 'same' ? p.country || null : p.management === 'other' ? p.managementCountry || null : null;
}

/**
 * Every answer that is in the profile but is not used because it cannot be (WP-53, T6), with the step that fixes it. An answer that is
 * treated as missing must say so and say why; the results and the roadmap print these lines above the cards.
 */
export function answerProblems(p: Profile): { step: number; text: string }[] {
  const out: { step: number; text: string }[] = [];
  if (p.management === 'other' && !p.managementCountry) {
    out.push({ step: 2, text: 'You said the executive management is in another country but did not choose which one, so that answer is treated as not given.' });
  }
  if (pctProblem(p.componentPct)) {
    out.push({ step: 3, text: `The share of component cost you entered (“${p.componentPct.trim().slice(0, 12)}”) is not a number from 0 to 100, so it is treated as not given.` });
  }
  return out;
}

/** The request body for POST /api/readiness/assess, or null while the country is not chosen. */
export function toRequest(p: Profile): AssessRequest | null {
  if (!p.country) return null;
  const statuses: Record<string, Status | 'unknown'> = {};
  // step 4 of the wizard shows these with "We do not hold it" chosen: once it was passed an empty one is "not held"; before, nobody asked (WP-73)
  const asked = p.step > 4;
  // "I am not sure" on the supplier page stays unknown even after the wizard was finished
  for (const code of visibleCodes(p.country)) statuses[code] = p.statuses[code] ?? (asked && p.supplier.answers[code] !== 'unsure' ? 'not_held' : 'unknown');
  // not asked by the wizard: sent only once the roadmap has marked it, else the rules read it as unknown and ask
  for (const code of roadmapOnlyCodes(p.country)) if (p.statuses[code]) statuses[code] = p.statuses[code];
  return {
    profile: {
      country: p.country,
      legal_form: p.legalForm === '' ? null : p.legalForm,
      applicant_kind: p.applicantKind === '' ? null : p.applicantKind,
      executive_management_country: managementCountryOf(p),
      third_country_control: p.control === 'no' || p.control === 'ua_eea_only' || p.control === 'other' ? p.control : null,
      ua_non_government_controlled_area: p.country === 'UA' ? tri(p.uaOccupied) : null,
      // not asked of a software or services company (WP-91): a leftover answer is not sent, so the rules ask instead of reading it
      non_eu_component_cost_pct: p.offering === 'software_services' ? null : componentShare(p),
      restricted_third_country_component: p.offering === 'software_services' ? null : tri(p.restricted),
      components_from_ua: p.offering === 'software_services' ? null : tri(p.uaComponents),
      components_from_eea_efta: p.offering === 'software_services' ? null : tri(p.eeaComponents),
      // a Ukrainian company is itself the entity the rule asks for; the question is not asked of it, so a leftover answer is not sent
      ua_partner: p.country === 'UA' ? null : tri(p.uaPartner),
      safe_role: p.safeRole === '' || p.safeRole === 'unsure' ? null : p.safeRole,
      handles_classified: tri(p.classified),
      product_regime: p.regime === '' ? 'unknown' : p.regime,
      export_intent: p.exportIntent === '' ? null : p.exportIntent,
      ...applicantFields(p),
      ...supplierFields(p),
      // WP-107: read by the roadmap only (no AQAP step for software and services firms); "products" changes nothing, so only that answer is sent
      ...(p.offering === 'software_services' ? { offering: p.offering } : {}),
    },
    statuses,
  };
}

/**
 * WP-93: the answers the call verdict reads besides the rules (backend/dgate/verdict.py; the programme rules do not read them), only those
 * given: an absent field is unknown to the API, and a profile of version 3 sends what it sent before.
 */
export function applicantFields(p: Profile): Record<string, string | boolean> {
  const out: Record<string, string | boolean> = {};
  if (p.orgKind) out.org_kind = p.orgKind;
  if (p.headcount) out.headcount = p.headcount;
  const group = tri(p.inGroup);
  if (group !== null) out.in_group = group;
  if (p.inGroup === 'yes' && p.groupHeadcount) out.group_headcount = p.groupHeadcount;
  const ctl = controlCountryOf(p);
  if (ctl) out.control_country = ctl;
  const investor = tri(p.investor);
  if (investor !== null) out.investor_precommitment = investor;
  // The size class and the SEAP-partner answer stay in the browser, as before: the API's verdict reads them as unknown (dgate/verdict.py).
  return out;
}

/**
 * WP-99: the control question's answer as one choice: "only by Ukraine" and "only by an EEA EFTA state" are two answers, kept as
 * `ua_eea_only` with the country. '' while unanswered.
 */
export type ControlChoice = 'no' | 'ua' | 'eea' | 'other' | 'unsure' | '';
export function controlChoice(p: Profile): ControlChoice {
  if (p.control !== 'ua_eea_only') return p.control;
  return p.controlCountry === 'ua' || p.controlCountry === 'eea' ? p.controlCountry : '';
}
export function withControlChoice(p: Profile, v: Exclude<ControlChoice, ''>): Profile {
  if (v === 'ua' || v === 'eea') return { ...p, control: 'ua_eea_only', controlCountry: v };
  // the country asked after "another country" is kept while that is the answer
  return { ...p, control: v, controlCountry: v === 'other' && p.control === 'other' ? p.controlCountry : '' };
}

/** The controlling country the rules read: only with the control answer it belongs to, and never "not sure". */
export function controlCountryOf(p: Profile): 'ua' | 'eea' | 'cn' | 'ru_by' | 'other_non_eu' | null {
  const c = p.controlCountry;
  if (p.control === 'ua_eea_only' && (c === 'ua' || c === 'eea')) return c;
  if (p.control === 'other' && (c === 'cn' || c === 'ru_by' || c === 'other_non_eu')) return c;
  return null;
}

/** The answers of the supplier page the rules read, only those given (an absent field is unknown to the API, and keeps the body small). */
export function supplierFields(p: Profile): Record<string, boolean | string> {
  const out: Record<string, boolean | string> = {};
  const put = (field: string, v: Answer, kind?: 'enum') => {
    if (kind === 'enum' ? v !== '' : v === 'yes' || v === 'no') out[field] = kind === 'enum' ? v : v === 'yes';
  };
  put('foreign_capital', p.supplier.foreignOwner);
  put('us_components', p.supplier.usComponents);
  if (p.country === 'ES') {
    for (const q of ES_QUESTIONS) if (!q.when || q.when(p)) put(q.field, ans(p, q.field), q.kind);
  } else if (isEu(p.country)) put(EU_QUESTION, ans(p, EU_QUESTION));
  // WP-68: the German rules apply only to a company established in Germany; the dual-use rule to any company
  const ask = (q: EsQuestion) => { if (!q.when || q.when(p)) put(q.field, ans(p, q.field), q.kind); };
  if (p.country === 'DE') DE_QUESTIONS.forEach(ask);
  ask(DUAL_USE_QUESTION);
  return out;
}

/** Whether the wizard has been finished (the last step was passed). */
export function isFinished(p: Profile | null): p is Profile {
  return p !== null && p.country !== '' && p.step >= 6;
}

/** The profile with one requirement's status changed (the roadmap's "mark as done"). */
export function withStatus(p: Profile, code: string, status: Status): Profile {
  return { ...p, statuses: { ...p.statuses, [code]: status }, updatedAt: new Date().toISOString() };
}

// ---------------------------------------------------------------- what is still unanswered (U7)

/** One question of the wizard that has no answer yet, in the words of the wizard, with the step that asks it. */
export interface Unanswered { step: number; question: string }

/**
 * The questions the rules read that the profile leaves empty, in the order of the wizard. The optional ones (name, the investor's
 * pre-commitment, the two partner questions: the Ukraine Support Instrument card asks for the first itself while it is empty) and the certificates, which count as "not held" until said otherwise, are not listed. Empty before a country is chosen.
 * WP-93: the staff count, the group and the share of non-EU components are listed: the results named the share as a missing answer and
 * the list did not (finding 7 of 23 October 2026).
 */
export function unanswered(p: Profile): Unanswered[] {
  const out: Unanswered[] = [];
  const need = (step: number, empty: boolean, question: string) => { if (empty) out.push({ step, question }); };
  need(1, !p.country, 'Country where your company is established');
  need(1, !p.legalForm, 'Legal form of your organisation');
  // WP-93: the size rules of the EIC, the SME-only calls and RAPID read these; unanswered, they say "check"
  need(1, (p.applicantKind === '' || p.applicantKind === 'company_or_research') && !p.orgKind, 'Whether you are a company, a university or a research organisation');
  need(1, !p.headcount, 'How many people your organisation employs');
  need(1, !p.inGroup, 'Whether your company is part of a group');
  need(1, p.inGroup === 'yes' && !p.groupHeadcount, 'How many people the whole group employs');
  need(2, !p.management, 'Where the executive management of your company is');
  need(2, p.management === 'other' && !p.managementCountry, 'Country of the executive management');
  need(2, !p.control, 'Whether your company is controlled from outside the EU');
  need(2, p.control === 'other' && !p.controlCountry, 'Which country controls your company');
  need(2, p.country === 'UA' && !p.uaOccupied, 'Whether you are established in an area of Ukraine the government does not control');
  need(3, !p.regime, 'Which export regime your main product is in');
  // a software or services company is not asked about components (WP-91): those rules stay open in the results, with the reason
  const products = p.offering !== 'software_services';
  need(3, products && componentShare(p) === null && p.componentBand !== 'unsure', 'What share of the estimated cost of the components of your end product originates outside the EU, the EEA EFTA states and Ukraine');
  need(3, products && !p.restricted, 'Whether a component comes from a third country that contravenes the security and defence interests of the Union');
  need(3, products && !p.uaComponents, 'Whether components originate in Ukraine');
  need(3, products && !p.eeaComponents, 'Whether components originate in an EEA EFTA state');
  need(3, !p.safeRole, 'Your role in a SAFE-supported procurement');
  need(5, !p.classified, 'Whether you will handle classified information');
  need(5, !p.exportIntent, 'Whether you export, or plan to export');
  return out;
}

/** The step to open when a finished profile is changed: the first with an unanswered question, else the first. */
export function firstStepToAnswer(p: Profile): number {
  return unanswered(p)[0]?.step ?? 1;
}

/** The profile fields the wizard asks (the API's `missing` may name others: the Spanish, German and NATO/EU questions of WP-64, and requirements). */
const WIZARD_FIELDS = new Set(['country', 'legal_form', 'applicant_kind', 'executive_management_country', 'third_country_control',
  'ua_non_government_controlled_area', 'ua_partner', 'non_eu_component_cost_pct', 'restricted_third_country_component',
  'components_from_ua_or_eea_efta', 'components_from_ua', 'components_from_eea_efta', 'safe_role', 'product_regime', 'handles_classified', 'export_intent',
  'org_kind', 'headcount', 'in_group', 'group_headcount', 'control_country', 'investor_precommitment',
  // WP-107 (p09): reported missing for every EU company and asked only on the supplier page; step 5 asks it too
  'receives_eea_defence_products']);

/** The fields and requirements the supplier page asks (WP-65); the results link such a question to that page. */
const SUPPLIER_ASKS = new Set(['foreign_capital', 'us_components', ...ES_FIELDS, ...DE_FIELDS, DUAL_USE_QUESTION.field, ...CLEARANCE_CODES,
  ...[...CERTIFICATES, ...REGISTRATIONS].flatMap((c) => (c.code ? [c.code] : []))]);

/**
 * WP-89: the wizard's questions the supplier page asks as well, and where: classified work and exports in their blocks, the questions the
 * EU funding programmes read (and the PIC) in its block "If you also want EU funding" (`EU_FUNDING_FIELDS`).
 */
export const EU_FUNDING_FIELDS = ['legal_form', 'executive_management_country', 'third_country_control', 'non_eu_component_cost_pct',
  'restricted_third_country_component', 'components_from_ua_or_eea_efta', 'components_from_ua', 'components_from_eea_efta', 'ua_partner', 'safe_role', 'REQ-PIC'] as const;
const SUPPLIER_PAGE_ASKS: Record<string, string> = {
  handles_classified: 'q-classified', export_intent: 'q-export_intent', [EU_QUESTION]: `q-${EU_QUESTION}`,
  // the export authorisation is asked in the export block once the item may be on a control list; the block says what makes it appear
  'REQ-EXPORT': 'sp-export',
  ...Object.fromEntries(EU_FUNDING_FIELDS.map((f) => [f, 'sp-eu'])),
};

/**
 * Where the question behind an API `missing` field is asked (WP-73), or null when nothing on this site asks it: a field of the wizard links
 * to its step, a field or requirement of the supplier page to its question there, a requirement of the wizard's step 4 to that step.
 */
export function askedAt(field: string, supplier = false, profile: Profile | null = null): string | null {
  const f = field.replace(/^profile\./, '');
  // WP-89: a supplier answers on its own page what its verdicts still miss, the EU funding questions there too (#sp-eu)
  if (supplier && SUPPLIER_PAGE_ASKS[f]) return `/readiness/supplier#${SUPPLIER_PAGE_ASKS[f]}`;
  if (WIZARD_FIELDS.has(f)) return `/readiness?step=${stepOfField(f)}`;
  // WP-68: each shown only while the answers it depends on allow: the link goes to its block, which says what makes it appear
  if (f === DUAL_USE_QUESTION.field || f === 'de_ausfuhrliste') return '/readiness/supplier#sp-export';
  // WP-97: a question of the Spanish or German rules links to its own field; one that is hidden for these answers (a follow-up whose
  // parent is not answered yet) links to the field that makes it appear, so every link lands on a question of the page
  const q = QUESTIONS.find((x) => x.field === f) ?? ES_CLEARANCES.find((x) => x.code === f);
  if (q) {
    const shown = !q.when || profile === null || q.when(profile);
    if (shown) return `/readiness/supplier#q-${f}`;
    const parent = 'field' in q ? q.parent : q.parent ?? 'classified';
    if (!parent) return `/readiness/supplier#q-${f}`;
    return askedAt(parent, supplier, profile) ?? `/readiness/supplier#q-${parent}`;
  }
  if (f === 'classified') return '/readiness/supplier#q-classified';
  if (SUPPLIER_ASKS.has(f)) return `/readiness/supplier#q-${f}`;
  if (STATUS_ITEMS.some((i) => i.code === f && !i.roadmapOnly)) return '/readiness?step=4';
  return null;
}

/**
 * WP-97: whether the company answered "I am not sure" to the question behind an API `missing` field: an answer, not a missing one. The
 * rule stays open; the results say so and leave it out of the count of missing answers.
 */
export function notSure(p: Profile, field: string): boolean {
  const f = field.replace(/^profile\./, '');
  const wizard: Record<string, string> = {
    handles_classified: p.classified, third_country_control: p.control, safe_role: p.safeRole, restricted_third_country_component: p.restricted,
    components_from_ua_or_eea_efta: p.uaComponents === 'unsure' || p.eeaComponents === 'unsure' ? 'unsure' : '',
    components_from_ua: p.uaComponents, components_from_eea_efta: p.eeaComponents, ua_partner: p.uaPartner, ua_non_government_controlled_area: p.uaOccupied,
    non_eu_component_cost_pct: p.componentBand, control_country: p.controlCountry, investor_precommitment: p.investor, in_group: p.inGroup,
    foreign_capital: p.supplier.foreignOwner, us_components: p.supplier.usComponents,
  };
  return (wizard[f] ?? p.supplier.answers[f]) === 'unsure';
}

/** Whether the supplier page asks the question behind an API `missing` field (a field the wizard asks is linked to the wizard first). */
export function supplierAsks(field: string): boolean {
  return SUPPLIER_ASKS.has(field.replace(/^profile\./, ''));
}

/** Whether the wizard asks the question behind an API `missing` field; if not, the page shows the question without a link to a step. */
export function wizardAsks(field: string): boolean {
  return WIZARD_FIELDS.has(field.replace(/^profile\./, ''));
}

/** The wizard step that asks the question behind an API `missing` field (see `ProgrammeAssessment.missing`); 1 for one it does not know. */
export function stepOfField(field: string): number {
  const f = field.replace(/^profile\./, '');
  if (['country', 'legal_form', 'org_kind', 'headcount', 'in_group', 'group_headcount'].includes(f)) return 1;
  if (['executive_management_country', 'third_country_control', 'ua_non_government_controlled_area', 'ua_partner', 'control_country', 'investor_precommitment'].includes(f)) return 2;
  if (['non_eu_component_cost_pct', 'restricted_third_country_component', 'components_from_ua_or_eea_efta', 'components_from_ua', 'components_from_eea_efta', 'safe_role', 'product_regime'].includes(f)) return 3;
  if (['handles_classified', 'export_intent', EU_QUESTION].includes(f)) return 5;
  return 1;
}

// ---------------------------------------------------------------- export and import (U7: a second client must not overwrite the first)

const MAX_IMPORT = 20_000;

/** The profile as a block of text to keep: the same JSON the browser stores, with the date it was written. */
export function exportProfile(p: Profile): string {
  return JSON.stringify({ ...p, updatedAt: new Date().toISOString() }, null, 2);
}

/** A profile from text a visitor pasted or loaded from a file, or the reason it is not one of ours. */
export function importProfile(text: string): { ok: true; profile: Profile } | { ok: false; reason: string } {
  if (text.length > MAX_IMPORT) return { ok: false, reason: 'That is too long to be a set of answers from this site.' };
  let raw: unknown;
  try { raw = JSON.parse(text); } catch { return { ok: false, reason: 'That is not a set of answers: it does not read as the block this site writes.' }; }
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw) || ![PROFILE_VERSION, ...LEGACY_VERSIONS].includes((raw as { version?: unknown }).version as number)) {
    return { ok: false, reason: 'That is not a set of answers from this site (its version is missing or unknown).' };
  }
  return { ok: true, profile: parseProfile(raw) };
}

// ---------------------------------------------------------------- storage

export function loadProfile(): Profile | null {
  try {
    const raw = window.localStorage.getItem(PROFILE_KEY);
    return raw === null ? null : parseProfile(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function saveProfile(p: Profile): boolean {
  try {
    window.localStorage.setItem(PROFILE_KEY, JSON.stringify({ ...p, updatedAt: new Date().toISOString() }));
    return true;
  } catch {
    return false;
  }
}

export function clearProfile(): void {
  try {
    window.localStorage.removeItem(PROFILE_KEY);
  } catch {
    /* nothing to clear */
  }
}
