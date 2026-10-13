/**
 * The CPV finder's data: a selection of the official CPV 2008 vocabulary (lib/data/cpv.json, titles verbatim
 * from the Publications Office's codelist; none is written by us). Only codes in that file are listed.
 */
import data from './data/cpv.json';
import { cpvDivisionLabel, cpvLabel } from './taxonomy';

const CODES = data.codes as Record<string, string>;

export const CPV_SOURCE = {
  retrieved: data._retrieved,
  licence: data._licence,
  note: data._note,
  /** How many codes the full vocabulary holds. */
  vocabularySize: 9454,
  held: Object.keys(CODES).length,
};

export interface CpvRow {
  code: string;
  title: string;
  /** The significant digits of the code (trailing zeros dropped, at least the 2-digit division). */
  prefix: string;
  /** 0 division, 1 group, 2 class, 3 category, 4 below. */
  level: number;
  indent: number;
}
export interface CpvGroup { id: string; title: string | null; rows: CpvRow[] }
export interface CpvSection { id: string; title: string; intro: string; groups: CpvGroup[] }

/** The vocabulary's title of a 3-digit group (`351` is the title of 35100000), or null when we do not hold it. */
export function cpvGroupTitle(group: string): string | null {
  return /^\d{3}$/.test(group) ? (CODES[`${group}00000`] ?? null) : null;
}

/** The vocabulary's own title of a full code (`50640000`), or null when it is not one of the codes we hold. */
export function cpvTitle(code: string): string | null {
  const digits = /^\d{8}/.exec(code)?.[0];
  return digits ? (CODES[digits] ?? null) : null;
}

/**
 * The name to show for a notice's CPV code: the code's own title when we hold it (`exact`), else the title of its
 * group or division. Never a title we wrote: they all come from the vocabulary.
 */
export function cpvName(code: string): { label: string; exact: boolean } | null {
  const own = cpvTitle(code);
  return own ? { label: own, exact: true } : cpvLabel(code);
}

/** A 3-digit group's title for the market tables; the division's title, said to be one, where the group is not held. */
export function cpvGroupName(group: string): string | null {
  const own = cpvGroupTitle(group);
  if (own) return own;
  const division = cpvDivisionLabel(group);
  return division ? `${division} (division)` : null;
}

/** `35121700` -> `351217`; `35000000` -> `35`. A 2- to 8-digit prefix is what the /tenders filter takes. */
export function cpvPrefix(code: string): string {
  return code.replace(/0+$/, '').padEnd(2, '0').slice(0, 8);
}

function row(code: string, base: number): CpvRow | null {
  const title = CODES[code];
  if (!title) return null;
  const prefix = cpvPrefix(code);
  const level = Math.min(4, Math.max(0, prefix.length - 2));
  return { code, title, prefix, level, indent: Math.max(0, level - base) };
}

const rows = (codes: string[], base: number) => codes.map((c) => row(c, base)).filter((r): r is CpvRow => r !== null);
const sorted = (test: (c: string) => boolean) => Object.keys(CODES).filter(test).sort();

/** Military groups (353 to 358) first, then the rest of division 35, the adjacent codes, the supply divisions. */
export function cpvSections(): CpvSection[] {
  const group = (g: string, base = 1): CpvGroup => ({
    id: `g-${g}`,
    title: g === '350' ? null : `${g} · ${CODES[`${g}00000`] ?? ''}`,
    rows: rows(sorted((c) => (g === '350' ? c === '35000000' : c.startsWith(g))), base),
  });
  const militaryGroups = ['353', '354', '355', '356', '357', '358'];
  const otherGroups = ['350', '351', '352'];
  const adjacent = ['45216200', '50640000', '75220000', '75221000'];
  const divisions = sorted((c) => c.endsWith('000000') && c !== '35000000');
  const supply: CpvRow[] = [];
  for (const d of divisions) {
    const r = row(d, 0);
    if (r) supply.push(r);
    supply.push(...rows(sorted((c) => c.startsWith(d.slice(0, 2)) && c.endsWith('00000') && !c.endsWith('000000')), 0));
  }
  return [
    {
      id: 'military', title: 'Military equipment',
      intro: 'The military groups of division 35: weapons, vehicles, ships, aircraft, electronic systems and personal equipment.',
      groups: militaryGroups.map((g) => group(g)),
    },
    {
      id: 'security', title: 'Security, fire-fighting and police equipment',
      intro: 'The rest of division 35. A civil buyer can use these codes too, so a code alone does not make a notice defence.',
      groups: otherGroups.map((g) => group(g)),
    },
    {
      id: 'adjacent', title: 'Codes outside division 35 that name military or defence work',
      intro: 'Construction, maintenance and services whose titles name military or defence work.',
      groups: [{ id: 'g-adjacent', title: null, rows: rows(adjacent, 0) }],
    },
    {
      id: 'supply', title: 'Common supply divisions',
      intro: 'Every CPV division, with the groups of the divisions suppliers meet most: clothing, office and computing, electrical, communication, transport, laboratory and industrial equipment, construction materials, software, maintenance, transport and professional services.',
      groups: [{ id: 'g-supply', title: null, rows: supply }],
    },
  ];
}
