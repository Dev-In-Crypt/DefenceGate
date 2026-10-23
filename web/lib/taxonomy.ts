import type { CountryCode, ProgrammeCode, Regime, SourceHealth } from './types';

/** Funder countries the API serves (API_CONTRACT.md). */
export const COUNTRIES: Record<CountryCode, string> = {
  EU: 'European Union', PL: 'Poland', SE: 'Sweden', FR: 'France', ES: 'Spain',
  FI: 'Finland', DE: 'Germany', IT: 'Italy', NL: 'Netherlands',
};

/** Countries DefenceGate's audience is based in (landing page marketing copy, not funder countries). */
export const AUDIENCE_COUNTRIES: string[] = ['PL', 'LT', 'LV', 'EE', 'RO', 'CZ', 'ES', 'PT', 'UA'];
const AUDIENCE_NAMES: Record<string, string> = {
  PL: 'Poland', LT: 'Lithuania', LV: 'Latvia', EE: 'Estonia', RO: 'Romania', CZ: 'Czechia', ES: 'Spain', PT: 'Portugal', UA: 'Ukraine',
};
const COUNTRY_NAMES: Record<string, string> = { ...AUDIENCE_NAMES, ...COUNTRIES };

let regionNames: Intl.DisplayNames | null | undefined;
/** The English name of an ISO 3166 code from the platform's own data (UX walk-through U9: "US, IL, CA" beside "Germany"). */
function regionName(code: string): string | null {
  if (!/^[A-Z]{2}$/.test(code) || code === 'XX') return null;
  if (regionNames === undefined) {
    try { regionNames = new Intl.DisplayNames(['en'], { type: 'region' }); } catch { regionNames = null; }
  }
  try {
    const name = regionNames?.of(code);
    return name && name !== code && !/^unknown/i.test(name) ? name : null;
  } catch { return null; }
}

/** Name for any country code we show, funder or audience. Falls back to the platform's name for the code, then to the code. */
export function countryName(code: string): string {
  return COUNTRY_NAMES[code] ?? BUYER_COUNTRIES[code] ?? regionName(code) ?? code;
}

/**
 * Countries a tender buyer can be in: any ISO-2 the sources carry, not only funder
 * countries. Ordered by how much we hold (12 October 2026); a code outside the list is
 * still shown, as the code.
 */
export const BUYER_COUNTRIES: Record<string, string> = {
  DE: 'Germany', PL: 'Poland', FR: 'France', CZ: 'Czechia', ES: 'Spain', RO: 'Romania',
  IT: 'Italy', GB: 'United Kingdom', FI: 'Finland', NL: 'Netherlands', DK: 'Denmark',
  SE: 'Sweden', NO: 'Norway', BG: 'Bulgaria', SI: 'Slovenia', BE: 'Belgium', LT: 'Lithuania',
  LV: 'Latvia', GR: 'Greece', EE: 'Estonia', HR: 'Croatia', HU: 'Hungary', PT: 'Portugal',
  SK: 'Slovakia', IE: 'Ireland', AT: 'Austria', CY: 'Cyprus', CH: 'Switzerland', MT: 'Malta',
  LU: 'Luxembourg', IS: 'Iceland',
};
export const BUYER_COUNTRY_CODES: string[] = Object.keys(BUYER_COUNTRIES);

/** Every funder country the API can return. The filter narrows this to those with coverage. */
export const FUNDER_COUNTRIES: CountryCode[] = ['EU', 'PL', 'SE', 'FR', 'ES', 'FI', 'DE', 'IT', 'NL'];

/**
 * Funder countries with a grants source that has run at least once, from /v1/sources.
 * Countries already selected in the URL stay visible. Falls back to the full list when no source says anything.
 */
export function fundersWithCoverage(sources: SourceHealth[], selected: CountryCode[] = []): CountryCode[] {
  const covered = FUNDER_COUNTRIES.filter((c) => selected.includes(c) || sources.some((s) => s.type === 'grants' && s.country === c && s.status !== 'never'));
  return covered.length > 0 ? covered : FUNDER_COUNTRIES;
}

