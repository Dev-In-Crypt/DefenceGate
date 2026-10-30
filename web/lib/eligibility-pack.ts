/**
 * WP-156: the eligibility check's results pack (Pro and up, `eligibility_export`). The API gives every open call with the facts the list
 * badges read (GET /v1/account/eligibility/calls, the same answer for every account); the browser compares them with the saved profile by
 * the one verdict of a call (lib/fit.ts `callFit`, the badge's and the call page's), keeps the calls the profile fits, and prints them or
 * writes them as CSV. The profile never leaves the browser. Pure: no DOM, no network (lib/eligibility-pack.check.ts runs it).
 */
import type { EligibilityFact, Line, Verdict } from './eligibility-check';
import { callFit, fitLabel, fitsProfile, shownFit, verdictLines, type CallFacts, type Fit, type FitResult } from './fit';
import type { Profile } from './profile';
import type { Assessment } from './readiness-types';
import { isoUtc, type Cell } from './csv';

/** One call's facts as /v1/fit/facts serves them (backend partners.facts_of). */
export interface PackFit {
  state: 'read' | 'not_read' | 'no_source';
  programme?: string;
  topic?: string;
  ukraineNoFunding?: string | null;
  facts?: Record<string, { value: unknown; note?: string | null; quote?: string | null; scope?: string }>;
}
export interface PackCall {
  id: string; slug: string; title: string; programme: string; programmeName: string | null; topicId: string | null;
  deadline: string | null; deadlineIsDate: boolean; rolling: boolean; sourceUrl: string | null; sourceName: string | null;
  fit: PackFit | null;
}
export interface PackAnswer { items: PackCall[]; total: number; cap: number; asOf: string }

/** The facts in the shape the verdict reads, as lib/fit-store.ts turns the badge's answer into it. */
export function callFactsOf(f: PackFit | null): CallFacts | null {
  if (!f) return null;
  return {
    state: f.state, programme: f.programme ?? '', topic: f.topic ?? '', ukraineNoFunding: f.ukraineNoFunding ?? null,
    facts: Object.fromEntries(Object.entries(f.facts ?? {}).map(([k, v]) => [k, {
      value: v.value, note: v.note ?? null, quote: v.quote ?? '', confidence: 1, scope: v.scope as EligibilityFact['scope'],
    }])),
  };
}

export interface PackRow { call: PackCall; result: FitResult; fit: Fit; word: string; lines: Line[] }
export interface Pack { rows: PackRow[]; counts: Record<Fit, number> }

/** The open calls the profile fits (eligible, or nothing known blocks it), in the API's order (soonest deadline first), and how many of each. */
export function buildPack(calls: PackCall[], profile: Profile, assessment: Pick<Assessment, 'assessments' | 'roadmap'> | null): Pack {
  const counts: Record<Fit, number> = { yes: 0, check: 0, no: 0, unknown: 0 };
  const rows: PackRow[] = [];
  for (const call of calls) {
    const result = callFit(callFactsOf(call.fit), profile, assessment);
    const fit = shownFit(result);
    counts[fit] += 1;
    if (fitsProfile(result.fit)) rows.push({ call, result, fit, word: fitLabel(result).word, lines: verdictLines(result) });
  }
  return { rows, counts };
}

export const LINE_WORD: Record<Verdict, string> = { yes: 'Allowed', check: 'Check', no: 'Not allowed' };
export const PACK_CSV_HEADER = ['call', 'programme', 'topic', 'deadline', 'verdict', 'rule', 'outcome', 'reason', 'quote', 'call_page', 'source_page'];

/** One row per line of a call's verdict (a call without lines: one row), so a spreadsheet can filter by rule or outcome. `base`: the site's address. */
export function packCsvRows(rows: PackRow[], base: string): Cell[][] {
  return rows.flatMap(({ call, word, lines }) => {
    const head: Cell[] = [call.title, call.programmeName ?? call.programme, call.topicId, `${isoUtc(call.deadline, call.deadlineIsDate)}${call.rolling ? ' (rolling, a cut-off)' : ''}`, word];
    const tail: Cell[] = [`${base}/funding/${call.slug}`, call.sourceUrl];
    return lines.length === 0
      ? [[...head, '', '', '', '', ...tail]]
      : lines.map((l) => [...head, l.label, LINE_WORD[l.verdict], l.reason, l.quote ?? '', ...tail]);
  });
}
