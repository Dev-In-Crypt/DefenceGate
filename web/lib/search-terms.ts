/**
 * WP-98: the search words of other languages and the buyers' abbreviations (lib/data/search-terms.json, the API's own copy at
 * backend/dgate/data/search-terms.json, held identical by backend/tests/unit/test_wp98.py). The API applies them
 * (backend/dgate/search_terms.py); this is the same reading for the demo data and the empty-result hint. Pure: wp98.check.ts runs it.
 */
import data from './data/search-terms.json';

export interface SearchTermGroup { id: string; label: string; cpv: string[]; terms: string[] }
export const SEARCH_GROUPS: SearchTermGroup[] = data.groups;
export const BUYER_ABBREVIATIONS: { abbr: string; country: string; names: string[] }[] = data.buyers;

const SEPARATORS = /[\s\-–—/_.,;:()"'’]+/u;
const LETTERS: Record<string, string> = { ł: 'l', ø: 'o', ß: 'ss', đ: 'd', ħ: 'h', æ: 'ae', œ: 'oe', þ: 'th', ð: 'd', ı: 'i' };

/** The words of a text as dg_fold folds them (migration 0054): lower case, accents and ł/ß/æ off, split at its separators. */
export function foldWords(text: string): string[] {
  const s = text.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().replace(/[łøßđħæœþðı]/g, (c) => LETTERS[c] ?? c);
  return s.split(SEPARATORS).filter(Boolean);
}

export interface Expanded {
  /** Each slot: its alternatives, each a list of words, the typed words first. Every slot must be filled. */
  slots: string[][][];
  /** The terms searched beyond the typed words. */
  also: string[];
  groups: SearchTermGroup[];
}

const key = (words: string[]) => words.flatMap(foldWords).join(' ');

/**
 * As search_terms.expand: the longest term of a group at each position is a slot any term of the group fills. WP-101: a run of
 * terms of one group ("Drehteile Frästeile") is one slot, any term of the group or all the typed words.
 */
export function expand(words: string[]): Expanded {
  const folded = words.map((w) => foldWords(w).join(' '));
  const out: Expanded = { slots: [], also: [], groups: [] };
  const typedKeys: Set<string>[] = [];
  const slotGroup: (SearchTermGroup | null)[] = [];
  let i = 0;
  while (i < words.length) {
    let best: { n: number; g: SearchTermGroup } | null = null;
    for (const g of SEARCH_GROUPS) {
      for (const t of g.terms) {
        const f = foldWords(t);
        if (f.length && f.join(' ') === folded.slice(i, i + f.length).join(' ') && (!best || f.length > best.n)) best = { n: f.length, g };
      }
    }
    if (!best) { out.slots.push([[words[i]]]); typedKeys.push(new Set()); slotGroup.push(null); i += 1; continue; }
    let typed = words.slice(i, i + best.n);
    const keys = new Set([key(typed)]);
    if (slotGroup.length && slotGroup[slotGroup.length - 1] === best.g) {
      typed = [...out.slots.pop()![0], ...typed];
      for (const k of typedKeys.pop()!) keys.add(k);
      slotGroup.pop();
    }
    out.slots.push(subsumed([typed, ...best.g.terms.map((t) => t.split(SEPARATORS).filter(Boolean))]).slice(0, MAX_ALTERNATIVES));
    typedKeys.push(keys);
    slotGroup.push(best.g);
    if (!out.groups.includes(best.g)) out.groups.push(best.g);
    i += best.n;
  }
  out.slots.forEach((alts, s) => {
    for (const a of alts.slice(1)) { const l = a.join(' '); if (!typedKeys[s].has(key(a)) && !out.also.includes(l)) out.also.push(l); }
  });
  return out;
}

const MAX_ALTERNATIVES = 40;

function subsumed(alts: string[][]): string[][] {
  const one = alts.filter((a) => a.length === 1).map((a) => foldWords(a[0])[0]).filter(Boolean);
  const seen = new Set<string>();
  return alts.filter((a) => {
    const k = key(a);
    if (!k || seen.has(k)) return false;
    if (!k.includes(' ') && one.some((o) => o !== k && k.startsWith(o))) return false;
    seen.add(k);
    return true;
  });
}

const words = (text: string | null | undefined) => (text ? foldWords(text) : []);
const begins = (w: string, have: string[]) => { const f = foldWords(w).join(' '); return have.some((h) => h.startsWith(f)); };
const phrase = (term: string[], have: string[]) => {
  const t = term.flatMap(foldWords);
  return have.some((_, i) => t.every((w, j) => (have[i + j] ?? '').startsWith(w) && (j === t.length - 1 || have[i + j] === w)));
};

/**
 * Whether the texts of a notice fill every slot, as the API reads them: the typed words each begin a word of a title or the buyer's name
 * (in any order); a term of the group begins a word of a title (a term of several words: that phrase).
 */
export function matchesSlots(slots: string[][][], titles: (string | null | undefined)[], buyer: string | null | undefined): boolean {
  const t = titles.flatMap(words);
  const all = [...t, ...words(buyer)];
  return slots.every(([typed, ...terms]) => typed.every((w) => begins(w, all)) || terms.some((term) => phrase(term, t)));
}

/**
 * WP-101: a TED notice number (220199-2026, 2026/S 203-724451), as the API reads it (backend/dgate/tenders.py NOTICE_NUMBER): the
 * search asks for that notice whatever its status, so the tender list opens on All for it (an awarded notice was "not found" in Open).
 */
export const NOTICE_NUMBER = /^(?:\d{1,8}-(?:19|20)\d{2}|(?:19|20)\d{2}\/S \d{1,3}-\d{1,8})$/i;

/** The tender list's query for these words (`/tenders?...`): a notice number in every status. */
export function tenderListQuery(q: string): Record<string, string> {
  return NOTICE_NUMBER.test(q) ? { q, status: 'all' } : { q };
}

/** The full names an abbreviation stands for, when the search is exactly that abbreviation (a space inside it optional). */
export function buyerNames(text: string): string[] {
  const typed = foldWords(text).join('');
  return typed ? BUYER_ABBREVIATIONS.filter((b) => foldWords(b.abbr).join('') === typed).flatMap((b) => b.names) : [];
}

const SHOWN = 8;

/** "Also searched, the same product in other languages: Drohne, dron, UAV and 6 more." Null when nothing else was searched. */
export function alsoSearchedLine(also: string[] | undefined | null): string | null {
  if (!also?.length) return null;
  const more = also.length - SHOWN;
  return `Also searched, the same product in other languages: ${also.slice(0, SHOWN).join(', ')}${more > 0 ? ` and ${more} more` : ''}.`;
}

/** Every word of `name` begins a word of `text`. */
export function namesAll(name: string, text: string): boolean {
  const have = foldWords(text);
  return foldWords(name).every((w) => have.some((h) => h.startsWith(w)));
}
