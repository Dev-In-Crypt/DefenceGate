/**
 * Words, formats and the one browser call of the readiness check. Pure except `assess`, which posts the
 * request of `lib/profile.ts` to the site's own `/api/readiness/assess` and keeps nothing.
 * lib/readiness.check.ts runs the pure parts on its own.
 */
import type { AssessRequest } from './profile';
import { countryInText, countryName } from './taxonomy';
import { fetchPatiently } from './answer-cache';
import { formatDateUtc, plural } from './format';
import type { Assessment, Outcome, RIssuer, RMoney, RSource, RSpan, RequirementDetail, RoadmapTotals, Verdict, VerificationStatus } from './readiness-types';

export const VERDICT_WORD: Record<Verdict, string> = { eligible: 'Eligible', obtain: 'Obtain first', blocked: 'Blocked', conditional: 'Conditional' };
export const VERDICT_MEANING: Record<Verdict, string> = {
  eligible: 'No rule of this programme blocks you on the answers given. This does not cover the exclusion criteria and the capacity checks of the Financial Regulation, or the conditions each call sets.',
  obtain: 'Every rule that applicants must meet is met except a registration you can obtain. Once you hold it, no rule of this programme blocks you on the answers given.',
  blocked: 'At least one rule that every applicant must meet is not met.',
  conditional: 'No rule is plainly broken, but a condition applies or an answer is missing.',
};
/**
 * The meanings on a supply route (NATO and NSPA, the Spanish Ministry of Defence): its rules bind a supplier where they apply (the HSEM where
 * classified information is handled), and the Financial Regulation of EU funding has nothing to say about a purchase (QA m-1, WP-73).
 */
const ROUTE_MEANING: Record<Verdict, string> = {
  eligible: 'No rule of this route blocks you on the answers given. Each buyer sets further conditions in its tender documents.',
  obtain: 'Every rule of this route that applies to you is met except a registration you can obtain. Once you hold it, no rule of this route blocks you on the answers given.',
  blocked: 'At least one rule of this route that applies to you, and that a supplier must meet, is not met.',
  conditional: 'No rule is plainly broken, but a condition applies or an answer is missing.',
};
export function verdictMeaning(a: { kind: string; verdict: Verdict }): string {
  return (a.kind === 'route' ? ROUTE_MEANING : VERDICT_MEANING)[a.verdict];
}

export const OUTCOME_WORD: Record<Outcome, string> = {
  met: 'Met', not_met: 'Not met', to_obtain: 'To obtain', conditional: 'Conditional', unknown: 'Needs an answer',
  not_applicable: 'Does not apply', info: 'For information',
};

/**
 * What a verification status means for a line, depending on where its text comes from. A line taken from the
 * research notes was marked verified when the notes were written; this site did not read its source again, and
 * says so instead of "the page was fetched".
 */
export function statusWords(status: VerificationStatus, origin: 'primary' | 'notes' | 'call_document', url?: string | null): string {
  // a national law or a ministry page (WP-64) is a primary source too, but not the Official Journal
  const national = origin === 'primary' && !!url && !isOfficialJournal(url);
  if (national && status === 'V') return 'Verified: the text was checked against the official source linked here.';
  if (national && status === 'S') return 'Partly verified: the text was read in the official source linked here, but the rule rests on an interpretation of it.';
  if (status === 'V') {
    if (origin === 'call_document') return 'Verified: the sentence was checked against the Commission’s call document named in the reference, not against the Official Journal.';
    return origin === 'primary'
      ? 'Verified: the text was checked against the Official Journal text of the regulation.'
      : 'Marked verified in the DefenceGate research notes when they were written (7 September 2026); not checked again on this site.';
  }
  if (status === 'S') return 'Seen in search results, not fetched directly.';
  return 'Unverified: a lead to check, not a fact.';
}

/** The sentence a requirement page prints for a rule: what it asks (never the "not met" verdict text). */
export function ruleSentence(texts: Record<string, string>): string {
  return withoutAnswerEcho(texts.requires ?? texts.info ?? '');
}