/** Currencies offered in the budget filter. EUR first (the default). The source's own currency is never converted. */
export const CURRENCIES: readonly string[] = ['EUR', 'PLN', 'SEK', 'CZK', 'RON', 'DKK', 'NOK', 'GBP'];

export const PROGRAMMES: Record<ProgrammeCode, { label: string; name: string; slug: string }> = {
  EDF: { label: 'EDF', name: 'European Defence Fund', slug: 'edf' },
  EDIP: { label: 'EDIP', name: 'European Defence Industry Programme', slug: 'edip' },
  HORIZON: { label: 'Horizon Europe', name: 'Horizon Europe', slug: 'horizon' },
  DIGITAL: { label: 'Digital Europe', name: 'Digital Europe Programme', slug: 'digital' },
  CEF: { label: 'Connecting Europe', name: 'Connecting Europe Facility', slug: 'cef' },
  NATIONAL: { label: 'National', name: 'National programmes', slug: 'national' },
};
export const PROGRAMME_CODES = Object.keys(PROGRAMMES) as ProgrammeCode[];

export const REGIMES: Record<Regime, string> = { defence: 'Defence', 'dual-use': 'Dual-use' };
export const REGIME_CODES = Object.keys(REGIMES) as Regime[];

/**
 * The 24 official languages of the EU, then the others the sources write in (NO, IS, UK, TR, RU, AR).
 * Looked up in lower case; a code not listed is shown as sent, in capitals.
 */
export const LANGUAGES: Record<string, string> = {
  bg: 'Bulgarian', hr: 'Croatian', cs: 'Czech', da: 'Danish', nl: 'Dutch', en: 'English', et: 'Estonian', fi: 'Finnish',
  fr: 'French', de: 'German', el: 'Greek', hu: 'Hungarian', ga: 'Irish', it: 'Italian', lv: 'Latvian', lt: 'Lithuanian',
  mt: 'Maltese', pl: 'Polish', pt: 'Portuguese', ro: 'Romanian', sk: 'Slovak', sl: 'Slovenian', es: 'Spanish', sv: 'Swedish',
  no: 'Norwegian', nb: 'Norwegian', nn: 'Norwegian', is: 'Icelandic', uk: 'Ukrainian', tr: 'Turkish', ru: 'Russian', ar: 'Arabic',
};

/** Language codes arrive as `en`, `ES` or `Pl`: look them up in lower case. An unknown code is shown in capitals. */
export function languageName(code: string): string {
  const c = code.trim().toLowerCase();
  return LANGUAGES[c] ?? c.toUpperCase();
}
/** A title language that is not English gets a label. A missing language is not labelled. */
export function isNonEnglish(code: string | null | undefined): boolean {
  return Boolean(code) && code!.toLowerCase() !== 'en';
}

export function programmeBySlug(slug: string): ProgrammeCode | undefined {
  return PROGRAMME_CODES.find((c) => PROGRAMMES[c].slug === slug);
}

/**
 * How a tender's scope is named. `supply` is "supplies to a defence buyer", never "defence notice". It also holds the
 * two groups of 14 October 2026 (`also`): the directive's legal basis alone from a civil buyer, and a military product
 * code alone from a police, prison, border, customs or tax body.
 */
export const TENDER_SCOPES: Record<'core' | 'supply', { label: string; hint: string; also?: string }> = {
  core: { label: 'Military goods and works', hint: 'The notice itself is defence.' },
  supply: {
    label: 'Other purchase by armed forces',
    hint: 'Only the buyer is a defence body; the notice itself is not marked as defence.',
    also: 'This list also holds notices with a single defence signal from the wrong kind of buyer: “Filed under the defence procurement directive by a civil buyer”, and “Security-body purchase of a military-type product code” (police, prison, border, customs or tax bodies).',
  },
};

