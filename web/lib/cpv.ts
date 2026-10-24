/**
 * The CPV finder's data: a selection of the official CPV 2008 vocabulary (lib/data/cpv.json, titles verbatim
 * from the Publications Office's codelist; none is written by us). Only codes in that file are listed.
 */
import data from './data/cpv.json';
import keywordData from './data/product-keywords.json';
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

/** Folded as the API's `dg_fold` (and `cpv_labels.fold`): lower case, no accents, the separators one space, a leading space. */
export function foldWords(text: string): string {
  const t = text.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();
  return ` ${t.split(/[\s\-–—/_.,;:()"'’]+/).filter(Boolean).join(' ')}`;
}

/** WP-90: whether a search word begins a word of a CPV title, as the API's tender search reads them (backend/dgate/cpv_labels.py: 3 letters or more). */
export function titleHasWord(title: string | null | undefined, word: string): boolean {
  const w = foldWords(word).trim();
  return w.length >= 3 && !w.includes(' ') && !!title && foldWords(title).includes(` ${w}`);
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

/**
 * The name a card prints beside a CPV chip: the code's own title and nothing else. A code outside the 366-code selection
 * has no title of its own here, and the title of its group or division is not its name: 39225500 (Pyrotechnics, on a
 * grenade tender) was printed as "Furniture, furnishings, domestic appliances and cleaning products", the title of
 * division 39 (UX audit T17). The detail page says "Within: ..." for those, which is true; a card has no room to.
 */
export function cpvOwnName(code: string): string | null {
  const name = cpvName(code);
  return name?.exact ? name.label : null;
}

/** A 3-digit group's title for the market tables; the division's title, said to be one, where the group is not held. */
export function cpvGroupName(group: string): string | null {
  const own = cpvGroupTitle(group);
  if (own) return own;
  const division = cpvDivisionLabel(group);
  // The group's own title is not in the selection we hold; say what we know (its division) and not that the
  // group is the division (site-qa2:N10: "Construction work (division)" for group 452).
  return division ? `${division}: group ${group}` : null;
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

export interface ProductMatch {
  /** The CPV prefixes to filter by: the shortest that cover the matching codes, at most `max`. */
  prefixes: string[];
  /** Codes whose title matched, with their titles (first few, for the page to show why). */
  codes: { code: string; title: string }[];
  /** How many codes matched. */
  matched: number;
  /** More prefixes matched than `max`: the filter holds the first `max` only. */
  truncated: boolean;
  /** How the codes were found: from the curated product words (`keyword`) or from the titles of the finder (`title`). */
  via?: 'keyword' | 'title';
  /** For a keyword match, a word of explanation the entry carries (an ambiguous word says what it is read as). */
  note?: string;
}

interface KeywordEntry { words: string[]; codes: { code: string; title: string }[]; note?: string }
export const PRODUCT_KEYWORDS = keywordData.entries as KeywordEntry[];

/** Lower-case words without accents or punctuation: "Bullet-proof" and "bullet proof" are the same phrase. */
const wordsOf = (s: string) => s.toLowerCase().normalize('NFD').replace(/\p{M}/gu, '').split(/[^a-z0-9]+/).filter(Boolean);

/**
 * `word` as written in a title: the word itself, its plural or its past form ("rocket"/"rockets", "armour"/"armoured", "battery"/"batteries").
 * Never a piece of a longer word: a substring match read "gun" in "Gunmetal" and "fuel" in "fuelled" (UX audit M7, 19 October 2026).
 */
export function isForm(titleWord: string, word: string): boolean {
  if (!titleWord || !word) return false;
  if (titleWord === word || titleWord === `${word}s` || titleWord === `${word}es` || titleWord === `${word}ed`) return true;
  return word.endsWith('y') && titleWord === `${word.slice(0, -1)}ies`;
}

/**
 * The curated product words (lib/data/product-keywords.json). The whole query must be made of listed phrases, otherwise null and
 * the titles of the finder are searched as before: "drone zzzz" is not read as "drone". The codes are the official ones, with their titles.
 */
function keywordEntries(query: string): KeywordEntry[] | null {
  const q = wordsOf(query);
  if (q.length === 0) return null;
  const found: { entry: KeywordEntry; from: number; to: number }[] = [];
  for (const entry of PRODUCT_KEYWORDS) {
    for (const phrase of entry.words) {
      const t = wordsOf(phrase);
      for (let i = 0; i + t.length <= q.length; i++) {
        if (t.every((w, j) => q[i + j] === w)) found.push({ entry, from: i, to: i + t.length });
      }
    }
  }
  // The longest phrase wins: "body armour" is one phrase, not "body" and "armour", and "armoured vehicles" is not "armoured" as well.
  const longest = found.filter((a) => !found.some((b) => b !== a && b.from <= a.from && b.to >= a.to && b.to - b.from > a.to - a.from));
  const used = q.map((_, i) => longest.some((m) => m.from <= i && i < m.to));
  const hit = [...new Set(longest.map((m) => m.entry))];
  return hit.length === 0 || !used.every(Boolean) ? null : hit;
}

function keywordMatch(query: string, max: number): ProductMatch | null {
  const hit = keywordEntries(query);
  if (!hit) return null;
  const codes = [...new Map(hit.flatMap((e) => e.codes).map((c) => [c.code, c])).values()];
  const all = [...new Set(codes.map((c) => cpvPrefix(c.code)))].sort((a, b) => a.length - b.length || a.localeCompare(b));
  const kept: string[] = [];
  for (const p of all) if (!kept.some((k) => p.startsWith(k))) kept.push(p);
  const note = hit.map((e) => e.note).filter(Boolean).join(' ');
  return { prefixes: kept.slice(0, max), truncated: kept.length > max, matched: codes.length, codes: codes.slice(0, 6), via: 'keyword', ...(note ? { note } : {}) };
}

/**
 * The CPV codes of the finder (this file's selection of the official vocabulary) whose title holds every word asked for,
 * as prefixes for a filter. "ammunition" gives the codes whose title begins so; a prefix that is already covered by a shorter one
 * is dropped, so a group and its members count once. Nothing here is a title of ours (U9: a product search for the supplier map).
 * A curated list of product words comes first (WP-43): the finder matches titles only, so "drone", "explosives" and "body armour" found nothing
 * and "tank" found heating tanks.
 */
export function cpvForWords(words: string, max = 20): ProductMatch {
  const curated = keywordMatch(words, max);
  if (curated) return curated;
  const ws = wordsOf(words).filter((w) => w.length >= 3).slice(0, 5);
  if (ws.length === 0) return { prefixes: [], codes: [], matched: 0, truncated: false, via: 'title' };
  // A word of the title, not a piece of one (WP-57): "gun" is not in "Gunmetal pipe fittings" and "fuel" is not in "nuclear fuelled".
  const found = Object.entries(CODES).filter(([, title]) => { const t = wordsOf(title); return ws.every((w) => t.some((x) => isForm(x, w))); });
  // Titles that begin with the word are the thing itself ("Ammunition"); a title that only lists it ("Weapons, ammunition and associated
  // parts") would pull in the whole group. The headwords are used when there are any.
  const heads = found.filter(([, title]) => isForm(wordsOf(title)[0] ?? '', ws[0]));
  const hits = (heads.length > 0 ? heads : found).sort(([a], [b]) => a.localeCompare(b));
  const all = [...new Set(hits.map(([code]) => cpvPrefix(code)))].sort((a, b) => a.length - b.length || a.localeCompare(b));
  const kept: string[] = [];
  for (const p of all) if (!kept.some((k) => p.startsWith(k))) kept.push(p);
  return {
    prefixes: kept.slice(0, max), truncated: kept.length > max, matched: hits.length, via: 'title',
    codes: hits.slice(0, 6).map(([code, title]) => ({ code, title })),
  };
}

/** Every code we hold with its official title: the finder's selection and the codes of the curated product words. */
const DICTIONARY = new Map<string, string>([...PRODUCT_KEYWORDS.flatMap((e) => e.codes.map((c) => [c.code, c.title] as const)), ...Object.entries(CODES)]);

/** The official title of a code of the dictionary (finder selection or product words), or null. */
export function cpvDictionaryTitle(code: string): string | null {
  return DICTIONARY.get(code) ?? null;
}

/**
 * The codes a supplier can pick for its profile (WP-65), at most `max`, from `dictionary`: the full official vocabulary once the supplier page
 * has loaded it (`lib/cpv-full.ts`, WP-73), else our selection. A 2- to 8-digit query is a code prefix. Otherwise the codes of the curated
 * product words come first, then every code whose official title holds each word of the query as a whole word (`isForm`: no piece of a
 * longer word, so "gun" is not "Gunmetal"), the titles that begin with the word before the others, broader codes first. No language model.
 */
export function cpvSearch(query: string, max = 20, dictionary: ReadonlyMap<string, string> = DICTIONARY): { code: string; title: string }[] {
  const q = query.trim();
  const out = (codes: string[]) => codes.slice(0, max).map((code) => ({ code, title: dictionary.get(code) ?? DICTIONARY.get(code) ?? '' }));
  if (/^\d{2,8}$/.test(q)) return out([...dictionary.keys()].filter((c) => c.startsWith(q)).sort());
  // in the entry's own order (WP-89: "castings" leads with Cast-iron products, the code named for the product itself)
  const curated = [...new Set((keywordEntries(q) ?? []).flatMap((e) => e.codes.map((c) => c.code)))];
  const ws = wordsOf(q).filter((w) => w.length >= 3).slice(0, 5);
  const heads: string[] = [];
  const rest: string[] = [];
  if (ws.length > 0) {
    for (const [code, title] of dictionary) {
      const tw = wordsOf(title);
      // either way round: "castings" finds "Casting machines" as "casting" finds "Castings"
      if (!ws.every((w) => tw.some((x) => isForm(x, w) || isForm(w, x)))) continue;
      (isForm(tw[0] ?? '', ws[0]) || isForm(ws[0], tw[0] ?? '') ? heads : rest).push(code);
    }
  }
  // the broader codes first (a group before its classes), then by code: with 9,454 titles a word like "vehicles" matches over a hundred.
  // WP-89: a product before the machine that makes it ("castings": cast-iron products before casting machines), in each list.
  const byLevel = (a: string, b: string) => cpvPrefix(a).length - cpvPrefix(b).length || a.localeCompare(b);
  const ranked = (xs: string[]) => [...xs.filter((c) => !isMachineCode(c, dictionary)).sort(byLevel), ...xs.filter((c) => isMachineCode(c, dictionary)).sort(byLevel)];
  return out([...new Set([...curated, ...ranked(heads), ...ranked(rest)])]);
}

/** WP-89: what the curated product words of a query say of themselves ("The CPV has no code for castings as such: ..."), or null. */
export function productNote(query: string): string | null {
  const notes = (keywordEntries(query) ?? []).map((e) => e.note).filter((n): n is string => !!n);
  return notes.length ? [...new Set(notes)].join(' ') : null;
}

/**
 * WP-89: a code for a machine, a machine tool or machinery (what makes a product, not the product): the machine tools (group 426) and
 * every code whose official title names a machine, machinery, a machining centre or presses. The supplier search lists these after
 * the products.
 */
export function isMachineCode(code: string, dictionary: ReadonlyMap<string, string> = DICTIONARY): boolean {
  if (code.startsWith('426')) return true;
  const title = dictionary.get(code) ?? DICTIONARY.get(code) ?? '';
  return wordsOf(title).some((w) => ['machine', 'machines', 'machinery', 'machining', 'presses'].includes(w));
}

/**
 * WP-89 (UX audit, section 4): a one-click start for an automotive parts maker on the supplier profile, trimmed by the visitor:
 * the vehicle and military-vehicle part codes the defence buyers use for spare parts, and the product codes of castings, fasteners and
 * wiring. Official codes and titles; the demand map counts under each.
 */
// WP-105 (p01): military vehicles and associated parts as a whole (35400000, the class 354: "Suministro de repuestos para vehículos BRI II"
// is coded 35400000 itself), in place of its parts code 35420000 and 35421000, which it covers
export const AUTOMOTIVE_SET = ['34300000', '34320000', '34330000', '35400000', '34322000', '34312000', '44470000', '44530000', '31611000'] as const;

/**
 * WP-97 (persona round of 23 October 2026): the other one-click starts, official CPV 2008 codes. Services: transport (60), cargo handling
 * and storage (631), fuels (091), facilities management (79993), cleaning (909), canteen and catering (555), repair of vehicles (501, the
 * vehicle class of division 50: the whole division matches too many notices for one map), defence training (806) and IT services (72).
 * Ammunition and explosives: ammunition and its parts (3533, 3534) and the explosives, propellants, pyrotechnics and fuses of group 2461.
 * Precision machining and aerospace parts: the mechanical spare parts of military vehicles, warships and military aircraft, aircraft
 * parts, mechanical spare parts, gearing and parts of firearms.
 */
export const SERVICES_SET = ['60000000', '63100000', '09100000', '79993000', '90900000', '55500000', '50100000', '80600000', '72000000'] as const;
export const AMMUNITION_SET = ['35330000', '35340000', '24610000', '24611000', '24612000', '24613000', '24615000'] as const;
// WP-105 (p03: the profile's set and the tender list's group differed, "Open now in Germany (0)" against 1): one list, read by the supplier
// profile and by the tender list's "Machined parts and spare parts" (lib/analyst.ts); aircraft parts are in AVIATION_SET
export const MACHINING_SET = ['35421000', '35521000', '35641000', '34320000', '34330000', '34913000', '35340000', '44530000'] as const;
// WP-105 (p02, p07): uniforms and textiles (the tender list's group), ships and naval, aircraft and aviation, official CPV 2008 codes
export const UNIFORM_SET = ['35810000', '18100000', '18200000', '18300000', '18800000', '35113400', '39500000'] as const;
export const NAVAL_SET = ['34500000', '35500000', '50640000', '50241000'] as const;
export const AVIATION_SET = ['34700000', '35600000', '50650000', '50211000'] as const;

export interface CodeSet { key: 'automotive' | 'machining' | 'ammunition' | 'services' | 'uniforms' | 'naval' | 'aviation'; label: string; covers: string; codes: readonly string[] }
export const CODE_SETS: CodeSet[] = [
  { key: 'automotive', label: 'Automotive supplier', codes: AUTOMOTIVE_SET,
    covers: 'vehicle and military-vehicle parts, engine and brake parts, cast-iron products, fasteners and wiring sets' },
  { key: 'machining', label: 'Machined parts and spare parts', codes: MACHINING_SET,
    covers: 'mechanical spare parts of military vehicles, warships and military aerospace equipment, other mechanical and miscellaneous spare parts, spare parts for vehicles, parts of firearms and ammunition, and fasteners' },
  { key: 'uniforms', label: 'Uniforms, textiles and protective gear', codes: UNIFORM_SET,
    covers: 'individual equipment, occupational clothing and workwear, outerwear and garments, footwear, protective and safety clothing, and textile articles' },
  { key: 'naval', label: 'Ships and naval', codes: NAVAL_SET,
    covers: 'ships and boats, warships and their parts, and the repair and maintenance of warships and ships' },
  { key: 'aviation', label: 'Aircraft and aviation', codes: AVIATION_SET,
    covers: 'aircraft and their parts, military aircraft, missiles and spacecraft, and the repair and maintenance of military and other aircraft' },
  { key: 'ammunition', label: 'Ammunition and explosives maker', codes: AMMUNITION_SET,
    covers: 'ammunition and its parts, explosives, propellants, pyrotechnic articles, fuses and detonators' },
  { key: 'services', label: 'Services to the armed forces', codes: SERVICES_SET,
    covers: 'transport, cargo handling and storage, fuels, facilities management, cleaning, catering, vehicle repair, defence training and IT services' },
];

/** WP-97: what kind of codes a profile holds, for the words of its report: services (CPV divisions 50 to 98), else the set it overlaps most. */
export type CodeKind = 'services' | 'automotive' | 'machining' | 'ammunition' | 'goods' | 'none';
export function codeKind(codes: readonly string[]): CodeKind {
  const valid = codes.filter((c) => /^\d{8}$/.test(c));
  if (valid.length === 0) return 'none';
  const services = valid.filter((c) => Number(c.slice(0, 2)) >= 50).length;
  if (services * 2 > valid.length) return 'services';
  const overlap = (set: readonly string[]) => valid.filter((c) => set.includes(c)).length;
  // automotive: the set, or any code of motor vehicles and their parts (341, 342, 343) and military-vehicle parts (3542)
  const vehicle = valid.filter((c) => AUTOMOTIVE_SET.includes(c as never) || /^(341|342|343|3542)/.test(c)).length;
  const best = (['automotive', 'ammunition', 'machining'] as const).map((k) => ({ k, n: k === 'automotive' ? vehicle : overlap(CODE_SETS.find((s) => s.key === k)!.codes) }))
    .sort((a, b) => b.n - a.n)[0];
  return best.n * 2 >= valid.length ? best.k : 'goods';
}
