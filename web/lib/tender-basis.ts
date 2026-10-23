/**
 * Why a notice is in the directory, said as the signals the API actually holds instead of one generic
 * "Defence notice" label: a police or fire-brigade buyer that declares Directive 2009/81/EC is there for that
 * reason, and the chips say so. Pure and import-free so lib/ui.check.ts can run it on its own.
 */

export interface BasisInput {
  legalBasis?: string | null;
  scope?: string | null;
  buyerClass?: string | null;
  dualUse?: boolean | null;
  securityClearance?: boolean | null;
  /** The signals that qualified the notice (API `qualifiedBy`); undefined on an older API build. */
  qualifiedBy?: string[] | null;
  /** The notice's own military CPV codes, and all its codes (to say "one of 46"). */
  militaryCpv?: string[] | null;
  cpvCodes?: string[] | null;
  /** How sure we are (API `confidence`); undefined on an older API build. */
  confidence?: ConfidenceInput | null;
}

export type ConfidenceLevel = 'high' | 'medium' | 'low';
export interface ConfidenceInput { level?: string | null; basis?: string[] | null }

/** Where the three levels are explained: the section "How sure are we" of the methodology page. */
export const CONFIDENCE_HREF = '/methodology#s-how-sure-are-we';
// WP-88: the level in words a reader uses (the audit found "Medium confidence"); `level` and the CSV cell are unchanged.
const CONFIDENCE_WORD: Record<ConfidenceLevel, string> = { high: 'Clearly defence', medium: 'Probably defence', low: 'Possibly defence' };

/**
 * The badge next to the "why" chips: the visible text, the sentence shown on hover and focus (the API's `basis`), and
 * the accessible name, which says the level and the reason. null when the API gives no level (an older build) or one
 * this build does not know, so a new level is never shown as a wrong word.
 */
/** The CSV cell: the level only (`high`, `medium`, `low`), empty when the API gave none or one this build does not know. */
export function confidenceCell(c: ConfidenceInput | null | undefined): string {
  return confidenceView(c)?.level ?? '';
}

export interface ConfidenceView { level: ConfidenceLevel; text: string; sentence: string; name: string }
export function confidenceView(c: ConfidenceInput | null | undefined): ConfidenceView | null {
  const level = c?.level as ConfidenceLevel | undefined;
  if (!level || !(level in CONFIDENCE_WORD)) return null;
  const sentence = (c?.basis ?? []).filter(Boolean).join('; ');
  const text = CONFIDENCE_WORD[level];
  return { level, text, sentence: sentence ? `${sentence}.` : '', name: sentence ? `${text}: ${sentence}.` : text };
}

/** "Military product code (CPV 35811300, one of 46 codes)": the code that qualified the notice, not "a code". */
export function militaryCodeChip(military: string[] | null | undefined, all: string[] | null | undefined): string {
  const codes = (military ?? []).filter(Boolean);
  if (codes.length === 0) return 'Military product code (CPV)';
  const shown = codes.slice(0, 3).join(', ') + (codes.length > 3 ? ` and ${codes.length - 3} more` : '');
  const total = (all ?? []).length;
  return total > codes.length ? `Military product code (CPV ${shown}, among ${total} codes)` : `Military product code (CPV ${shown})`;
}

const DEFENCE_DIRECTIVE = /(2009[/-]81|32009L0081)/i;
/** The reasons a notice is listed, in the plain words of the owner's decision of 16 October 2026. */
export const DIRECTIVE_CHIP = 'Defence directive (2009/81/EC)';
export const BUYER_CHIP = 'Defence buyer';
/** The line that introduces the chips on a card. */
export const WHY_HERE = 'Why this is here';

/**
 * The two groups that are defence-qualified but not `core` (owner decision of 14 October 2026): scope `supply`,
 * named by the API's `qualifiedBy`. Each is the notice's only defence signal, from the wrong kind of buyer.
 */
export const SCOPE_GROUP_LABELS: Record<string, string> = {
  directive_civil_buyer: 'Filed under the defence procurement directive by a civil buyer',
  security_buyer_cpv: 'Security-body purchase of a military-type product code',
};

const SCOPE_GROUP_NOTES: Record<string, string> = {
  directive_civil_buyer: 'The notice states the defence procurement directive as its legal basis, and nothing else marks it as defence: its buyer is not a defence or security body. It is listed with supplies, not with defence notices.',
  security_buyer_cpv: 'The notice carries a military product code, and nothing else marks it as defence: its buyer is a police, prison, border, customs or tax body. It is listed with supplies, not with defence notices.',
};

/** The line under the chips of a notice filed in one of the two groups; null for any other notice. */
export function scopeGroupNote(qualifiedBy: string[] | null | undefined): string | null {
  const group = (qualifiedBy ?? []).find((q) => q in SCOPE_GROUP_NOTES);
  return group ? SCOPE_GROUP_NOTES[group] : null;
}

