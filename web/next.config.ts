import type { NextConfig } from 'next';
import { PHASE_DEVELOPMENT_SERVER, PHASE_PRODUCTION_BUILD } from 'next/constants';

/**
 * A production build must know its public https:// origin: it ends up in canonical URLs,
 * Open Graph URLs, the sitemap and robots.txt (lib/seo.ts reads NEXT_PUBLIC_SITE_URL).
 * - set but not https://  -> the build fails;
 * - unset                 -> the build fails too, unless DG_ALLOW_INSECURE_SITE_URL=1
 *   (for local previews of a production build; the site then falls back to its default origin).
 * Checked in the build phase only, so `next start` in a runtime container is not affected.
 */
function assertSiteUrl(): void {
  const url = process.env.NEXT_PUBLIC_SITE_URL;
  if (!url) {
    if (process.env.DG_ALLOW_INSECURE_SITE_URL === '1') return;
    throw new Error(
      'NEXT_PUBLIC_SITE_URL is not set. A production build needs the public https:// origin of the site. ' +
        'For a local preview only, set DG_ALLOW_INSECURE_SITE_URL=1.',
    );
  }
  if (!url.startsWith('https://')) {
    throw new Error('NEXT_PUBLIC_SITE_URL must start with https:// for a production build.');
  }
}

/**
 * Content-Security-Policy.
 *
 * script-src carries 'unsafe-inline', and nothing else is relaxed. A per-request nonce (middleware)
 * was considered and rejected: a nonce only works on dynamically rendered pages, and every public page
 * here is statically generated with ISR (revalidate = 3600), where the cached HTML would carry a stale
 * nonce. The inline scripts that need it are Next's own bootstrap (self.__next_f), the theme pre-paint
 * script in app/layout.tsx; JSON-LD blocks are data, not scripts, and are not subject to script-src.
 * Hashes do not work either because Next's bootstrap payload differs on every page.
 * 'unsafe-eval' is added in the dev server only (React refresh needs it).
 *
 * Everything else is locked to same-origin: fonts are self-hosted by next/font at build time and the
 * pages make no third-party requests.
 */
function contentSecurityPolicy(dev: boolean): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ''}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join('; ');
}

export default function config(phase: string): NextConfig {
  if (phase === PHASE_PRODUCTION_BUILD) assertSiteUrl();
  const dev = phase === PHASE_DEVELOPMENT_SERVER;

  return {
    reactStrictMode: true,
    poweredByHeader: false,
    // A self-contained server.js for the runtime image (web/Dockerfile).
    output: 'standalone',
    async headers() {
      return [
        {
          source: '/(.*)',
          headers: [
            { key: 'Content-Security-Policy', value: contentSecurityPolicy(dev) },
            { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
            { key: 'X-Content-Type-Options', value: 'nosniff' },
            { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=(), payment=(), usb=()' },
            { key: 'X-Frame-Options', value: 'DENY' },
            { key: 'Strict-Transport-Security', value: 'max-age=31536000' },
          ],
        },
      ];
    },
  };
}