/**
 * A static page speaks to nobody who has answered anything: a leading sentence that repeats an answer ("You said you move dual-use
 * items to other EU countries.") is left out of the text a requirement page prints; the rest of the text is unchanged.
 */
export function withoutAnswerEcho(text: string): string {
  return text.replace(/^(?:You said[^.]*\.\s*)+/, '');
}

/**
 * The programme keys of the rules, in words (U13: "Appears in the rules of GENERAL", "NATO-SUPPLY", "EDIP-USI" were shown as they are
 * stored). A key that is not here is shown as it is.
 */
export const PROGRAMME_NAME: Record<string, string> = {
  EDF: 'EDF', EDIP: 'EDIP', 'EDIP-USI': 'EDIP Ukraine Support Instrument', SAFE: 'SAFE', 'NATO-SUPPLY': 'NATO and NSPA supply',
  'ES-MOD': 'Spanish defence supplier (MoD)', GENERAL: 'the general requirements',
};
export const programmeName = (code: string): string => PROGRAMME_NAME[code] ?? code;

/** WP-112: the routes that are one country's own: their rules say nothing about a company of another country. */
export const ROUTE_COUNTRY: Record<string, string> = { 'ES-MOD': 'ES' };

/**
 * WP-112 (p03: ISO 9001 and EN 9100 "Appear in the rules of Spanish defence supplier (MoD)" on /requirements for Germany): the routes
 * whose rules name a requirement, for the visitor's country. Another country's own route is left out; when only such routes name it,
 * the line says that no rule we hold for this country does (no source is put in its place). `countryWord`: "Germany".
 */
export function appearsLine(programmes: readonly string[], country = '', countryWord = country): string {
  const own = programmes.filter((p) => !country || !ROUTE_COUNTRY[p] || ROUTE_COUNTRY[p] === country);
  if (own.length > 0) return `Appears in the rules of ${joinWords(own.map(programmeName))}. `;
  if (programmes.length === 0) return '';
  return `No rule we hold for ${countryWord} names it; we hold it from the rules of ${joinWords(programmes.map(programmeName))} only. `;
}
/** "A, B and C" */
export function joinWords(items: string[]): string {
  return items.length <= 1 ? (items[0] ?? '') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

export const OBLIGATION_WORD = { mandatory: 'Required', conditional: 'Only in some cases', recommended: 'Recommended' } as const;

export const CATEGORY_WORD: Record<string, string> = {
  identification: 'Identification', registration: 'Registration', quality: 'Quality', export_control: 'Export control',
  security: 'Security clearance', integrity: 'Integrity', admission: 'Eligibility rule', origin: 'Origin rule',
};

const nf = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });

/** WP-89: the one words for a cost or a time that no source states, on the report, the roadmap and the requirement pages alike. */
export const NOT_STATED = 'Not stated by the source';

/** "USD 17,000 to 48,000", "free", or "not stated". Money is never converted. */
export function formatRange(m: RMoney | null): string {
  if (!m || m.min === null || m.max === null) return NOT_STATED;
  if (m.basis === 'free') return 'Free';
  const cur = m.currency ?? '';
  return m.min === m.max ? `${cur} ${nf.format(m.min)}` : `${cur} ${nf.format(m.min)} to ${nf.format(m.max)}`;
}

/** Days as the sources speak: "immediate", "3 to 8 months", "4 to 20 days"; when they give no words, "no time needed" for zero. */
export function formatDays(s: RSpan | null): string {
  if (!s || s.min === null || s.max === null) return NOT_STATED;
  return s.text ?? daysRange(s.min, s.max);
}

/**
 * WP-89 (UX audit, section 4): one cost statement per requirement, wherever it is shown (report, roadmap, requirement pages, a call's
 * readiness block): the source's own words when it gives them ("Free of charge (NSPA)", "USD 17,000 to 48,000 ... (vendor quote)"), else
 * the range, else NOT_STATED. The report used to say "Not stated in a primary source" where the roadmap said "Free".
 */
