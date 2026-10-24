/**
 * WP-91, the funding path of the UX audit of 22 October 2026 (section 6: a Polish drone-software start-up). Pure: no React, no DOM,
 * no network (lib/wp91.check.ts runs it in node).
 *
 *   emptyLine     an empty "Open" list says what is coming and what closed, never only "No calls match"
 *   applySummary  "Can I apply?" for one country on the first screen of a call, from the engine's outcomes (`rulesApply.byCountry`)
 *                 and the call document's facts: a "no" only where a rule is not met, a "yes" only where the establishment rule is met
 *                 and nothing else open is known; everything else "check", with the rule named
 *   whatItFunds   the commercial subject in plain words: the topic keywords the source states, never a technical specification
 */
import { check, consortiumCondition, sizeRule, type EligibilityFacts } from './eligibility-check';
import { formatDateUtc } from './format';
import { fold, parseQuery } from './text-search';
import { countryName } from './taxonomy';
import type { Call, CallFilters, RuleOutcome, RulesApply } from './types';

export type Verdict = 'yes' | 'check' | 'no';

const EU27 = new Set('AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE'.split(' '));
const EEA_EFTA = new Set(['IS', 'LI', 'NO']);

/** The group of the rules a country is in (backend/dgate/rules_apply.py SUMMARY_GROUPS). */
export function countryGroup(country: string): 'EU' | 'EEA_EFTA' | 'UA' | 'OTHER' {
  if (EU27.has(country)) return 'EU';
  if (EEA_EFTA.has(country)) return 'EEA_EFTA';
  return country === 'UA' ? 'UA' : 'OTHER';
}

const named = (country: string) => (country === 'XX' || !country ? 'your country' : countryName(country));

// ---------------------------------------------------------------- 1. an empty list is not a dead end

/**
 * The sentence above the forthcoming and recently closed calls of an empty open list: "No open calls in Poland now; next expected:
 * ... opens 3 Nov 2026." `upcoming` and `closed` are the same filters with the status changed, soonest and newest first.
 */
export function emptyLine(f: CallFilters, upcoming: Call[], closed: Call[]): string {
  const where = f.country?.length === 1 ? ` in ${countryName(f.country[0])}` : f.country?.length ? ` in ${f.country.map(countryName).join(', ')}` : '';
  const head = `No ${f.status === 'closing-soon' ? 'calls closing in the next 30 days' : 'open calls'}${where}${f.country?.length ? '' : ' for this search'} now`;
  const next = upcoming[0];
  if (next) {
    const when = next.openingDate ? `opens ${formatDateUtc(next.openingDate)}` : next.deadline ? `planned deadline ${formatDateUtc(next.deadline)}` : 'date not stated';
    return `${head}; next expected: “${next.title}”, ${when}.`;
  }
  const last = closed[0];
  if (last) return `${head}, and none is announced; the latest that closed is “${last.title}”${last.deadline ? `, on ${formatDateUtc(last.deadline)}` : ''}.`;
  return `${head}, none is announced and none has closed.`;
}

// ---------------------------------------------------------------- 2. "Can I apply?" on the first screen

export interface SummaryLine { key: string; verdict: Verdict | 'info'; text: string }
/** `unknown` (WP-93, finding 6): no rule of the call or its programme is held, so nothing is said either way. */
export interface Summary { verdict: Verdict | 'unknown'; lines: SummaryLine[] }

const lowerFirst = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);
const worst = (a: Verdict, b: Verdict): Verdict => (a === 'no' || b === 'no' ? 'no' : a === 'check' || b === 'check' ? 'check' : 'yes');

/**
 * What a company of `country` can do with this call, in two or three lines. `kind` is the applicant kind of the saved profile (''
 * when not answered): only a public body is not told "Companies cannot apply". Null without a country.
 */
