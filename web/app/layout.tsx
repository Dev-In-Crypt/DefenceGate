import type { Metadata, Viewport } from 'next';
import { Manrope, DM_Mono } from 'next/font/google';
import { SITE } from '@/lib/seo';
import { THEME_SCRIPT } from '@/lib/theme';
import { ThemeSync } from '@/components/dg/theme-sync';
import './globals.css';

const manrope = Manrope({ subsets: ['latin', 'latin-ext', 'cyrillic'], variable: '--font-manrope', display: 'swap' });
const dmMono = DM_Mono({ subsets: ['latin', 'latin-ext'], weight: ['400', '500'], variable: '--font-dm-mono', display: 'swap' });

export const metadata: Metadata = {
  metadataBase: new URL(SITE.url),
  title: { default: `${SITE.name} · Defence and dual-use tenders and funding calls`, template: `%s · ${SITE.name}` },
  description: 'Defence and dual-use tenders and funding calls from TED and national portals in one place, each linked to its original source.',
  icons: { icon: '/brand/favicon.svg', apple: '/brand/app-icon.svg' },
};

// No `themeColor` here: Next streams viewport metas and may insert them after the theme script ran, with the per-scheme colours,
// so the browser bar would disagree with a saved choice. The theme script creates the one meta itself (React does not own it, so
// hydration cannot reset it).
export const viewport: Viewport = {};

// Applies the theme before paint: the saved choice, else the system's scheme (lib/theme.ts). The theme-color meta follows the same choice.

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${manrope.variable} ${dmMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <ThemeSync />
        {children}
      </body>
    </html>
  );
}