/**
 * The one glossary of scope names (owner decision of 16 October 2026): the home page, the scope filter, the cards, the
 * glossary and the methodology all take their words from here, and the URL value is the key. `relevant` is the default
 * and is left out of URLs.
 */
export const SCOPE_CHOICES: Record<'relevant' | 'core' | 'supply' | 'all', { label: string; short: string; hint: string }> = {
  relevant: {
    label: 'All defence', short: 'All defence',
    hint: 'Both lists below together. This is what the site shows unless you choose another.',
  },
  core: { label: 'Military goods and works', short: 'Military goods and works', hint: TENDER_SCOPES.core.hint },
  supply: { label: 'Other purchases by armed forces', short: 'Other purchases by armed forces', hint: TENDER_SCOPES.supply.hint },
  all: { label: 'Everything, also dual-use purchases of civil buyers', short: 'All notices', hint: 'Everything we hold that has any defence signal, also a military code bought by a municipality or a hospital.' },
};

/** Legal bases we can name. Anything else is shown as the source gives it. */
const LEGAL_BASES: Record<string, string> = {
  '32009L0081': 'Directive 2009/81/EC (defence and security procurement)',
  '32014L0024': 'Directive 2014/24/EU (public procurement)',
  '32014L0025': 'Directive 2014/25/EU (utilities procurement)',
  '32014L0023': 'Directive 2014/23/EU (concessions)',
  // WP-88: PLACSP's code for an ordinary contract, in words (Spain's public sector contracts law)
  'Ley 9/2017 (LCSP)': 'Spanish public sector contracts law (Ley 9/2017)',
};
export function legalBasisLabel(code: string): string | null {
  const k = code.trim();
  if (k.toLowerCase() === 'other') return 'Other legal basis (not one of the EU procurement directives)';
  return LEGAL_BASES[k] ?? LEGAL_BASES[k.toUpperCase()] ?? null;
}

/**
 * Procedure names the sources give in their own language, in English. Keys are lower case with accents and
 * punctuation folded to single spaces. A name not listed here is shown exactly as the source states it.
 */
const PROCEDURES: Record<string, string> = {
  'open': 'Open procedure', 'ouvert': 'Open procedure', 'procedure ouverte': 'Open procedure', 'appel d offres ouvert': 'Open procedure',
  'abierto': 'Open procedure', 'procedimiento abierto': 'Open procedure', 'openbaar': 'Open procedure', 'openbare procedure': 'Open procedure',
  'restricted': 'Restricted procedure', 'restreint': 'Restricted procedure', 'procedure restreinte': 'Restricted procedure',
  'appel d offres restreint': 'Restricted procedure', 'restringido': 'Restricted procedure', 'procedimiento restringido': 'Restricted procedure',
  'niet openbaar': 'Restricted procedure', 'niet openbare procedure': 'Restricted procedure',
  'negociee': 'Negotiated procedure', 'negocie': 'Negotiated procedure', 'procedure negociee': 'Negotiated procedure',
  'negociado': 'Negotiated procedure', 'procedimiento negociado': 'Negotiated procedure', 'onderhandelingsprocedure': 'Negotiated procedure',
  'negociado con publicidad': 'Negotiated procedure with prior publication', 'procedimiento negociado con publicidad': 'Negotiated procedure with prior publication',
  'negociado sin publicidad': 'Negotiated procedure without prior publication', 'procedimiento negociado sin publicidad': 'Negotiated procedure without prior publication',
  'dialogue competitif': 'Competitive dialogue', 'dialogo competitivo': 'Competitive dialogue', 'concurrentiegerichte dialoog': 'Competitive dialogue',
};

/** The English name of a procedure the source gave in another language; null when it is not one we know (show it as stated). */
export function procedureLabel(procedure: string): string | null {
  const key = procedure.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const label = PROCEDURES[key];
  return label && label.toLowerCase() !== procedure.trim().toLowerCase() ? label : null;
}

/**
 * CPV (Common Procurement Vocabulary) names for the codes we meet most: the whole of division 35 and the
 * division level of the rest. Codes outside this table are shown as a bare code, never guessed.
 */