/** What kind of body the buyer is, by the API's `buyerClass`. `other` says nothing and gets no chip. */
const BUYER_CLASS: Record<string, string> = {
  defence: 'Defence body',
  security: 'Security or interior body',
  fire_rescue: 'Fire and rescue body',
  health: 'Health body',
  education: 'Education body',
  municipal: 'Municipal body',
};

/** The chips, in the order a reader weighs them: the legal basis, the scope, the buyer, then the rest. */
export function basisChips(t: BasisInput): string[] {
  const chips: string[] = [];
  const directive = Boolean(t.legalBasis && DEFENCE_DIRECTIVE.test(t.legalBasis));
  // A notice filed in one of the two groups says that, and nothing that would read as "defence notice".
  const group = Array.isArray(t.qualifiedBy) ? t.qualifiedBy.find((q) => q in SCOPE_GROUP_LABELS) : undefined;
  if (group) {
    chips.push(SCOPE_GROUP_LABELS[group]);
    const named = t.buyerClass ? BUYER_CLASS[t.buyerClass] : undefined;
    if (named) chips.push(named);
    if (t.securityClearance) chips.push('Security-clearance field present');
    return chips;
  }
  if (directive) chips.push(DIRECTIVE_CHIP);
  if (Array.isArray(t.qualifiedBy)) {
    // Driven by the signal that qualified the notice (site-qa2:N2): a military code is named only when it is what
    // qualified the notice, and a notice that is here through its buyer says so and nothing about a code.
    const by = t.qualifiedBy;
    if (by.includes('military_cpv') && !directive) chips.push(militaryCodeChip(t.militaryCpv, t.cpvCodes));
    if ((by.includes('buyer') || t.scope === 'supply') && !directive && !by.includes('military_cpv')) chips.push(BUYER_CHIP);
  } else {
    // An API that does not say what qualified the notice: `core` without the directive is a military product code.
    if (t.scope === 'core' && !directive) chips.push('Military product code (CPV)');
    if (t.scope === 'supply') chips.push(BUYER_CHIP);
  }
  const cls = t.buyerClass ? BUYER_CLASS[t.buyerClass] : undefined;
  if (cls) chips.push(cls);
  if (t.dualUse) chips.push('Dual-use / security');
  if (t.securityClearance) chips.push('Security-clearance field present');
  return chips;
}

export interface SignalInput {
  securityClearance?: boolean | null;
  subcontracting?: boolean | null;
  publishedAt?: string | null;
  source?: { sourceId?: string | null } | null;
}
/** What a "Security clearance" or "Subcontracting" cell says, and a line under it when the bare answer misleads. */
export interface SignalView { text: string; hint: string | null }

const TED_SOURCE = /^(eu-)?ted$/i;
/**
 * The clearance field (BT-732) exists only in eForms, which TED made mandatory on 25 October 2023, and the
 * subcontracting words are read from the text of TED notices only. A notice published from 2024 on, from TED, was
 * read for them; every other notice (a national source, or TED before 2024) was not, and "not found" would be a
 * finding we never made.
 */
const READ_FROM_DAY = '2024-01-01';

function wasRead(t: SignalInput): boolean {
  if (!TED_SOURCE.test(t.source?.sourceId ?? '')) return false;
  const day = (t.publishedAt ?? '').slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(day) && day >= READ_FROM_DAY;
}

export function clearanceView(t: SignalInput): SignalView {
  if (t.securityClearance) {
    return {
      text: 'Field present in the notice',
      hint: 'The field also carries sanctions declarations and criminal-record certificates, so it does not by itself mean clearance is required. Read the notice.',
    };
  }
  return { text: wasRead(t) ? 'Not detected' : 'Not read from this source', hint: null };
}

export function subcontractingView(t: SignalInput): SignalView {
  if (t.subcontracting) return { text: 'Mentioned in the notice', hint: null };
  return { text: wasRead(t) ? 'Not detected' : 'Not read from this source', hint: null };
}

/** The one line under the chips. */
export const CLASSIFIED_AUTOMATICALLY = 'Listed by our automatic rules';

/**
 * The additional CPV codes through which a notice matched a CPV filter, when its main code does not match: the card
 * shows the main code only, so a notice found by an additional code looked like a wrong result (4 of 9 hits of
 * cpv=34 on 16 October 2026). Empty when there is no filter or the main code already matches.
 */
export function matchedCpv(t: { cpv?: string | null; cpvCodes?: string[] | null }, prefixes: readonly string[] | undefined): string[] {
  if (!prefixes || prefixes.length === 0) return [];
  const hit = (code: string) => prefixes.some((p) => code.startsWith(p));
  if (t.cpv && hit(t.cpv)) return [];
  return (t.cpvCodes ?? []).filter((c) => c !== t.cpv && hit(c)).slice(0, 3);
}
