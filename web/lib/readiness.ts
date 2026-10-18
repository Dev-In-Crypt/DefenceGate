/**
 * Words, formats and the one browser call of the readiness check. Pure except `assess`, which posts the
 * request of `lib/profile.ts` to the site's own `/api/readiness/assess` and keeps nothing.
 * lib/readiness.check.ts runs the pure parts on its own.
 */
import type { AssessRequest } from './profile';
import { countryName } from './taxonomy';
import type { Assessment, Outcome, RMoney, RSource, RSpan, RequirementDetail, Verdict, VerificationStatus } from './readiness-types';

export const VERDICT_WORD: Record<Verdict, string> = { eligible: 'Eligible', obtain: 'Obtain first', blocked: 'Blocked', conditional: 'Conditional' };
export const VERDICT_MEANING: Record<Verdict, string> = {
  eligible: 'No rule of this programme blocks you on the answers given. This does not cover the exclusion criteria and the capacity checks of the Financial Regulation, or the conditions each call sets.',
  obtain: 'Every rule that applicants must meet is met except a registration you can obtain. Once you hold it, no rule of this programme blocks you on the answers given.',
  blocked: 'At least one rule that every applicant must meet is not met.',
  conditional: 'No rule is plainly broken, but a condition applies or an answer is missing.',
};

export const OUTCOME_WORD: Record<Outcome, string> = {
  met: 'Met', not_met: 'Not met', to_obtain: 'To obtain', conditional: 'Conditional', unknown: 'Needs an answer',
  not_applicable: 'Does not apply', info: 'For information',
};

/**
 * What a verification status means for a line, depending on where its text comes from. A line taken from the
 * research notes was marked verified when the notes were written; this site did not read its source again, and
 * says so instead of "the page was fetched".
 */
export function statusWords(status: VerificationStatus, origin: 'primary' | 'notes' | 'call_document'): string {
  if (status === 'V') {
    if (origin === 'call_document') return 'Verified: the sentence was checked against the Commission’s call document named in the reference, not against the Official Journal.';
    return origin === 'primary'
      ? 'Verified: the text was checked against the Official Journal text of the regulation.'
      : 'Marked verified in the DefenceGate research notes when they were written (7 September 2026); not checked again on this site.';
  }
  if (status === 'S') return 'Seen in search results, not fetched directly.';
  return 'Unverified: a lead to check, not a fact.';
}

/** The sentence a requirement page prints for a rule: what it asks (never the "not met" verdict text). */
export function ruleSentence(texts: Record<string, string>): string {
  return texts.requires ?? texts.info ?? '';
}

export const OBLIGATION_WORD = { mandatory: 'Required', conditional: 'Only in some cases', recommended: 'Recommended' } as const;

export const CATEGORY_WORD: Record<string, string> = {
  identification: 'Identification', registration: 'Registration', quality: 'Quality', export_control: 'Export control',
  security: 'Security clearance', integrity: 'Integrity', admission: 'Eligibility rule', origin: 'Origin rule',
};

const nf = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });

/** "USD 17,000 to 48,000", "free", or "not stated". Money is never converted. */
export function formatRange(m: RMoney | null): string {
  if (!m || m.min === null || m.max === null) return 'Not stated in the sources';
  if (m.basis === 'free') return 'Free';
  const cur = m.currency ?? '';
  return m.min === m.max ? `${cur} ${nf.format(m.min)}` : `${cur} ${nf.format(m.min)} to ${nf.format(m.max)}`;
}

/** Days as the sources speak: "immediate", "3 to 8 months", "4 to 20 days". */
export function formatDays(s: RSpan | null): string {
  if (!s || s.min === null || s.max === null) return 'Not stated in the sources';
  return s.text ?? daysRange(s.min, s.max);
}

export function daysRange(min: number, max: number): string {
  if (max === 0) return 'immediate';
  const unit = (n: number) => (n >= 60 ? `${Math.round(n / 30)} months` : `${n} days`);
  if (min === max) return unit(max);
  return max >= 60 && min >= 60 ? `${Math.round(min / 30)} to ${Math.round(max / 30)} months` : `${min} to ${max} days`;
}

/** The source line under a rule: where the text comes from, in words a visitor can check. */
export function originWords(s: RSource): string {
  if (s.origin === 'call_document') return 'Quoted from the Commission’s call document named in the reference; the Official Journal text does not say it.';
  return s.origin === 'primary'
    ? 'Quoted from the Official Journal text of the regulation.'
    : 'Quoted from the DefenceGate research notes of 7 September 2026; the primary page was not re-read for this line.';
}

export function isoDay(value: string): string {
  return /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : value;
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

/** Compute the verdict: the one call that leaves the browser. Nothing is kept by the server. */
export async function assess(request: AssessRequest, signal?: AbortSignal): Promise<Assessment> {
  const res = await fetch('/api/readiness/assess', {
    method: 'POST', headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(request), signal, cache: 'no-store', credentials: 'omit',
  });
  if (!res.ok) throw new AssessError(res.status, res.status === 429 ? 'Too many requests. Wait a minute and try again.' : 'The check could not be computed. Try again in a moment.');
  return (await res.json()) as Assessment;
}

/**
 * The questions a requirement page answers, built from its own data. The page shows them as text and the
 * structured data repeats the same strings, so the markup never claims more than the page says.
 */
export function faqOf(r: RequirementDetail): { q: string; a: string }[] {
  const out: { q: string; a: string }[] = [];
  if (r.kind === 'document') {
    const named = r.issuers.filter((i) => i.country !== '*');
    const everywhere = r.issuers.filter((i) => i.country === '*');
    const parts = [
      ...everywhere.map((i) => `${i.name} (the same body for every country)`),
      ...named.map((i) => `${countryName(i.country)}: ${i.name}`),
    ];
    out.push({
      q: `Who issues ${r.name}?`,
      a: parts.length > 0 ? `${parts.join('. ')}. The body has not been collected for the countries not listed.` : 'The issuing body has not been collected for any country.',
    });
    out.push({ q: `How much does ${r.name} cost?`, a: r.cost ? `${r.cost.text ?? formatRange(r.cost)}.${r.cost.label ? ` Note: ${r.cost.label}.` : ''}` : 'No cost is stated in the sources used.' });
    out.push({ q: `How long does ${r.name} take?`, a: r.days ? `${formatDays(r.days)}.` : 'No duration is stated in the sources used.' });
  }
  if (r.mandatoryFor) out.push({ q: `Who needs ${r.name}?`, a: r.mandatoryFor });
  return out;
}
