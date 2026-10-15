/**
 * The "what changed" feed as Atom 1.0 (RFC 4287). Pure and import-light: lib/atom.check.ts runs it on its own.
 *
 * Each entry is one notice on one UTC day (`Change.id`), so its `id` is stable for good: a reader never shows a
 * change twice, and `updated` is when we last observed that day's change. Titles, buyers, countries, dates and
 * statuses only, as everywhere else: no contact data and nothing about what is being bought beyond its title.
 */
import type { Change } from './types';

export interface AtomOptions {
  /** Site origin, no trailing slash: https://defencegatehub.com */
  origin: string;
  /** Path of the feed itself, with its query when it has one: /changes.atom?country=PL */
  selfPath: string;
  /** Path of the HTML page the feed mirrors: /changes?country=PL */
  pagePath: string;
  title: string;
  subtitle: string;
  /** Used for `updated` when there is no entry. */
  generatedAt: string;
}

/** XML 1.0 forbids most control characters; a stray one in a title would make the whole feed unreadable. */
// eslint-disable-next-line no-control-regex
const ILLEGAL_XML = /[\u0000-\u0008\u000B\u000C\u000E-\u001F￾￿]/g;

export function xmlText(value: string): string {
  return value
    .replace(ILLEGAL_XML, '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** RFC 3339 in UTC, to the second: the one date form every reader parses. */
export function rfc3339(value: string): string {
  const t = new Date(value);
  return Number.isNaN(t.getTime()) ? '1970-01-01T00:00:00Z' : `${t.toISOString().slice(0, 19)}Z`;
}

/** A tag URI (RFC 4151) that stays the same whatever the site's URL becomes. */
export function tagId(origin: string, ...parts: string[]): string {
  let host = 'defencegatehub.com';
  try { host = new URL(origin).hostname; } catch { /* the default stands */ }
  return `tag:${host},2026:${parts.join(':')}`;
}

function summary(c: Change): string {
  const t = c.tender;
  const where = t.country ? `${t.buyerName} (${t.country})` : t.buyerName;
  if (c.kind === 'new') return `New notice from ${where}.`;
  const lines = c.changes.map((l) => `${l.label}: ${l.before ?? 'not stated'} to ${l.after ?? 'not stated'}`);
  return `Amended notice from ${where}. ${lines.join('. ')}.`;
}

export function entryTitle(c: Change): string {
  return `${c.kind === 'new' ? 'New' : 'Amended'}: ${c.tender.title}`;
}

export function buildAtom(changes: Change[], o: AtomOptions): string {
  const updated = changes.reduce((m, c) => (c.detectedAt > m ? c.detectedAt : m), '') || o.generatedAt;
  const self = `${o.origin}${o.selfPath}`;
  const entries = changes.map((c) => {
    const link = `${o.origin}/tenders/${c.tender.slug}`;
    return [
      '  <entry>',
      `    <id>${xmlText(tagId(o.origin, 'change', c.id))}</id>`,
      `    <title>${xmlText(entryTitle(c))}</title>`,
      `    <link rel="alternate" type="text/html" href="${xmlText(link)}"/>`,
      `    <updated>${rfc3339(c.detectedAt)}</updated>`,
      `    <category term="${c.kind}"/>`,
      `    <summary type="text">${xmlText(summary(c))}</summary>`,
      '  </entry>',
    ].join('\n');
  });
  return [
    '<?xml version="1.0" encoding="utf-8"?>',
    '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en">',
    `  <id>${xmlText(tagId(o.origin, 'changes', o.selfPath.replace(/^\/changes\.atom\??/, '') || 'all'))}</id>`,
    `  <title>${xmlText(o.title)}</title>`,
    `  <subtitle>${xmlText(o.subtitle)}</subtitle>`,
    `  <updated>${rfc3339(updated)}</updated>`,
    `  <link rel="self" type="application/atom+xml" href="${xmlText(self)}"/>`,
    `  <link rel="alternate" type="text/html" href="${xmlText(`${o.origin}${o.pagePath}`)}"/>`,
    '  <author><name>DefenceGate</name></author>',
    ...entries,
    '</feed>',
    '',
  ].join('\n');
}

/** A weak validator: the same entries and the same dates give the same tag. */
export function etagOf(body: string): string {
  // FNV-1a, 32 bit: not a security measure, only a change detector.
  let h = 0x811c9dc5;
  for (let i = 0; i < body.length; i += 1) {
    h ^= body.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return `"${h.toString(16)}-${body.length.toString(16)}"`;
}
