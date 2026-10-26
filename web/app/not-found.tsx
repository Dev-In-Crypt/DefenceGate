import type { Metadata } from 'next';
import Link from 'next/link';
import { getAccountStatus } from '@/lib/account';
import { getHealth } from '@/lib/api';
import { NOT_FOUND_META } from '@/lib/seo';
import { HeaderBar } from '@/components/dg/header-bar';
import { Footer } from '@/components/dg/footer';
import { Button } from '@/components/dg/button';
import { AutoGrid } from '@/components/dg/auto-grid';

export const metadata: Metadata = NOT_FOUND_META;

const LINKS = [
  { label: 'Funding calls', href: '/funding', text: 'Open EU and national funding calls.' },
  { label: 'Tenders', href: '/tenders', text: 'Procurement notices from defence buyers.' },
  { label: 'Buyers', href: '/buyers', text: 'The bodies behind the notices.' },
  { label: 'Deadline calendar', href: '/calendar', text: 'Upcoming deadlines in one calendar.' },
  { label: 'Source status', href: '/data', text: 'What we collect and when it last ran.' },
];

/**
 * The 404 of the whole site (an address no route matches, and `notFound()` from a route without its own page).
 * It lives outside the (public) layout, so it draws the header and footer itself.
 */
export default async function NotFound() {
  const [{ open }, health] = await Promise.all([getAccountStatus(), getHealth()]);
  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-pill focus:bg-surface focus:px-5 focus:py-3 focus:font-bold">
        Skip to content
      </a>
      <div className="page pt-4">
        <HeaderBar accountsOpen={open} />
      </div>
      <main id="main" className="page flex flex-col gap-8 py-8 md:gap-12 md:py-12">
        <header className="flex flex-col gap-3">
          <p className="m-0 font-mono text-mono text-ink-muted">Error 404</p>
          <h1 className="m-0 page-title">This page is not in the directory</h1>
          <p className="lead m-0 max-w-prose">
            The address may be mistyped, or the notice or call may no longer be listed. Try the search on one of the lists below.
          </p>
        </header>
        <AutoGrid as="ul" fill min={340}>
          {LINKS.map((l) => (
            <li key={l.href} className="flex min-w-0 flex-col gap-1 rounded-lg border border-transparent bg-surface p-5">
              <Link href={l.href} className="text-body font-bold">{l.label}</Link>
              <span className="text-small text-ink-muted">{l.text}</span>
            </li>
          ))}
        </AutoGrid>
        <div>
          <Button href="/">Back to the home page</Button>
        </div>
      </main>
      <Footer health={health} />
    </>
  );
}
