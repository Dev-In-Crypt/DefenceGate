/**
 * WP-99 (persona round of 23 October 2026, p09): "Subscribe to this search" for a funding search, as /tenders has it (WP-90): the calendar
 * of the search (`/funding.ics` with the list's filters, as webcal and as a file) and an Atom feed of its calls (`/funding.atom`, the same
 * filters). Pure and import-light: lib/wp99.check.ts runs it.
 *
 * The feed lists the calls of the search, the newest first (when we first saw them), so a reader shows a new call that matches as a new
 * entry; each entry's id is the call's own and stays the same. A moved date is in the change feed (/changes.atom), not here.
 */
import { rfc3339, tagId, xmlText } from './atom';
import { toQuery } from './filters';
import { formatDateLabelledUtc } from './format';
import type { Call, CallFilters } from './types';

/** The filters of /funding the calendar file and the feed read (app/(public)/funding.ics/route.ts SEARCH_PARAMS); not the page or the view. */
export const FUNDING_SEARCH_PARAMS = ['q', 'programme', 'regime', 'country', 'status', 'from', 'to', 'min', 'max', 'currency', 'sort', 'cascade', 'ukraine', 'who'] as const;
/** The calls a feed holds at most: the newest first. */
export const FUNDING_FEED_MAX = 100;

export interface FundingSubscription { ics: string | null; webcal: string | null; atom: string }

/** The addresses of a funding search's calendar and feed. A Closed list has no date to come: no calendar (the file refuses it). */
export function fundingSubscription(f: CallFilters, origin: string): FundingSubscription {
  // the page and the order of the list are not filters of a feed
  const q = toQuery({ ...f, page: 1, sort: undefined, pageSize: undefined });
  const ics = (f.status ?? 'open') === 'closed' ? null : `/funding.ics${q}`;
  const host = origin.replace(/^https?:\/\//, '').replace(/\/$/, '');
  return { ics, webcal: ics ? `webcal://${host}${ics}` : null, atom: `/funding.atom${q}` };
}

/** The calls the feed holds: the newest first, at most FUNDING_FEED_MAX. */
export function feedCalls(calls: Call[]): Call[] {
  return [...calls].sort((a, b) => b.firstSeenAt.localeCompare(a.firstSeenAt) || b.id.localeCompare(a.id)).slice(0, FUNDING_FEED_MAX);
}

function summary(c: Call): string {
  const deadline = c.deadline ? `Deadline ${formatDateLabelledUtc(c.deadline)}${c.deadlineIsDate ? ' (the source gives a day and no time)' : ''}.` : 'No deadline stated.';
  return `${c.issuer ?? c.programmeName}, ${c.programmeName}. ${deadline} Source: ${c.source.sourceName}. The original call is authoritative.`;
}

export function buildFundingAtom(calls: Call[], o: { origin: string; query: string; describe: string; total: number; generatedAt: string }): string {
  const held = feedCalls(calls);
  const updated = held.reduce((m, c) => (c.firstSeenAt > m ? c.firstSeenAt : m), '') || o.generatedAt;
  const cut = o.total > held.length ? ` This feed holds the newest ${held.length} of the ${o.total} calls; the page lists them all.` : '';
  return [
    '<?xml version="1.0" encoding="utf-8"?>',
    '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en">',
    `  <id>${xmlText(tagId(o.origin, 'funding', o.query.replace(/^\?/, '') || 'all'))}</id>`,
    `  <title>${xmlText(`DefenceGate funding: ${o.describe}`)}</title>`,
    `  <subtitle>${xmlText(`The funding calls of one search on DefenceGate (${o.describe}), the newest first: a new call that matches is a new entry.${cut}`)}</subtitle>`,
    `  <updated>${rfc3339(updated)}</updated>`,
    `  <link rel="self" type="application/atom+xml" href="${xmlText(`${o.origin}/funding.atom${o.query}`)}"/>`,
    `  <link rel="alternate" type="text/html" href="${xmlText(`${o.origin}/funding${o.query}`)}"/>`,
    '  <author><name>DefenceGate</name></author>',
    ...held.map((c) => [
      '  <entry>',
      `    <id>${xmlText(tagId(o.origin, 'call', c.id))}</id>`,
      `    <title>${xmlText(c.title)}</title>`,
      `    <link rel="alternate" type="text/html" href="${xmlText(`${o.origin}/funding/${c.slug}`)}"/>`,
      `    <published>${rfc3339(c.firstSeenAt)}</published>`,
      `    <updated>${rfc3339(c.firstSeenAt)}</updated>`,
      `    <category term="${xmlText(c.programme)}"/>`,
      `    <summary type="text">${xmlText(summary(c))}</summary>`,
      '  </entry>',
    ].join('\n')),
    '</feed>',
    '',
  ].join('\n');
}