export function costStatement(m: RMoney | null): string {
  if (!m || m.min === null || m.max === null) return NOT_STATED;
  return m.text ?? formatRange(m);
}

/** The time of a requirement, the same everywhere (see `costStatement`). */
export function timeStatement(s: RSpan | null): string {
  return formatDays(s);
}

/** "0 to 0 days" read as a mistake (U8): a step that is issued at once needs no time. */
export function daysRange(min: number, max: number): string {
  if (max === 0) return 'no time needed';
  const unit = (n: number) => (n >= 60 ? `${Math.round(n / 30)} months` : `${n} ${plural(n, 'day')}`);
  if (min === max) return unit(max);
  return max >= 60 && min >= 60 ? `${Math.round(min / 30)} to ${Math.round(max / 30)} months` : `${min} to ${max} days`;
}

const stepsWord = (n: number): string => `${n} ${n === 1 ? 'step' : 'steps'}`;

/**
 * The cost in the headline of the roadmap, from the cost data of its steps (WP-53, T7). "Free" only when every step states that it is free;
 * a plan in which some steps state no cost never reads as a complete or a free plan: it says how many are free, how many have no stated
 * cost, and the sum of the ones that state a price. `steps`: how many steps the total is over; `unknown`: how many of them state no cost.
 */
export function costHeadline(totals: RoadmapTotals, steps: number, unknown: number): string {
  const money = totals.cost.map((c) => `${c.currency} ${c.min.toLocaleString('en-GB')} to ${c.max.toLocaleString('en-GB')}`).join(' and ');
  if (unknown <= 0) return money || (totals.freeSteps.length > 0 && totals.freeSteps.length >= steps ? 'Free' : totals.freeSteps.length > 0 ? `${stepsWord(totals.freeSteps.length)} free` : 'Nothing is stated');
  const free = totals.freeSteps.length;
  const parts = [money, free > 0 ? `${stepsWord(free)} free` : '', free > 0 ? `${unknown} with no stated cost` : `${stepsWord(unknown)} with no stated cost`].filter(Boolean);
  return parts.join(', ');
}

/** The time in the headline: the range of the steps that state one, and how many state none (a plan of unknown time is not "no time needed"). */
export function timeHeadline(days: { min: number; max: number }, steps: number, unknown: number): string {
  if (unknown <= 0) return daysRange(days.min, days.max);
  if (unknown >= steps) return `${stepsWord(unknown)} with no stated time`;
  return `${daysRange(days.min, days.max)}, ${unknown} with no stated time`;
}

/** The source line under a rule: where the text comes from, in words a visitor can check. */
/** EUR-Lex or the Publications Office: the Official Journal. Anything else quoted as primary is a national law or an official page. */
export function isOfficialJournal(url: string): boolean {
  return /^https?:\/\/(?:[a-z-]+\.)*(?:eur-lex\.europa\.eu|publications\.europa\.eu)\//i.test(url);
}

export function originWords(s: RSource): string {
  if (s.origin === 'primary' && s.url && !isOfficialJournal(s.url)) return `Quoted from the official source linked here, read on ${isoDay(s.lastReviewed)}.`;
  if (s.origin === 'call_document') return 'Quoted from the Commission’s call document named in the reference; the Official Journal text does not say it.';
  return s.origin === 'primary'
    ? 'Quoted from the Official Journal text of the regulation.'
    : 'Quoted from the DefenceGate research notes of 7 September 2026; the primary page was not re-read for this line.';
}

export function isoDay(value: string): string {
  return /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : value;
}

/** A day the way the rest of the site writes it: "7 Sep 2026" (a value that is not a day is shown as it is). */
export function siteDay(value: string): string {
  return /^\d{4}-\d{2}-\d{2}/.test(value) ? formatDateUtc(value.slice(0, 10)) : value;
}

/**
 * The name of a source without the name of our own working document. A reference such as "NSPA, quoted in the DefenceGate technical
 * appendix, NCAGE" is shown as "NSPA"; one that is only the document and a section of it ("DefenceGate technical appendix, Export
 * control") has no name left and is null: the page shows the link to the source instead. Anything else is returned as it is.
 */