const CPV_LABELS: Record<string, string> = {
  // WP-87: the four divisions /suppliers showed without a name (titles from the CPV 2008 vocabulary, lib/data/cpv-full.json)
  '16': 'Agricultural machinery',
  '41': 'Collected and purified water',
  '76': 'Services related to the oil and gas industry',
  '77': 'Agricultural, forestry, horticultural, aquacultural and apicultural services',
  '03': 'Agricultural, farming, fishing, forestry and related products',
  '09': 'Petroleum products, fuel, electricity and other sources of energy',
  '14': 'Mining, basic metals and related products',
  '15': 'Food, beverages, tobacco and related products',
  '18': 'Clothing, footwear, luggage articles and accessories',
  '19': 'Leather and textile fabrics, plastic and rubber materials',
  '22': 'Printed matter and related products',
  '24': 'Chemical products',
  '30': 'Office and computing machinery, equipment and supplies',
  '31': 'Electrical machinery, apparatus, equipment and consumables',
  '32': 'Radio, television, communication, telecommunication and related equipment',
  '33': 'Medical equipments, pharmaceuticals and personal care products',
  '34': 'Transport equipment and auxiliary products to transportation',
  '35': 'Security, fire-fighting, police and defence equipment',
  '38': 'Laboratory, optical and precision equipments',
  '37': 'Musical instruments, sport goods, games, toys, handicraft, art materials and accessories',   // titles of 37 and 92 verbatim from the CPV 2008 vocabulary (U9: they showed no name)
  '39': 'Furniture, furnishings, domestic appliances and cleaning products',
  '42': 'Industrial machinery',
  '43': 'Machinery for mining, quarrying, construction equipment',
  '44': 'Construction structures and materials',
  '45': 'Construction work',
  '48': 'Software package and information systems',
  '50': 'Repair and maintenance services',
  '51': 'Installation services',
  '55': 'Hotel, restaurant and retail trade services',
  '60': 'Transport services',
  '63': 'Supporting and auxiliary transport services',
  '64': 'Postal and telecommunications services',
  '65': 'Public utilities',
  '66': 'Financial and insurance services',
  '70': 'Real estate services',
  '71': 'Architectural, construction, engineering and inspection services',
  '72': 'IT services: consulting, software development, Internet and support',
  '73': 'Research and development services and related consultancy services',
  '75': 'Administration, defence and social security services',
  '79': 'Business services: law, marketing, consulting, recruitment, printing and security',
  '80': 'Education and training services',
  '85': 'Health and social work services',
  '90': 'Sewage, refuse, cleaning and environmental services',
  '92': 'Recreational, cultural and sporting services',
  '98': 'Other community, social and personal services',
  '351': 'Emergency and security equipment',
  '352': 'Police equipment',
  '353': 'Weapons, ammunition and associated parts',
  '354': 'Military vehicles and associated parts',
  '355': 'Warships and associated parts',
  '356': 'Military aircraft, missiles and spacecraft',
  '357': 'Military electronic systems',
  '358': 'Individual and support equipment',
};

/** The title of a 2-digit CPV division (`45`), or null when we do not hold it. */
export function cpvDivisionLabel(code: string): string | null {
  return /^\d{2}/.test(code) ? (CPV_LABELS[code.slice(0, 2)] ?? null) : null;
}

/**
 * Name for a CPV code: the 3-digit group where we know it, else the 2-digit division, else null.
 * `exact` is false when the name is that of the enclosing group or division, not of the code itself.
 */
export function cpvLabel(code: string): { label: string; exact: boolean } | null {
  const digits = /^\d{8}/.exec(code)?.[0];
  if (!digits) return null;
  const group = CPV_LABELS[digits.slice(0, 3)];
  if (group) return { label: group, exact: digits.slice(3) === '00000' };
  const division = CPV_LABELS[digits.slice(0, 2)];
  if (division) return { label: division, exact: digits.slice(2) === '000000' };
  return null;
}