export function applySummary(call: Pick<Call, 'rulesApply' | 'documentEligibility'> & Partial<Pick<Call, 'programme' | 'topicId'>>, country: string, kind = ''): Summary | null {
  if (!country) return null;
  const name = named(country);
  const lines: SummaryLine[] = [];
  const ra: RulesApply | null | undefined = call.rulesApply;
  const facts = (call.documentEligibility?.facts ?? {}) as EligibilityFacts;

  const companyNo = ra?.forCompany?.find((r) => r.outcome === 'not_met');
  if (companyNo) {
    const publicBody = kind !== '' && kind !== 'company_or_research';
    lines.push(publicBody
      ? { key: 'who', verdict: 'check', text: `${companyNo.title}. Check that your organisation is one of them.` }
      : { key: 'who', verdict: 'no', text: `Companies cannot apply to this call. ${companyNo.title}.` });
  }

  const rows: RuleOutcome[] | undefined = ra?.byCountry?.[countryGroup(country)];
  if (rows && rows.length > 0) {
    const no = rows.find((r) => r.outcome === 'not_met');
    const partner = rows.find((r) => r.asks.includes('ua_partner'));
    const conditional = rows.find((r) => r.outcome === 'conditional');
    const established = rows.find((r) => r.rule.endsWith('-ESTABLISH'));
    if (no) lines.push({ key: 'country', verdict: 'no', text: `From ${name}: you cannot apply. ${no.title} (${no.reason})` });
    else if (partner) lines.push({ key: 'country', verdict: 'check', text: `From ${name}: only together with a partner established in Ukraine, with its executive management there (${lowerFirst(partner.title)}).` });
    else if (conditional) lines.push({ key: 'country', verdict: 'check', text: `From ${name}: only on a condition. ${conditional.reason}` });
    else if (established?.outcome === 'met') lines.push({ key: 'country', verdict: 'yes', text: `From ${name}: your country is eligible (${lowerFirst(established.title)}).` });
    else lines.push({ key: 'country', verdict: 'check', text: `From ${name}: check the call’s rules on where applicants must be established.` });
    // Shown to a Ukrainian company only: the other groups never carry the rule (`applies_when` country UA).
    if (rows.some((r) => r.asks.includes('ua_non_government_controlled_area'))) {
      lines.push({ key: 'territory', verdict: 'check', text: 'Not if your company is established in an area of Ukraine that the Ukrainian government does not control.' });
    }
    const also = rows.filter((r) => r.outcome === 'unknown' && !r.asks.includes('ua_partner') && !r.asks.includes('ua_non_government_controlled_area'));
    if (!no && also.length > 0) lines.push({ key: 'also', verdict: 'info', text: `Also required: ${also.map((r) => lowerFirst(r.title)).join('; ')}.` });
  } else if (facts.eligible_countries) {
    const ctx = call.programme ? { programme: call.programme, topic: call.topicId ?? '' } : undefined;
    const line = check(facts, { country, orgType: '', hasPartners: '', controlledAbroad: '' }, ctx).lines.find((l) => l.key === 'country');
    if (line) lines.push({ key: 'country', verdict: line.verdict, text: `From ${name}: ${lowerFirst(line.reason)}` });
  } else if (Object.keys(facts).length === 0) {
    // WP-93 (finding 6): nothing is held, so nothing is "possible": the call's own text decides (RAPID, the Cyber Defense Factory)
    return { verdict: 'unknown', lines: [{ key: 'country', verdict: 'info', text: 'No rules of this programme are encoded here and none were read from its documents: read who may apply in the official call text.' }] };
  } else {
    lines.push({ key: 'country', verdict: 'check', text: 'Where applicants must be established was not read from this call: check its own text. The rules that were read are below.' });
  }

  // The consortium as the call document states it (never a bare "not required" when a single applicant has a condition).
  if (facts.consortium_required?.value === true) {
    const n = facts.min_entities?.value;
    const k = facts.min_countries?.value;
    lines.push({ key: 'consortium', verdict: 'info', text: `A consortium is required${typeof n === 'number' ? `: at least ${n} legal entities` : ''}${typeof k === 'number' ? ` from at least ${k} countries` : ''}.` });
  } else if (facts.consortium_required?.value === false) {
    const c = consortiumCondition(facts);
    lines.push({ key: 'consortium', verdict: 'info', text: c ? `No consortium for every applicant: ${lowerFirst(c)}` : 'A single applicant may apply, as the call document states it.' });
  }
  // WP-102 (131): the size limit and the investor pre-commitment are in the short block too, not only further down the page
  const size = sizeRule(facts);
  if (size) lines.push({ key: 'size', verdict: 'info', text: `Only for ${size.words}, with the staff of linked enterprises counted${size.midcap ? `; a small mid-cap only on a condition: ${size.midcap}` : ''}.` });
  if (facts.investor_precommitment?.value === true) {
    lines.push({ key: 'investor', verdict: 'check', text: 'A pre-commitment of a single qualified investor for at least 20 % of the funding round you aim to raise is required.' });
  }
  const verdict = lines.reduce<Verdict>((v, l) => (l.verdict === 'info' ? v : worst(v, l.verdict)), 'yes');
  return { verdict, lines };
}

export const SUMMARY_WORD: Record<Verdict | 'unknown', string> = {
  yes: 'Nothing in the rules we hold stops you so far',
  check: 'Possible, with a condition to check',
  no: 'The rules we hold say you cannot apply',
  unknown: 'Rules not read: check the call document',
};

/**
 * WP-109 (p05, 191): the portal's topic code and the one the call document writes can differ in the last part (…-12-NATCH on the portal,
 * …-12-NCH in the document). The document's spelling, when its sentences name the same topic with another last part; else null.
 */
export function otherTopicCode(topic: string, text: string): string | null {
  const parts = topic.toUpperCase().split('-');
  if (parts.length < 4) return null;
  const base = parts.slice(0, -1).join('-');
  const found = text.toUpperCase().match(new RegExp(`${base.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}-([A-Z0-9]+)\\b`));
  return found && found[1] !== parts[parts.length - 1] ? `${base}-${found[1]}` : null;
}

// ---------------------------------------------------------------- "What it funds"

/** The commercial subject of a call in plain words: its title and the source's topic keywords. No description is stored. */
export function whatItFunds(call: Pick<Call, 'title' | 'scope' | 'actionType'>): string {
  const kw = call.scope.filter((s) => s.trim() !== '').slice(0, 8);
  return kw.length > 0
    ? `${call.title}. The source’s keywords for this topic: ${kw.join(', ')}.`
    : `${call.title}. The source gives no topic keywords for it.`;
}

// ---------------------------------------------------------------- 7. "Fits my profile" by the visitor's own topics

/** The visitor's topic words (stored in the browser only): folded, distinct, at most 8, of 2 to 40 characters. */
export function topicWords(text: string): string[] {
  return [...new Set(text.split(/[,;\n]+/).map((w) => fold(w)).filter((w) => w.length >= 2 && w.length <= 40))].slice(0, 8);
}

/** How many of the visitor's topics a call's text holds, matched as the search matches (synonyms included): the order of "Fits my profile". */
export function topicScore(topics: string[], text: string): number {
  return topics.filter((t) => parseQuery(t)?.matches(text) ?? false).length;
}
