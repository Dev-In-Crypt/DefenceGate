/**
 * Self-check of WP-114 (coverage audit of 24 October 2026): the sitemap index and its files, and the ETag of the machine
 * outputs (calendar files, CSV, sitemaps). Not part of the app and not imported by it. Run from web/:  npm run check
 */
import assert from 'node:assert/strict';
import { matches, withEtag } from './etag';
import { SITEMAP_MAX_URLS, parseSitemapFile, sitemapFiles, sitemapIndex, urlset } from './sitemap';

// The index names the pages, the suppliers and one file per tender id range
assert.deepEqual(sitemapFiles(3), ['pages.xml', 'suppliers.xml', 'tenders-0.xml', 'tenders-1.xml', 'tenders-2.xml']);
assert.deepEqual(sitemapFiles(0), ['pages.xml', 'suppliers.xml', 'tenders-0.xml']);
const index = sitemapIndex([{ url: 'https://x.test/sitemaps/pages.xml' }]);
assert.match(index, /^<\?xml version="1.0" encoding="UTF-8"\?>\n<sitemapindex xmlns="http:\/\/www.sitemaps.org\/schemas\/sitemap\/0.9">/);
assert.match(index, /<sitemap><loc>https:\/\/x.test\/sitemaps\/pages.xml<\/loc><\/sitemap>/);

// A file name is one of three shapes, nothing else
assert.deepEqual(parseSitemapFile('tenders-12.xml'), { kind: 'tenders', page: 12 });
assert.deepEqual(parseSitemapFile('suppliers.xml'), { kind: 'suppliers' });
for (const bad of ['tenders-.xml', 'tenders-1.xml.gz', '../pages.xml', 'tenders-99999.xml', 'pages']) assert.equal(parseSitemapFile(bad), null, bad);

// A file escapes its addresses, dates them in ISO form, and never holds more than 50,000 URLs
const one = urlset([{ url: 'https://x.test/a?b=1&c=<2>', lastModified: '2026-10-24' }, { url: 'https://x.test/b', lastModified: 'not a date' }]);
assert.ok(one.includes('<url><loc>https://x.test/a?b=1&amp;c=&lt;2&gt;</loc><lastmod>2026-10-24T00:00:00.000Z</lastmod></url>'));
assert.ok(one.includes('<url><loc>https://x.test/b</loc></url>'));
const many = urlset(Array.from({ length: SITEMAP_MAX_URLS + 5 }, (_, i) => ({ url: `https://x.test/${i}` })));
assert.equal(many.match(/<url>/g)?.length, SITEMAP_MAX_URLS);

// If-None-Match: a list, weak tags, the wildcard
assert.ok(matches('"a-1"', '"a-1"'));
assert.ok(matches('W/"a-1", "b-2"', '"a-1"'));
assert.ok(matches('*', '"a-1"'));
assert.ok(!matches('"a-2"', '"a-1"'));
assert.ok(!matches(null, '"a-1"'));

async function etags(): Promise<void> {
  const file = () => new Response('BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n', { headers: { 'content-type': 'text/calendar', 'cache-control': 'public, max-age=3600' } });
  const first = await withEtag(new Request('https://x.test/calendar.ics'), file());
  const tag = first.headers.get('etag');
  assert.ok(tag && /^"[0-9a-f]+-[0-9a-f]+"$/.test(tag));
  assert.equal(await first.text(), 'BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n');
  assert.equal(first.headers.get('cache-control'), 'public, max-age=3600');
  // the same file again: 304, no body, the tag and the caching kept
  const again = await withEtag(new Request('https://x.test/calendar.ics', { headers: { 'if-none-match': tag } }), file());
  assert.equal(again.status, 304);
  assert.equal(await again.text(), '');
  assert.equal(again.headers.get('etag'), tag);
  // another body is another tag; an error is passed through untagged
  const other = await withEtag(new Request('https://x.test/calendar.ics', { headers: { 'if-none-match': tag } }), new Response('other'));
  assert.equal(other.status, 200);
  const failed = await withEtag(new Request('https://x.test/calendar.ics'), new Response('down', { status: 502 }));
  assert.equal(failed.status, 502);
  assert.equal(failed.headers.get('etag'), null);
}

etags().then(() => console.log('wp114 checks passed')).catch((e) => { console.error(e); process.exit(1); });
