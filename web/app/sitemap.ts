import type { MetadataRoute } from 'next';
import { getAllCallSlugs, getHealth, isCallSlug } from '@/lib/api';
import { absoluteUrl } from '@/lib/seo';

export const revalidate = 3600;

/** Only routes that exist. Filtered /funding?… views are noindex and are not listed. */
const STATIC_PATHS = ['/', '/funding'];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [calls, health] = await Promise.all([getAllCallSlugs(), getHealth()]);
  const lastModified = new Date(health.generatedAt);
  return [
    ...STATIC_PATHS.map((p) => ({ url: absoluteUrl(p), lastModified })),
    ...calls.filter((c) => isCallSlug(c.slug)).map((c) => ({ url: absoluteUrl(`/funding/${c.slug}`), lastModified: new Date(c.updatedAt) })),
  ];
}
