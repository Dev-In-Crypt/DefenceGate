import { cpvTitle } from './cpv';
import { displayName } from './display-name';
import { programmeNameOf } from './format';

/**
 * WP-174 (QA 24 Nov 2026, A-3, B-18): headings a reader can use in the change feed and on /changes. A notice titled only with
 * its reference ("DAF_2026_000182") says what it buys by its main code first; a title in capitals is drawn in sentence case
 * (lib/display-name.ts); a funding call titled by its stage alone ("Short proposal") names its programme.
 */

/** A title that is a reference and nothing else: one token with a digit in it ("DAF_2026_000182", "2026/AR44U/00005142E"). */
export function isReferenceOnly(title: string | null | undefined): boolean {
  const t = (title ?? '').trim();
  return t.length > 0 && !/\s/.test(t) && /\d/.test(t);
}

export function noticeHeading(t: { title: string; cpvCodes?: string[] | null; cpvTitles?: Record<string, string> | null }): string {
  const title = displayName(t.title);
  if (!isReferenceOnly(t.title)) return title;
  const main = t.cpvCodes?.[0];
  const what = main ? (t.cpvTitles?.[main] ?? cpvTitle(main)) : null;
  return what ? `${what} (${title})` : title;
}

/** Titles that name a stage of a call, not the call ("Short proposal", "Full proposals", "Cut-off 2"). */
const STAGE_ONLY = /^(?:(?:short|full|first|second) (?:proposals?|applications?)|proposals?|applications?|(?:step|stage|phase|cut-?off|round) ?\d*)$/i;

/** A call titled by its stage alone ("Short proposal") is read with its programme's name ("EIC Accelerator: Short proposal"). */
export function callHeading(c: { title: string; programme?: string; programmeName: string }): string {
  const title = displayName(c.title);
  const programme = programmeNameOf(c);
  return programme && STAGE_ONLY.test(title.trim()) ? `${programme}: ${title}` : title;
}
