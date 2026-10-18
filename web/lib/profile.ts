/**
 * The company profile of the readiness check (WP-29). It lives in the visitor's browser only, in
 * localStorage under `dg.profile.v1`; the server never stores it. Other pages may read it:
 *
 *   import { loadProfile } from '@/lib/profile';
 *   const p = loadProfile();            // null before the wizard has been started
 *   p?.country                          // 'UA', 'ES', ... or 'XX' for a country that is not listed
 *
 * What leaves the browser is `toRequest(profile)`: the answers the rules read (twelve fields) and the
 * status of each requirement, sent to POST /api/readiness/assess to compute the verdict. The company
 * name and the size class are kept here for the page and are never part of that request.
 *
 * Pure of React and of the DOM except `loadProfile`/`saveProfile`/`clearProfile`, which touch
 * localStorage inside try/catch (a private window or blocked storage must not break the page).
 * lib/profile.check.ts runs the rest on its own.
 */

export const PROFILE_KEY = 'dg.profile.v1';
export const PROFILE_VERSION = 1;

export type Tri = 'yes' | 'no' | 'unsure' | '';
export type Control = 'no' | 'ua_eea_only' | 'other' | 'unsure' | '';
export type Regime = 'none' | 'dual_use' | 'military' | 'unknown' | '';
export type ExportIntent = 'none' | 'within_eu' | 'outside_eu' | 'unsure' | '';
export type LegalForm = 'legal_person' | 'natural_person' | 'no_legal_personality' | '';
export type SafeRole = 'contractor' | 'subcontractor_involved' | 'other_supplier' | 'unsure' | '';
export type Status = 'held' | 'in_progress' | 'not_held' | 'not_applicable';
export type SizeClass = 'micro' | 'small' | 'medium' | 'large' | '';

export interface Profile {
  version: 1;
  /** The furthest wizard step reached (1 to 5), 6 once the last step was finished. */
  step: number;
  updatedAt: string | null;
  // step 1: company basics
  name: string;
  sizeClass: SizeClass;
  country: string;
  legalForm: LegalForm;
  // step 2: ownership and control
  managementSameCountry: boolean;
  managementCountry: string;
  control: Control;
  uaOccupied: Tri;
  // step 3: products and regime
  regime: Regime;
  componentPct: string;
  restricted: Tri;
  /** Any component from Ukraine or an EEA EFTA state (EDIP and the Ukraine Support Instrument count them differently from SAFE). */
  uaEeaComponents: Tri;
  /** The role in a SAFE-supported procurement: the SAFE rules on establishment and control bind the contractor and the subcontractors involved. */
  safeRole: SafeRole;
  // step 4: certifications held
  statuses: Record<string, Status>;
  // step 5: classified work and export intentions
  classified: Tri;
  exportIntent: ExportIntent;
}

/** The requirements the wizard asks about, in the order it shows them. `esOnly`: only for a Spanish company. */
export const STATUS_ITEMS: { code: string; esOnly?: boolean }[] = [
  { code: 'REQ-NCAGE' }, { code: 'REQ-PIC' }, { code: 'REQ-ISO9001' }, { code: 'REQ-EN9100' },
  { code: 'REQ-AQAP2110' }, { code: 'REQ-AQAP2310' }, { code: 'REQ-EXPORT' },
  { code: 'REQ-REOCE', esOnly: true }, { code: 'REQ-FSC-ES', esOnly: true },
];

export const STATUS_LABEL: Record<Status, string> = {
  held: 'We hold it', in_progress: 'In progress', not_held: 'We do not hold it', not_applicable: 'Not applicable to us',
};

export function visibleCodes(country: string): string[] {
  return STATUS_ITEMS.filter((i) => !i.esOnly || country === 'ES').map((i) => i.code);
}

export function emptyProfile(): Profile {
  return {
    version: 1, step: 1, updatedAt: null, name: '', sizeClass: '', country: '', legalForm: '', managementSameCountry: true, managementCountry: '',
    control: '', uaOccupied: '', regime: '', componentPct: '', restricted: '', uaEeaComponents: '', safeRole: '', statuses: {}, classified: '', exportIntent: '',
  };
}

