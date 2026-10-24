import { getAllBuyerSlugs, getAllCallSlugs, getAllSupplierSlugs, getDigestWeeks, getHealth, getTenderSitemapPage, isBuyerSlug, isCallSlug, isSupplierSlug, isTenderSlug } from '@/lib/api';
import { withEtag } from '@/lib/etag';
import { getNetworkSlugs } from '@/lib/networks-api';
import { requirementSlug } from '@/lib/readiness';
import { getRequirements } from '@/lib/readiness-api';
import { absoluteUrl } from '@/lib/seo';
import { type SitemapEntry, XML_HEADERS, parseSitemapFile, urlset } from '@/lib/sitemap';

/**
 * The files of the sitemap index (/sitemap.xml, WP-114). Only routes that exist and are indexable. Filtered /funding,
 * /tenders and /buyers views are noindex and not listed. /pack, /pricing, /imprint, /terms and /privacy carry
 * `robots: noindex` until they say something worth finding (the pack is not open, pricing is not announced, the imprint
 * waits for the provider's details, and the terms and privacy notice stay unindexed until it is filled in): a noindex page
 * does not belong in a sitemap. Add them here when their noindex is removed. /alerts is indexable and listed. /changes is
 * listed without its filters (a filtered or paged view is noindex); /changes.atom is a feed, not a page, and is linked from
 * the page's head. Tender pages: the core scope only (a supply notice's page is noindex), every one of them, by id range.
 */
const STATIC_PATHS = ['/', '/funding', '/tenders', '/buyers', '/suppliers', '/calendar', '/cpv', '/glossary', '/data', '/market', '/methodology', '/about', '/alerts', '/changes', '/digest', '/regulation', '/data/sovereignty', '/organisations', '/networks/ukraine-partners', '/networks/consortium-gaps'];

async function pages(): Promise<SitemapEntry[]> {
  // Funding slugs are required (as before). The other lists degrade to empty if their endpoints are not deployed yet.
  const requirements = await getRequirements().then((r) => r.items).catch(() => []);
  // The organisations with the most projects and the EDF projects (WP-28); the 80,000 CORDIS projects are reachable but not listed.
  const [orgSlugs, projectSlugs] = await getNetworkSlugs().catch(() => [[], []]);
  const [calls, buyers, health, weeks] = await Promise.all([
    getAllCallSlugs(), getAllBuyerSlugs().catch(() => []), getHealth(), getDigestWeeks().catch(() => []),
  ]);
  const lastModified = new Date(health.generatedAt);
  return [
    ...STATIC_PATHS.map((p) => ({ url: absoluteUrl(p), lastModified })),
    // An issue never changes once its week has ended: its last change is the end of the week.
    ...weeks.map((w) => ({ url: absoluteUrl(`/digest/${w.week}`), lastModified: new Date(w.weekTo) })),
    // The readiness check and the requirements catalogue (WP-29). /readiness/results and /readiness/roadmap are private to the visitor and noindex.
    // WP-86: /check is the entry to them; /companies is a redirect to /suppliers and /search a noindex page, so neither is listed.
    ...['/check', '/readiness', '/readiness/supplier', '/readiness/spain-automotive', '/requirements'].map((p) => ({ url: absoluteUrl(p), lastModified })),
    ...requirements.map((r) => ({ url: absoluteUrl(`/requirements/${requirementSlug(r.code)}`), lastModified: new Date(r.lastReviewed) })),
    ...calls.filter((c) => isCallSlug(c.slug)).map((c) => ({ url: absoluteUrl(`/funding/${c.slug}`), lastModified: new Date(c.updatedAt) })),
    ...orgSlugs.filter((o) => isBuyerSlug(o.slug)).map((o) => ({ url: absoluteUrl(`/organisations/${o.slug}`), lastModified: new Date(o.updatedAt) })),
    ...projectSlugs.filter((x) => isBuyerSlug(x.slug)).map((x) => ({ url: absoluteUrl(`/projects/${x.slug}`), lastModified: new Date(x.updatedAt) })),
    ...buyers.filter((b) => isBuyerSlug(b.slug)).map((b) => ({ url: absoluteUrl(`/buyers/${b.slug}`), lastModified: new Date(b.updatedAt) })),
  ];
}

export async function GET(request: Request, { params }: { params: Promise<{ name: string }> }): Promise<Response> {
  const file = parseSitemapFile((await params).name);
  if (!file) return new Response('There is no such sitemap.', { status: 404, headers: { 'content-type': 'text/plain; charset=utf-8' } });
  try {
    let entries: SitemapEntry[];
    if (file.kind === 'pages') {
      entries = await pages();
    } else if (file.kind === 'suppliers') {
      entries = (await getAllSupplierSlugs()).filter((s) => isSupplierSlug(s.slug))
        .map((s) => ({ url: absoluteUrl(`/suppliers/${s.slug}`), lastModified: s.updatedAt }));
    } else {
      const got = await getTenderSitemapPage(file.page);
      if (file.page >= got.pages) return new Response('There is no such sitemap.', { status: 404, headers: { 'content-type': 'text/plain; charset=utf-8' } });
      entries = got.items.filter((t) => isTenderSlug(t.slug)).map((t) => ({ url: absoluteUrl(`/tenders/${t.slug}`), lastModified: t.updatedAt }));
    }
    return withEtag(request, new Response(urlset(entries), { headers: XML_HEADERS }));
  } catch (err) {
    console.error('sitemap failed:', err instanceof Error ? err.message : String(err));
    return new Response('The sitemap could not be built right now.', { status: 503, headers: { 'content-type': 'text/plain; charset=utf-8', 'retry-after': '600' } });
  }
}
