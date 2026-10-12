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
  // `core` without the directive is a military product code: the notice itself is defence goods or services.
  if (t.scope === 'core' && !directive) chips.push('Military product code (CPV)');
  if (t.scope === 'supply') chips.push('Supplies to a defence buyer');
  const cls = t.buyerClass ? BUYER_CLASS[t.buyerClass] : undefined;
  if (cls) chips.push(cls);
  if (t.dualUse) chips.push('Dual-use / security');
  if (t.securityClearance) chips.push('Security clearance mentioned');
  return chips;
}

/** The one line under the chips. */
export const CLASSIFIED_AUTOMATICALLY = 'Classified automatically';