const oneOf = <T extends string>(value: unknown, allowed: readonly T[], fallback: T): T =>
  typeof value === 'string' && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
const text = (value: unknown, max: number): string => (typeof value === 'string' ? value.slice(0, max) : '');
const countryCode = (value: unknown): string => (typeof value === 'string' && /^[A-Z]{2}$/.test(value) ? value : '');

/** Read whatever is in storage as a profile: anything that is not one of ours is dropped field by field. */
export function parseProfile(raw: unknown): Profile {
  const base = emptyProfile();
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return base;
  const r = raw as Record<string, unknown>;
  if (r.version !== PROFILE_VERSION) return base;
  const statuses: Record<string, Status> = {};
  const given = typeof r.statuses === 'object' && r.statuses !== null && !Array.isArray(r.statuses) ? (r.statuses as Record<string, unknown>) : {};
  for (const { code } of STATUS_ITEMS) {
    const s = given[code];
    if (s === 'held' || s === 'in_progress' || s === 'not_held' || s === 'not_applicable') statuses[code] = s;
  }
  const pct = text(r.componentPct, 6);
  return {
    version: 1,
    step: typeof r.step === 'number' && Number.isInteger(r.step) && r.step >= 1 && r.step <= 6 ? r.step : 1,
    updatedAt: typeof r.updatedAt === 'string' ? r.updatedAt.slice(0, 40) : null,
    name: text(r.name, 120),
    sizeClass: oneOf(r.sizeClass, ['micro', 'small', 'medium', 'large', ''], ''),
    country: countryCode(r.country),
    legalForm: oneOf(r.legalForm, ['legal_person', 'natural_person', 'no_legal_personality', ''], ''),
    managementSameCountry: r.managementSameCountry !== false,
    managementCountry: countryCode(r.managementCountry),
    control: oneOf(r.control, ['no', 'ua_eea_only', 'other', 'unsure', ''], ''),
    uaOccupied: oneOf(r.uaOccupied, ['yes', 'no', 'unsure', ''], ''),
    regime: oneOf(r.regime, ['none', 'dual_use', 'military', 'unknown', ''], ''),
    componentPct: /^\d{0,3}([.,]\d{0,2})?$/.test(pct) ? pct : '',
    restricted: oneOf(r.restricted, ['yes', 'no', 'unsure', ''], ''),
    uaEeaComponents: oneOf(r.uaEeaComponents, ['yes', 'no', 'unsure', ''], ''),
    safeRole: oneOf(r.safeRole, ['contractor', 'subcontractor_involved', 'other_supplier', 'unsure', ''], ''),
    statuses,
    classified: oneOf(r.classified, ['yes', 'no', 'unsure', ''], ''),
    exportIntent: oneOf(r.exportIntent, ['none', 'within_eu', 'outside_eu', 'unsure', ''], ''),
  };
}

// ---------------------------------------------------------------- what leaves the browser

export interface AssessRequest {
  profile: {
    country: string;
    legal_form: 'legal_person' | 'natural_person' | 'no_legal_personality' | null;
    executive_management_country: string | null;
    third_country_control: 'no' | 'ua_eea_only' | 'other' | null;
    ua_non_government_controlled_area: boolean | null;
    non_eu_component_cost_pct: number | null;
    restricted_third_country_component: boolean | null;
    components_from_ua_or_eea_efta: boolean | null;
    safe_role: 'contractor' | 'subcontractor_involved' | 'other_supplier' | null;
    handles_classified: boolean | null;
    product_regime: 'none' | 'dual_use' | 'military' | 'unknown';
    export_intent: 'none' | 'within_eu' | 'outside_eu' | 'unsure' | null;
  };
  statuses: Record<string, Status>;
  /** A call of the funding list (its id), to also get the timing of the steps against its deadline (WP-32). */
  call?: number;
}

