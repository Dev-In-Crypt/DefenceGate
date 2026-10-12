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

/** Name for any country code we show, funder or audience. Falls back to the code. */
export function countryName(code: string): string {
  return COUNTRY_NAMES[code] ?? code;
}

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
  NATIONAL: { label: 'National', name: 'National programmes', slug: 'national' },
};
export const PROGRAMME_CODES = Object.keys(PROGRAMMES) as ProgrammeCode[];

export const REGIMES: Record<Regime, string> = { defence: 'Defence', 'dual-use': 'Dual-use' };
export const REGIME_CODES = Object.keys(REGIMES) as Regime[];

export const LANGUAGES: Record<string, string> = {
  en: 'English', pl: 'Polish', sv: 'Swedish', fr: 'French', es: 'Spanish', fi: 'Finnish', de: 'German', it: 'Italian',
  nl: 'Dutch', cs: 'Czech', ro: 'Romanian', pt: 'Portuguese', uk: 'Ukrainian',
};

export function programmeBySlug(slug: string): ProgrammeCode | undefined {
  return PROGRAMME_CODES.find((c) => PROGRAMMES[c].slug === slug);
}
