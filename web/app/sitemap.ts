import type { MetadataRoute } from 'next';
import { getAllCallSlugs, getHealth } from '@/lib/api';
import { absoluteUrl } from '@/lib/seo';
import { FUNDER_COUNTRIES, PROGRAMMES, REGIME_CODES } from '@/lib/taxonomy';

export const revalidate = 3600;

const STATIC_PATHS = ['/', '/funding', '/funding/open', '/funding/closing-soon', '/data', '/pricing', '/pack', '/alerts/subscribe', '/privacy', '/terms', '/imprint'];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [calls, health] = await Promise.all([getAllCallSlugs(), getHealth()]);
  const lastModified = new Date(health.generatedAt);
  const hubs = [
    ...FUNDER_COUNTRIES.map((c) => `/funding/country/${c.toLowerCase()}`),
    ...Object.values(PROGRAMMES).map((p) => `/funding/programme/${p.slug}`),
    ...REGIME_CODES.map((r) => `/funding/regime/${r}`),
  ];
  return [
    ...[...STATIC_PATHS, ...hubs].map((p) => ({ url: absoluteUrl(p), lastModified })),
    ...calls.map((c) => ({ url: absoluteUrl(`/funding/${c.slug}`), lastModified: new Date(c.updatedAt) })),
  ];
}
