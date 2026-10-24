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

/**
 * The names of organisations (`kind` 'title') also keep these: research bodies and companies the sources write in capitals or in
 * lower case ("CNRS", "inria"), and the legal forms that are not also a word. Chosen from the names the directory holds on
 * 19 October 2026 (WP-57); a short word that is also a word of some language ("mit", "foi") is not here.
 */
const NAME_KNOWN = [
  'CNRS', 'TNO', 'VTT', 'INRIA', 'EDF', 'CEA', 'DLR', 'AIT', 'SINTEF', 'NLR', 'ONERA', 'CSIC', 'CNR', 'ENEA', 'GTS', 'MBDA',
  'KNDS', 'BAE', 'OHB', 'GMV', 'ISD', 'DNV', 'GKN', 'ICT', 'INESC', 'INEGI', 'IMDEA', 'FFI', 'DTU', 'KTH', 'NTNU', 'EPFL', 'NOAA',
  'UNESCO', 'OECD', 'CERN', 'JRC', 'TUBITAK',
  // legal forms that are no word
  'SAS', 'SARL', 'SRO', 'DOO', 'UAB', 'SIA', 'ASA', 'EOOD', 'OOD', 'JSC', 'CLG', 'LBG', 'EEIG', 'ASBL', 'ETS', 'SLU', 'SAU',
  'IKE', 'SCPA', 'SNC', 'AIE', 'GIE', 'ApS', 'Kft', 'Lda', 'ehf', 'mbH', 'gGmbH',
  // WP-104: the mark of a Spanish state company (Sociedad Mercantil Estatal), "NAVANTIA SA, SME": not the word "Sme"
  'SME',
  'GmbH', 'Ltd', 'LLC', 'PLC', 'NV', 'BV', 'SRL', 'OYJ',
];
const NAME_KNOWN_BY_KEY = new Map(NAME_KNOWN.map((k) => [k.toLowerCase(), k]));
/**
 * Legal forms that are also words ("as", "ab", "sa", "ag", "ou"): read as the form only as the last word of a name, where
 * they are one ("Nammo Raufoss As" is "AS"; "As Good As Gold" keeps its words).
 */
const FINAL_FORMS = new Map<string, string>([
  ['as', 'AS'], ['ab', 'AB'], ['sa', 'SA'], ['ag', 'AG'], ['ad', 'AD'], ['ae', 'AE'], ['se', 'SE'], ['kg', 'KG'], ['sl', 'SL'],
  ['oy', 'OY'], ['spa', 'SpA'], ['ou', 'OÜ'], ['ev', 'e.V.'],
]);

/** Lower case in a name, unless it opens it (articles, prepositions and particles of the languages we meet). */
const SMALL = new Set([
  'of', 'the', 'and', 'for', 'in', 'on', 'at', 'to', 'de', 'la', 'le', 'les', 'du', 'des', 'del', 'della', 'di', 'da', 'do', 'dos',
  'das', 'van', 'von', 'der', 'den', 'het', 'een', 'en', 'y', 'e', 'et', 'i', 'a', 'o', 'za', 'na', 'w', 'z', 'ze', 'v', 'k', 'pro',
  'und', 'für', 'och', 'av', 'og', 'af', 'fur', 'fuer', 'zur', 'zum', 'u', 'voor',
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
  const known = (kind === 'title' ? NAME_KNOWN_BY_KEY.get(key) : undefined) ?? KNOWN_BY_KEY.get(key);
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
 *
 * A name (`kind` 'title') is also tidied (WP-57): a name with no capital at all is cased as a name ("ministere des armees"),
 * and the acronyms and legal forms of NAME_KNOWN / FINAL_FORMS are written as such wherever they stand in the source's own
 * case ("Cnrs", "Sas", "Gmbh" -> "CNRS", "SAS", "GmbH"). Only the case of letters changes, never the letters; the stored name is
 * not touched.
 */
export function displayName(text: string, kind: NameKind = 'sentence'): string {
  if (!text) return text;
  if (kind === 'title') return tidyName(text);
  return shoutCase(text, kind);
}

/** WP-104: a name of at most three words of at most four letters each, all in capitals, is a row of abbreviations ("DID SDS":
 * Direction d'Infrastructure de la Defense, Saint-Denis), not a shouted name: it is not cased ("Did Sds"). */
function abbreviations(text: string): boolean {
  const words = text.split(/[\s,.;/()-]+/).filter((w) => LETTER.test(w));
  return words.length > 0 && words.length <= 3 && words.every((w) => letterCount(w) <= 4 && !LOWER.test(w));
}

function shoutCase(text: string, kind: NameKind): string {
  if (upperShare(text) < 0.6 || capitalWordShare(text) < 0.75) return text;
  if (kind === 'title' && abbreviations(text)) return text;
  return text.split(/(\s+[-–—]\s+)/).map((part, i) => {
    if (i % 2 === 1 || !part.trim()) return part;
    if (part.trim().split(/\s+/).length === 1 && letterCount(part) <= 4) return part;
    return shout(part, kind);
  }).join('');
}

/** Upper case that never turns one letter into two ("ß" stays one letter, so the letters of a name are the same). */
const upperLetters = (s: string) => Array.from(s, (c) => (c === 'ß' ? 'ẞ' : c.toUpperCase().length === 1 ? c.toUpperCase() : c)).join('');
const HAS_UPPER = /\p{Lu}/u;

/** A letter that comes back as itself after upper and lower case ("ı" does not: it would come back as "i"). */
const roundTrips = (c: string) => c === 'ß' || c.toUpperCase().toLowerCase() === c;

function tidyName(text: string): string {
  // A name with no capital is cased as a name, unless some letter would change on the way ("kızılay": the Turkish dotless i).
  const noCapital = LETTER.test(text) && !HAS_UPPER.test(text) && Array.from(text).every(roundTrips);
  return tidyForms(shoutCase(noCapital ? upperLetters(text) : text, 'title'));
}

/** The case of the acronyms and legal forms of a name, token by token; a token with its own mixed case ("GmbH", "iXblue") is left. */
function tidyForms(input: string): string {
  const name = input.replace(/(\S)\s[Ee]\s[Vv]$/, '$1 e.V.');      // "gesellschaft e v" (the source dropped the dots)
  const tokens = name.match(/\S+/g) ?? [];
  const last = tokens.length - 1;
  let at = -1;
  return name.replace(/\S+/g, (token) => {
    at += 1;
    const core = /^([^\p{L}\p{N}]*)(\p{L}+)([^\p{L}\p{N}]*)$/u.exec(token);
    if (!core) return token;
    const [, head, body, tail] = core;
    const shape = body === body.toLowerCase() || body === body.toUpperCase() || body === capitalise(body.toLowerCase());
    if (!shape) return token;
    const key = body.toLowerCase();
    const form = NAME_KNOWN_BY_KEY.get(key) ?? (at === last && at > 0 ? FINAL_FORMS.get(key) : undefined);
    return form ? `${head}${form}${tail}` : token;
  });
}
