import type { MetadataRoute } from 'next';
import { getAllBuyerSlugs, getAllCallSlugs, getAllTenderSlugs, getHealth, isBuyerSlug, isCallSlug, isTenderSlug } from '@/lib/api';
import { absoluteUrl } from '@/lib/seo';

export const revalidate = 3600;

/**
 * Only routes that exist and are indexable. Filtered /funding, /tenders and /buyers views are noindex and not listed.
 * /pack, /pricing, /imprint, /terms and /privacy carry `robots: noindex` until they say something worth finding (the pack is not open,
 * pricing is not announced, the imprint waits for the provider's details, and the terms and privacy notice stay unindexed until it is filled in): a noindex page does not belong in a
 * sitemap. Add them here when their noindex is removed. /alerts is indexable and listed.
 */
const STATIC_PATHS = ['/', '/funding', '/tenders', '/buyers', '/calendar', '/cpv', '/glossary', '/data', '/market', '/methodology', '/about', '/alerts'];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // Funding slugs are required (as before). The tender and buyer lists degrade to empty if their endpoints are
  // not deployed yet, so a frontend built before the backend still produces a sitemap.
  const [calls, tenders, buyers, health] = await Promise.all([
    getAllCallSlugs(),
    getAllTenderSlugs().catch(() => []),
    getAllBuyerSlugs().catch(() => []),
    getHealth(),
  ]);
  const lastModified = new Date(health.generatedAt);
  return [
    ...STATIC_PATHS.map((p) => ({ url: absoluteUrl(p), lastModified })),
    ...calls.filter((c) => isCallSlug(c.slug)).map((c) => ({ url: absoluteUrl(`/funding/${c.slug}`), lastModified: new Date(c.updatedAt) })),
    ...tenders.filter((t) => isTenderSlug(t.slug)).map((t) => ({ url: absoluteUrl(`/tenders/${t.slug}`), lastModified: new Date(t.updatedAt) })),
    ...buyers.filter((b) => isBuyerSlug(b.slug)).map((b) => ({ url: absoluteUrl(`/buyers/${b.slug}`), lastModified: new Date(b.updatedAt) })),
  ];
}
