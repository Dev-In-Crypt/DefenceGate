/**
 * Display-only case for titles and buyer names that sources publish in capitals ("MINISTRSTVO ZA OBRAMBO").
 * The stored value is never changed: this runs where a name is drawn, and nowhere else (not in exports,
 * not in the evidence record, which shows what we hold).
 *
 * A string with fewer than 60% of its letters in upper case is left alone, and so is one in which fewer than
 * three words in four are written wholly in capitals ("EIC STEP Scale Up" is a title with two acronyms in it, not
 * a shouted one). In a shouting string a word that is already mixed case ("France", "Scale") is left as it is, and
 * the word after a dash opens a new sentence ("France - honey - FOURNITURE DE MIEL": the TED-composed prefix is
 * not ours to lower-case). In a shouting string these
 * stay as they are: codes with digits ("S2A", "A400M"), anything with a slash ("MINARM/DGA/DO/S2A"),
 * identifiers with digits or underscores ("2024-ESID-TLN-0046"), initialisms ("O.O."), known acronyms and
 * legal forms, and Roman numerals.
 * Pure and import-free so lib/ui.check.ts can run it on its own.
 */

/** Canonical spelling of the acronyms we meet in defence procurement. Matched without regard to case. */
const KNOWN = [
  'NATO', 'EDA', 'OCCAR', 'NSPA', 'EU', 'UK', 'MOD', 'MON', 'EDF', 'EDIP', 'BAAINBw', 'TED', 'CPV', 'EIC', 'EIB', 'ESA',
  // legal forms: "SA" is not the word "sa"
  'SA', 'AB', 'NV', 'BV', 'OY', 'OYJ', 'SL', 'SRL', 'AG', 'KG', 'GmbH', 'SpA', 'Ltd', 'LLC', 'PLC',
];
const KNOWN_BY_KEY = new Map(KNOWN.map((k) => [k.toLowerCase(), k]));

/** Lower case in a name, unless it opens it (articles, prepositions and particles of the languages we meet). */
const SMALL = new Set([
  'of', 'the', 'and', 'for', 'in', 'on', 'at', 'to', 'de', 'la', 'le', 'les', 'du', 'des', 'del', 'della', 'di', 'da', 'do', 'dos',
  'das', 'van', 'von', 'der', 'den', 'het', 'een', 'en', 'y', 'e', 'et', 'i', 'a', 'o', 'za', 'na', 'w', 'z', 'ze', 'v', 'k', 'pro',
  'und', 'für', 'och', 'av', 'og', 'af',
]);

/** Words after which a lone "I" is a numeral ("Phase I"), not the Polish "and". */
const NUMBERED = /^(part|phase|lot|stage|annex|class|group|type|level|etap|część|czesc|zadanie|lote|parte|teil|partie|los)$/i;

const ROMAN = /^(?:X{0,2})(?:IX|IV|V?I{0,3})$/;
const LETTER = /\p{L}/u;
const UPPER = /\p{Lu}/u;

export type NameKind = 'title' | 'sentence';

/** Share of the letters that are upper case; 0 when there are no letters. */
export function upperShare(s: string): number {
  let letters = 0;
  let upper = 0;
  for (const ch of s) {
    if (!LETTER.test(ch)) continue;
    letters += 1;
    if (UPPER.test(ch)) upper += 1;
  }
  return letters === 0 ? 0 : upper / letters;
}

const capitalise = (w: string) => {
  const chars = Array.from(w);
  const at = chars.findIndex((c) => LETTER.test(c));
  if (at < 0) return w;
  chars[at] = chars[at].toUpperCase();
  return chars.join('');
};

function letterCount(s: string): number {
  let n = 0;
  for (const ch of s) if (LETTER.test(ch)) n += 1;
  return n;
}

const LOWER = /\p{Ll}/u;

/** Share of the words (two letters or more) that are written wholly in capitals; 1 when there are none. */
export function capitalWordShare(s: string): number {
  let words = 0;
  let caps = 0;
  for (const token of s.split(/\s+/)) {
    if (letterCount(token) < 2) continue;
    words += 1;
    if (!LOWER.test(token)) caps += 1;
  }
  return words === 0 ? 1 : caps / words;
}

/** One hyphen-free word of a shouting string. `first`: it opens the string. `prev`: the word before it. */
function word(w: string, first: boolean, prev: string, kind: NameKind): string {
  if (!LETTER.test(w)) return w;
  if (LOWER.test(w)) return w;      // a word with a lower-case letter is not shouted: "France", "honey", "BAAINBw"
  const key = w.toLowerCase().replace(/\.$/, '');
  const known = KNOWN_BY_KEY.get(key);
  if (known) return known;
  if (/^\p{L}(?:\.\p{L})+$/u.test(w)) return w;                              // S.A  U.S.A  (the last dot is peeled off)
  if (w.length === 1 ? w === 'I' && NUMBERED.test(prev) : ROMAN.test(w)) return w;   // Roman numerals
  const lower = w.toLowerCase();
  if (!first && kind === 'title' && SMALL.has(lower)) return lower;
  let out = first || kind === 'title' ? capitalise(lower) : lower;
  if (kind === 'title') {
    // d'Armement, dell'Aeronautica: the part after a short article is a name again
    out = out.replace(/^(\p{L}{1,4})(['’])(\p{L}{3,})/u, (_m, a: string, q: string, b: string) => `${a}${q}${capitalise(b)}`);
  }
  return out;
}

/** One dash-free stretch of a shouting string, in the case of `kind`. */
function shout(text: string, kind: NameKind): string {
  let first = true;
  let prev = '';
  return text.replace(/(\s+)|(\S+)/g, (_m, space: string | undefined, token: string | undefined) => {
    if (space !== undefined) return space;
    const t = token as string;
    const core = /^([^\p{L}\p{N}]*)(.*?)([^\p{L}\p{N}]*)$/u.exec(t) ?? [t, '', t, ''];
    const [, head, body, tail] = core;
    let shown = body;
    if (body && LETTER.test(body)) {
      // A code ("S2A", "F-35", "2024-ESID-TLN-0046"), a file-like name ("AMOA_MAYOTTE") or anything with a slash is
      // left exactly as published: a token with a digit is an identifier, not a shouted word.
      const code = /\d/.test(body) || body.includes('/') || body.includes('_');
      if (!code) {
        shown = body.split('-').map((part, i) => word(part, first && i === 0, i === 0 ? prev : '', kind)).join('-');
      }
    }
    first = first && !LETTER.test(body);
    prev = body;
    return `${head}${shown}${tail}`;
  });
}

/**
 * `text` as a person reads it: sentence case for a title, title case for a name. Anything that is not
 * mostly upper case is returned unchanged, and so is a single short word (an acronym). Stretches between
 * " - " are read one by one: each opens a sentence, and a stretch that is one short word ("BNT" in
 * "2024-ESID-TLN-0046 - BNT - ASSISTANCE A MAITRISE D'OUVRAGE") is a code and stays.
 */
export function displayName(text: string, kind: NameKind = 'sentence'): string {
  if (!text || upperShare(text) < 0.6 || capitalWordShare(text) < 0.75) return text;
  return text.split(/(\s+[-–—]\s+)/).map((part, i) => {
    if (i % 2 === 1 || !part.trim()) return part;
    if (part.trim().split(/\s+/).length === 1 && letterCount(part) <= 4) return part;
    return shout(part, kind);
  }).join('');
}
