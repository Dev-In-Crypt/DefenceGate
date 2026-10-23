/**
 * Where the supplier map's winners come from (WP-61). TED always; PLACSP, Spain's national procurement portal, only while the API
 * serves its award winners (DGATE_PLACSP_AWARDS_PUBLIC): the summary then lists it in `sources`, with the attribution and the date of
 * last update its publisher's terms ask for (docs/sources/es_placsp.md). The pages word their coverage from this, never from a guess.
 */
import type { SupplierSourceNote } from './types';

export const PLACSP_CODES = ['es_placsp', 'es_placsp_agg'];

export function placspNote(sources: SupplierSourceNote[] | undefined | null): SupplierSourceNote | null {
  return (sources ?? []).find((s) => PLACSP_CODES.includes(s.code)) ?? null;
}

/** The short name of the source of one notice. WP-88: a person's words, not the portal's code (PLACSP is named in About this data). */
export function sourceLabel(code: string | undefined): string {
  return code && PLACSP_CODES.includes(code) ? 'Spanish portal' : 'TED';
}

/** The coverage paragraph of /suppliers. WP-85: the same contracts as the supplier report's "who to approach", over the same three years. */
export function coverageText(placsp: boolean): string {
  const same = ' These are the same contracts the supplier report counts in “who to approach”, so a company named there has a page here. ' +
    'A contract published in several notices is counted once.';
  return placsp
    ? "The winners named in TED result notices and in the award results of Spain's national procurement portal (PLACSP, Plataforma de " +
      'Contratación del Sector Público) that our archive holds in the defence-relevant scope, published in the last three years. An award ' +
      'published in both is counted once.' + same + ' TED holds only part of European defence spending (a 2025 ECIPE policy brief puts it at ' +
      'about a tenth; we have not re-checked that figure), and contracts awarded outside TED and PLACSP are not here, so a company missing ' +
      'from this map may win many.'
    : 'The winners named in TED result notices that our archive holds in the defence-relevant scope, published in the last three years.' + same +
      ' TED holds only part of European defence spending (a 2025 ECIPE policy brief puts it at about a tenth; we have not re-checked that ' +
      'figure), and contracts awarded outside it are not here, so a company missing from this map may win many.';
}

/** "Origen de los datos: …, last updated 20 Sep 2026." for a PLACSP note; empty without one. */
export function placspCredit(note: SupplierSourceNote | null, formatDate: (iso: string) => string): string {
  if (!note) return '';
  return `${note.attribution.replace(/\.$/, '')}${note.lastUpdated ? `, last updated ${formatDate(note.lastUpdated)}` : ''}.`;
}