export function publicRef(ref: string | null): string | null {
  if (!ref) return ref;
  const at = ref.indexOf('DefenceGate technical appendix');
  if (at < 0) return ref;
  const head = ref.slice(0, at).replace(/[,\s]*(?:quoted in the)?\s*$/i, '').trim();
  return head || null;
}

/**
 * One verbatim passage as stored, "[reference] text": the reference is shown by its public name, or not at all. A text that starts
 * inside a sentence ("register the organisation ...", the reference was its subject) opens with an ellipsis, and a table row
 * quoted from the appendix ("AQAP 2310 | Edition B ...") shows its cells separated by " · " instead of pipes.
 */
export function publicPassage(passage: string): string {
  const m = /^\[([^\]]*)\]\s*([\s\S]*)$/.exec(passage);
  if (!m) return passage;
  const ref = publicRef(m[1]);
  const text = m[2].replace(/ \| /g, ' · ').replace(/^(?=\p{Ll})/u, '…');
  return ref ? `[${ref}] ${text}` : text;
}

/**
 * The issuers of a requirement as the public page lists them. Rows that carry the same body, note, link and status (50 country rows of
 * NCAGE say "National codification bureau of the country, UNVERIFIED ...") are one group with a count and the countries by name; every
 * row's country is kept. A group needs `GROUP_MIN` rows. The rest are single rows: the row for every country first, then by country name.
 */
export const GROUP_MIN = 3;
export interface IssuerGroup { name: string; notes: string | null; url: string | null; verificationStatus: VerificationStatus; countries: string[] }
export function groupIssuers(issuers: RIssuer[]): { singles: RIssuer[]; groups: IssuerGroup[] } {
  const by = new Map<string, RIssuer[]>();
  for (const i of issuers) {
    const key = JSON.stringify([i.name, i.notes, i.url, i.verificationStatus]);
    by.set(key, [...(by.get(key) ?? []), i]);
  }
  const singles: RIssuer[] = [];
  const groups: IssuerGroup[] = [];
  for (const rows of by.values()) {
    if (rows.length >= GROUP_MIN && rows.every((r) => r.country !== '*')) {
      const [first] = rows;
      groups.push({ name: first.name, notes: first.notes, url: first.url, verificationStatus: first.verificationStatus,
        countries: rows.map((r) => countryName(r.country)).sort((a, b) => a.localeCompare(b, 'en')) });
    } else singles.push(...rows);
  }
  const label = (i: RIssuer) => (i.country === '*' ? '' : countryName(i.country));
  singles.sort((a, b) => label(a).localeCompare(label(b), 'en'));
  groups.sort((a, b) => b.countries.length - a.countries.length || a.name.localeCompare(b.name, 'en'));
  return { singles, groups };
}

/**
 * WP-91 (UX audit 6: "Issued by: PL National codification bureau (NCB) of the country / UNVERIFIED: ..."). NSPA's NCAGE request page: the
 * address of the requirements seed's REQ-NCAGE row for every other country (`*`); lib/wp91.check.ts holds the two equal.
 */
export const NSPA_NCAGE_URL = 'https://eportal.nspa.nato.int/Codification/CageTool/request-new-cage';

/** Who issues a requirement in one country, as plainly as our sources allow (never a body we have not verified). */
export type IssuerAnswer =
  | { kind: 'verified'; issuer: RIssuer }
  | { kind: 'unverified'; text: string; link: { label: string; url: string } | null }
  | { kind: 'none'; text: string };

/** WP-97: who issues the NCAGE code where our sources have not verified the national office, in the plain "not covered yet" words. */
export function ncageText(country: string): string {
  return `Not covered yet for ${countryInText(country)}: which office issues NCAGE codes (for a NATO member, its national codification bureau). Check with NSPA, whose NCAGE request tool is where a request starts.`;
}

