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
  if (directive) chips.push('Defence and security directive (2009/81/EC)');
  if (Array.isArray(t.qualifiedBy)) {
    // Driven by the signal that qualified the notice (site-qa2:N2): a military code is named only when it is what
    // qualified the notice, and a notice that is here through its buyer says so and nothing about a code.
    const by = t.qualifiedBy;
    if (by.includes('military_cpv') && !directive) chips.push(militaryCodeChip(t.militaryCpv, t.cpvCodes));
    if ((by.includes('buyer') || t.scope === 'supply') && !directive && !by.includes('military_cpv')) chips.push('Supplies to a defence buyer');
  } else {
    // An API that does not say what qualified the notice: `core` without the directive is a military product code.
    if (t.scope === 'core' && !directive) chips.push('Military product code (CPV)');
    if (t.scope === 'supply') chips.push('Supplies to a defence buyer');
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
export const CLASSIFIED_AUTOMATICALLY = 'Classified automatically';
