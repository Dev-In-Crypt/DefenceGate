import type { Metadata, Viewport } from 'next';
import { Manrope, DM_Mono } from 'next/font/google';
import { SITE } from '@/lib/seo';
import { THEME_STORAGE_KEY } from '@/lib/theme';
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
    { media: '(prefers-color-scheme: light)', color: '#F4F1EA' },
    { media: '(prefers-color-scheme: dark)', color: '#0F1D17' },
  ],
};

// Applies a saved theme before paint. Light is the default.
const themeScript = `try{var t=localStorage.getItem('${THEME_STORAGE_KEY}');if(t==='dark')document.documentElement.dataset.theme='dark'}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${manrope.variable} ${dmMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