const tri = (v: Tri): boolean | null => (v === 'yes' ? true : v === 'no' ? false : null);

/** The share as a number from 0 to 100, or null when the field is empty or not a number in that range. */
export function parsePct(value: string): number | null {
  const n = Number(value.trim().replace(',', '.'));
  return value.trim() !== '' && Number.isFinite(n) && n >= 0 && n <= 100 ? n : null;
}

/** The request body for POST /api/readiness/assess, or null while the country is not chosen. */
export function toRequest(p: Profile): AssessRequest | null {
  if (!p.country) return null;
  const statuses: Record<string, Status> = {};
  for (const code of visibleCodes(p.country)) statuses[code] = p.statuses[code] ?? 'not_held';
  return {
    profile: {
      country: p.country,
      legal_form: p.legalForm === '' ? null : p.legalForm,
      executive_management_country: p.managementSameCountry ? p.country : p.managementCountry || null,
      third_country_control: p.control === 'no' || p.control === 'ua_eea_only' || p.control === 'other' ? p.control : null,
      ua_non_government_controlled_area: p.country === 'UA' ? tri(p.uaOccupied) : null,
      non_eu_component_cost_pct: parsePct(p.componentPct),
      restricted_third_country_component: tri(p.restricted),
      components_from_ua_or_eea_efta: tri(p.uaEeaComponents),
      safe_role: p.safeRole === '' || p.safeRole === 'unsure' ? null : p.safeRole,
      handles_classified: tri(p.classified),
      product_regime: p.regime === '' ? 'unknown' : p.regime,
      export_intent: p.exportIntent === '' ? null : p.exportIntent,
    },
    statuses,
  };
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
 * The questions the rules read that the profile leaves empty, in the order of the wizard. The optional ones (name, size, the share of
 * non-EU components) and the certificates, which count as "not held" until said otherwise, are not listed. Empty before a country is chosen.
 */
export function unanswered(p: Profile): Unanswered[] {
  const out: Unanswered[] = [];
  const need = (step: number, empty: boolean, question: string) => { if (empty) out.push({ step, question }); };
  need(1, !p.country, 'Country where your company is established');
  need(1, !p.legalForm, 'Legal form of your organisation');
  need(2, !p.managementSameCountry && !p.managementCountry, 'Country of the executive management');
  need(2, !p.control, 'Whether your company is controlled from outside the EU');
  need(2, p.country === 'UA' && !p.uaOccupied, 'Whether you are established in an area of Ukraine the government does not control');
  need(3, !p.regime, 'Which export regime your main product is in');
  need(3, !p.restricted, 'Whether a component comes from a third country that contravenes the security and defence interests of the Union');
  need(3, !p.uaEeaComponents, 'Whether components originate in Ukraine or an EEA EFTA state');
  need(3, !p.safeRole, 'Your role in a SAFE-supported procurement');
  need(5, !p.classified, 'Whether you will handle classified information');
  need(5, !p.exportIntent, 'Whether you export, or plan to export');
  return out;
}

/** The step to open when a finished profile is changed: the first with an unanswered question, else the first. */
export function firstStepToAnswer(p: Profile): number {
  return unanswered(p)[0]?.step ?? 1;
}

/** The wizard step that asks the question behind an API `missing` field (see `ProgrammeAssessment.missing`); 1 for one it does not know. */
export function stepOfField(field: string): number {
  const f = field.replace(/^profile\./, '');
  if (['country', 'legal_form'].includes(f)) return 1;
  if (['executive_management_country', 'third_country_control', 'ua_non_government_controlled_area'].includes(f)) return 2;
  if (['non_eu_component_cost_pct', 'restricted_third_country_component', 'components_from_ua_or_eea_efta', 'safe_role', 'product_regime'].includes(f)) return 3;
  if (['handles_classified', 'export_intent'].includes(f)) return 5;
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
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw) || (raw as { version?: unknown }).version !== PROFILE_VERSION) {
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
