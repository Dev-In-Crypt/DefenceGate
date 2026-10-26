import type { MetadataRoute } from 'next';
import { SITE } from '@/lib/seo';

/**
 * WP-139 (r8 audit: 99 of the 111 fast 503s of 25 Oct 2026 were one crawler opening filtered supplier lists 10-15 at a time):
 * no address with a query string. Every filtered, sorted or paged view is noindex and canonicalises to its plain page, and
 * the sitemap lists none of them; the plain list pages and the detail pages stay open. The site's own scripts and images
 * (/_next/) stay readable for a crawler that renders the page.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{
      userAgent: '*',
      allow: ['/', '/_next/'],
      disallow: ['/*?', '/app', '/admin', '/v1', '/tenders/export.csv', '/funding/export.csv', '/market/export.csv', '/suppliers/*/contracts.csv'],
    }],
    sitemap: `${SITE.url}/sitemap.xml`,
    host: SITE.url,
  };
}
