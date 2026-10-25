/**
 * The regulatory tracker (/regulation, /regulation.atom): types, words and the Atom feed. Pure and import-light:
 * lib/regulation.check.ts runs it on its own. Every entry carries its primary source and a verbatim sentence of it.
 */
import { rfc3339, tagId, xmlText } from './atom';
import { requirementSlug } from './readiness';

export type RegulationStatus = 'proposed' | 'announced' | 'agreed' | 'adopted' | 'in_force' | 'unconfirmed';

export interface RegulationLink { kind: 'requirement' | 'programme' | 'page'; code: string; label: string }

export interface RegulationEntry {
  code: string;
  instrument: string;
  title: string;
  whatChanged: string;
  /** YYYY-MM-DD: the day of the event the entry reports. */
  eventDate: string;
  status: RegulationStatus;
  affected: string;
  source: { url: string; ref: string; quote: string };
  /** YYYY-MM-DD: the day we last read the source. */
  checkedOn: string;
  links: RegulationLink[];
}

export interface RegulationFeed { entries: RegulationEntry[]; lastChecked: string | null; notice: string }

export const STATUS_WORD: Record<RegulationStatus, string> = {
  proposed: 'Proposed', announced: 'Announced', agreed: 'Agreed', adopted: 'Adopted', in_force: 'In force', unconfirmed: 'Unconfirmed',
};

export const STATUS_MEANING: Record<RegulationStatus, string> = {
  proposed: 'A proposal exists; the institutions have not adopted it.',
  announced: 'The Commission has said it will propose; no proposal is published.',
  agreed: 'The negotiators agreed a text; formal adoption is still to come.',
  adopted: 'The institutions have adopted the act; it is not yet in force, or the source does not say it is.',
  in_force: 'The act is published and in force.',
  unconfirmed: 'No primary text we could read settles this point; the entry says which.',
};

/** Newest event first (U12: "Unconfirmed" came first, then 9 October, 15 June, 30 December 2025), ties by code. */
export function newestFirst(entries: RegulationEntry[]): RegulationEntry[] {
  return [...entries].sort((a, b) => (a.eventDate < b.eventDate ? 1 : a.eventDate > b.eventDate ? -1 : a.code.localeCompare(b.code)));
}

/**
 * WP-131 (round 7: "last checked 18 Oct 2026" read as the whole tracker's date, the newest of the entries'): when the entries' sources were
 * last checked, from their own dates. `say` formats a YYYY-MM-DD day. null for no entry.
 */
export function checkedLine(entries: readonly { checkedOn: string }[], say: (day: string) => string): string | null {
  const days = entries.map((e) => e.checkedOn).filter(Boolean).sort();
  if (days.length === 0) return null;
  const [first, last] = [days[0], days[days.length - 1]];
  return first === last
    ? `Every entry’s source was last checked on ${say(first)}, none since.`
    : `The entries’ sources were last checked between ${say(first)} and ${say(last)}; each entry gives its own date.`;
}

/** The address of one entry: the page and the anchor of its code. */
export const entryUrl = (origin: string, code: string): string => `${origin}/regulation#${code}`;

/** A line to copy into a note: who, what, the event date, the day we last read the source, the address and the primary source. */
export function citation(e: RegulationEntry, origin: string): string {
  return `DefenceGate regulatory tracker, “${e.title}” (${STATUS_WORD[e.status].toLowerCase()}, event of ${e.eventDate}; source last checked ${e.checkedOn}). ${entryUrl(origin, e.code)}. Primary source: ${e.source.ref}, ${e.source.url}.`;
}

/** Where a link of an entry leads on this site. A requirement is the readiness catalogue's page; a page is a path. */
export function linkHref(l: RegulationLink): string {
  if (l.kind === 'requirement') return `/requirements/${requirementSlug(l.code)}`;
  if (l.kind === 'programme') return '/readiness';
  return l.code.startsWith('/') ? l.code : `/${l.code}`;
}

export interface RegulationAtomOptions { origin: string; generatedAt: string }

/** The tracker as Atom 1.0: one entry per tracker entry; `updated` is the day we last checked it. */
export function buildRegulationAtom(feed: RegulationFeed, o: RegulationAtomOptions): string {
  const updated = feed.entries.reduce((m, e) => (e.checkedOn > m ? e.checkedOn : m), '') || o.generatedAt;
  const entries = newestFirst(feed.entries).map((e) => [
    '  <entry>',
    `    <id>${xmlText(tagId(o.origin, 'regulation', e.code))}</id>`,
    `    <title>${xmlText(`${e.title} (${STATUS_WORD[e.status]})`)}</title>`,
    `    <link rel="alternate" type="text/html" href="${xmlText(entryUrl(o.origin, e.code))}"/>`,
    `    <link rel="related" type="text/html" href="${xmlText(e.source.url)}" title="Primary source"/>`,
    `    <updated>${rfc3339(e.checkedOn)}</updated>`,
    `    <published>${rfc3339(e.eventDate)}</published>`,
    `    <category term="${xmlText(e.status)}"/>`,
    `    <summary type="text">${xmlText(`${e.whatChanged} Source: ${e.source.ref}. “${e.source.quote}” Last checked ${e.checkedOn}.`)}</summary>`,
    '  </entry>',
  ].join('\n'));
  return [
    '<?xml version="1.0" encoding="utf-8"?>',
    '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en">',
    `  <id>${xmlText(tagId(o.origin, 'regulation'))}</id>`,
    '  <title>DefenceGate: regulatory tracker</title>',
    '  <subtitle>Changes in the rules that matter to a defence supplier, each with its primary source</subtitle>',
    `  <updated>${rfc3339(updated)}</updated>`,
    `  <link rel="self" type="application/atom+xml" href="${xmlText(`${o.origin}/regulation.atom`)}"/>`,
    `  <link rel="alternate" type="text/html" href="${xmlText(`${o.origin}/regulation`)}"/>`,
    '  <author><name>DefenceGate</name></author>',
    ...entries,
    '</feed>',
    '',
  ].join('\n');
}
