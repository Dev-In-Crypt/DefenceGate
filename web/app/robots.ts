import type { MetadataRoute } from 'next';
import { SITE } from '@/lib/seo';

/**
 * WP-139 (r8 audit: 99 of the 111 fast 503s of 25 Oct 2026 were one crawler opening filtered supplier lists 10-15 at a time):
 * no address with a query string. Every filtered, sorted or paged view is noindex and canonicalises to its plain page, and
 * the sitemap lists none of them; the plain list pages and the detail pages stay open. The site's own scripts and images
 * (/_next/) stay readable for a crawler that renders the page.
 */
/**
 * Owner, 27 Oct 2026: AI crawlers and agents are kept off the whole site (training, AI search and agents fetching for a user).
 * Search engines (Googlebot, Bingbot) keep the rule above. robots.txt is a request, not a lock: Cloudflare enforces the rest.
 */
export const AI_AGENTS = [
  'GPTBot', 'ChatGPT-User', 'OAI-SearchBot', 'ClaudeBot', 'Claude-User', 'Claude-SearchBot', 'anthropic-ai', 'PerplexityBot',
  'Perplexity-User', 'Google-Extended', 'CCBot', 'Bytespider', 'Applebot-Extended', 'meta-externalagent', 'Amazonbot',
  'cohere-ai', 'Diffbot', 'MistralAI-User', 'DuckAssistBot', 'YouBot',
];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: AI_AGENTS, disallow: '/' }, {
      userAgent: '*',
      allow: ['/', '/_next/'],
      disallow: ['/*?', '/app', '/admin', '/v1', '/tenders/export.csv', '/funding/export.csv', '/market/export.csv', '/suppliers/*/contracts.csv', '/suppliers/export.csv'],
    }],
    sitemap: `${SITE.url}/sitemap.xml`,
    host: SITE.url,
  };
}
