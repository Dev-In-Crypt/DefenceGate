import type { MetadataRoute } from 'next';
import { getAllBuyerSlugs, getAllCallSlugs, getAllTenderSlugs, getDigestWeeks, getHealth, isBuyerSlug, isCallSlug, isTenderSlug } from '@/lib/api';
import { requirementSlug } from '@/lib/readiness';
import { getNetworkSlugs } from '@/lib/networks-api';
import { getRequirements } from '@/lib/readiness-api';
import { absoluteUrl } from '@/lib/seo';

export const revalidate = 3600;

/**
 * Only routes that exist and are indexable. Filtered /funding, /tenders and /buyers views are noindex and not listed.
 * /pack, /pricing, /imprint, /terms and /privacy carry `robots: noindex` until they say something worth finding (the pack is not open,
 * pricing is not announced, the imprint waits for the provider's details, and the terms and privacy notice stay unindexed until it is filled in): a noindex page does not belong in a
 * sitemap. Add them here when their noindex is removed. /alerts is indexable and listed. /changes is listed without its
 * filters (a filtered or paged view is noindex); /changes.atom is a feed, not a page, and is linked from the page's head.
 */
const STATIC_PATHS = ['/', '/funding', '/tenders', '/buyers', '/suppliers', '/calendar', '/cpv', '/glossary', '/data', '/market', '/methodology', '/about', '/alerts', '/changes', '/digest', '/regulation', '/data/sovereignty', '/organisations', '/networks/ukraine-partners', '/networks/consortium-gaps'];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // Funding slugs are required (as before). The tender and buyer lists degrade to empty if their endpoints are
  // not deployed yet, so a frontend built before the backend still produces a sitemap.
  const requirements = await getRequirements().then((r) => r.items).catch(() => []);
  // The organisations with the most projects and the EDF projects (WP-28); the 80,000 CORDIS projects are reachable but not listed.
  const [orgSlugs, projectSlugs] = await getNetworkSlugs().catch(() => [[], []]);
  const [calls, tenders, buyers, health, weeks] = await Promise.all([
    getAllCallSlugs(),
    getAllTenderSlugs().catch(() => []),
    getAllBuyerSlugs().catch(() => []),
    getHealth(),
    getDigestWeeks().catch(() => []),
  ]);
  const lastModified = new Date(health.generatedAt);
  return [
    ...STATIC_PATHS.map((p) => ({ url: absoluteUrl(p), lastModified })),
    // An issue never changes once its week has ended: its last change is the end of the week.
    ...weeks.map((w) => ({ url: absoluteUrl(`/digest/${w.week}`), lastModified: new Date(w.weekTo) })),
    // The readiness check and the requirements catalogue (WP-29). /readiness/results and /readiness/roadmap are private to the visitor and noindex.
    ...['/readiness', '/requirements'].map((p) => ({ url: absoluteUrl(p), lastModified })),
    ...requirements.map((r) => ({ url: absoluteUrl(`/requirements/${requirementSlug(r.code)}`), lastModified: new Date(r.lastReviewed) })),
    ...calls.filter((c) => isCallSlug(c.slug)).map((c) => ({ url: absoluteUrl(`/funding/${c.slug}`), lastModified: new Date(c.updatedAt) })),
    ...tenders.filter((t) => isTenderSlug(t.slug)).map((t) => ({ url: absoluteUrl(`/tenders/${t.slug}`), lastModified: new Date(t.updatedAt) })),
    ...orgSlugs.filter((o) => isBuyerSlug(o.slug)).map((o) => ({ url: absoluteUrl(`/organisations/${o.slug}`), lastModified: new Date(o.updatedAt) })),
    ...projectSlugs.filter((x) => isBuyerSlug(x.slug)).map((x) => ({ url: absoluteUrl(`/projects/${x.slug}`), lastModified: new Date(x.updatedAt) })),
    ...buyers.filter((b) => isBuyerSlug(b.slug)).map((b) => ({ url: absoluteUrl(`/buyers/${b.slug}`), lastModified: new Date(b.updatedAt) })),
  ];
}