export function issuerFor(code: string, issuers: RIssuer[], country: string): IssuerAnswer {
  const name = countryName(country);
  const own = issuers.filter((i) => i.country === country);
  const verified = own.find((i) => i.verificationStatus === 'V') ?? (own.length === 0 ? issuers.find((i) => i.country === '*' && i.verificationStatus === 'V') : undefined);
  if (verified) return { kind: 'verified', issuer: verified };
  const ncage = code === 'REQ-NCAGE';
  if (own.length > 0) {
    return {
      kind: 'unverified',
      // WP-97: the NCAGE words are one sentence everywhere (requirements page, roadmap, report, country route: `ncageText`)
      text: ncage ? ncageText(country) : `Not verified in our sources: we have not confirmed which body issues this in ${name}. Ask the national authority before you rely on any name.`,
      link: ncage ? { label: 'NSPA: request an NCAGE code', url: NSPA_NCAGE_URL } : null,
    };
  }
  return { kind: 'none', text: `The body that issues this in ${name} has not been collected. We list none rather than guess.` };
}

/** The slug of a requirement page: `REQ-AQAP2110` is `/requirements/aqap2110`. */
export function requirementSlug(code: string): string {
  return code.replace(/^REQ-/, '').toLowerCase();
}
export function requirementCode(slug: string): string | null {
  return /^[a-z0-9-]{1,30}$/i.test(slug) ? `REQ-${slug.replace(/^req-/i, '').toUpperCase()}` : null;
}

export class AssessError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export const ASSESS_FAILED = 'The check could not be computed. Try again in a moment.';

/** Compute the verdict: the one call that leaves the browser. Nothing is kept by the server. */
export async function assess(request: AssessRequest, signal?: AbortSignal): Promise<Assessment> {
  const res = await fetchPatiently('/api/readiness/assess', {
    method: 'POST', headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(request), signal, cache: 'no-store', credentials: 'omit',
  }).catch((e: unknown) => {
    // No answer at all (offline, blocked): the browser's own words ("Failed to fetch") are not shown, ours are (WP-58).
    if (signal?.aborted) throw e;
    throw new AssessError(0, ASSESS_FAILED);
  });
  if (!res.ok) throw new AssessError(res.status, res.status === 429 ? 'Too many requests. Wait a minute and try again.' : ASSESS_FAILED);
  return (await res.json()) as Assessment;
}

/**
 * The questions a requirement page answers, built from its own data. The page shows them as text and the
 * structured data repeats the same strings, so the markup never claims more than the page says.
 */
export function faqOf(r: RequirementDetail): { q: string; a: string }[] {
  const out: { q: string; a: string }[] = [];
  if (r.kind === 'document') {
    const { singles, groups } = groupIssuers(r.issuers);
    // A row for every country ('*') covers the countries not listed: alone it is the one body, next to country rows it is the rest.
    const every = singles.filter((i) => i.country === '*');
    const listed = [
      ...singles.filter((i) => i.country !== '*').map((i) => `${countryName(i.country)}: ${i.name}`),
      ...groups.map((g) => `${g.name}: ${joinWords(g.countries)}`),
    ];
    const parts = listed.length === 0
      ? every.map((i) => `${i.name} (the same body for every country)`)
      : [...listed, ...every.map((i) => `Every other country: ${i.name}`)];
    out.push({
      q: `Who issues ${r.name}?`,
      a: parts.length > 0 ? `${parts.join('. ')}.${every.length > 0 ? '' : ' The body has not been collected for the countries not listed.'}` : 'The issuing body has not been collected for any country.',
    });
    out.push({ q: `How much does ${r.name} cost?`, a: r.cost ? `${costStatement(r.cost)}.${r.cost.label ? ` Note: ${r.cost.label}.` : ''}` : 'No cost is stated in the sources used.' });
    out.push({ q: `How long does ${r.name} take?`, a: r.days ? `${formatDays(r.days)}.` : 'No duration is stated in the sources used.' });
  }
  if (r.mandatoryFor) out.push({ q: `Who needs ${r.name}?`, a: r.mandatoryFor });
  return out;
}
