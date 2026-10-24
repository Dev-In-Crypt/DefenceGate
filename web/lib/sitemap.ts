/**
 * WP-114: the sitemap as files of their own (sitemaps.org protocol). /sitemap.xml is an index of them: the pages and the
 * smaller lists (/sitemaps/pages.xml), the suppliers that have a page (/sitemaps/suppliers.xml) and every core tender, one
 * file per id range of the API (/sitemaps/tenders-<n>.xml, GET /v1/tenders/sitemap). One file was 5,000 tenders of
 * ~315,000 and no supplier at all (coverage audit of 24 October 2026); a sitemap file holds at most 50,000 URLs.
 */
import { xmlText } from './atom';

export const SITEMAP_MAX_URLS = 50_000;

export interface SitemapEntry { url: string; lastModified?: string | Date }

const iso = (d: string | Date | undefined): string | null => {
  if (d === undefined) return null;
  const t = new Date(d);
  return Number.isNaN(t.getTime()) ? null : t.toISOString();
};

const XML_HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n';
const NS = 'http://www.sitemaps.org/schemas/sitemap/0.9';

function item(tag: 'url' | 'sitemap', e: SitemapEntry): string {
  const when = iso(e.lastModified);
  return `<${tag}><loc>${xmlText(e.url)}</loc>${when ? `<lastmod>${when}</lastmod>` : ''}</${tag}>`;
}

/** A sitemap file; past SITEMAP_MAX_URLS the rest is cut (a caller pages instead). */
export function urlset(entries: SitemapEntry[]): string {
  return `${XML_HEAD}<urlset xmlns="${NS}">\n${entries.slice(0, SITEMAP_MAX_URLS).map((e) => item('url', e)).join('\n')}\n</urlset>\n`;
}

/** The index of sitemap files. */
export function sitemapIndex(files: SitemapEntry[]): string {
  return `${XML_HEAD}<sitemapindex xmlns="${NS}">\n${files.map((e) => item('sitemap', e)).join('\n')}\n</sitemapindex>\n`;
}

/** The file names under /sitemaps/: `pages.xml`, `suppliers.xml`, `tenders-<n>.xml`. */
export function sitemapFiles(tenderPages: number): string[] {
  return ['pages.xml', 'suppliers.xml', ...Array.from({ length: Math.max(1, tenderPages) }, (_, i) => `tenders-${i}.xml`)];
}

/** What a file name under /sitemaps/ names, or null. */
export function parseSitemapFile(name: string): { kind: 'pages' } | { kind: 'suppliers' } | { kind: 'tenders'; page: number } | null {
  if (name === 'pages.xml') return { kind: 'pages' };
  if (name === 'suppliers.xml') return { kind: 'suppliers' };
  const m = /^tenders-(\d{1,4})\.xml$/.exec(name);
  return m ? { kind: 'tenders', page: Number(m[1]) } : null;
}

export const XML_HEADERS = { 'content-type': 'application/xml; charset=utf-8', 'cache-control': 'public, max-age=3600' };
