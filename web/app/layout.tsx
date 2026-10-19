import type { Metadata, Viewport } from 'next';
import { Manrope, DM_Mono } from 'next/font/google';
import { SITE } from '@/lib/seo';
import { THEME_COLOR, THEME_SCRIPT } from '@/lib/theme';
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

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: THEME_COLOR.light },
    { media: '(prefers-color-scheme: dark)', color: THEME_COLOR.dark },
  ],
};

// Applies the theme before paint: the saved choice, else the system's scheme (lib/theme.ts). The theme-color metas follow the same choice.

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
