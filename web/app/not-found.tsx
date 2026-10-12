import type { Metadata } from 'next';
import Link from 'next/link';
import { getAccountStatus } from '@/lib/account';
import { HeaderBar } from '@/components/dg/header-bar';
import { Footer } from '@/components/dg/footer';
import { Button } from '@/components/dg/button';

export const metadata: Metadata = {
  title: 'Page not found',
  description: 'This address is not a page of DefenceGate. Browse defence tenders, buyers and funding calls from here.',
  robots: { index: false, follow: true },
};

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
  const { open } = await getAccountStatus();
  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-pill focus:bg-surface focus:px-5 focus:py-3 focus:font-bold">
        Skip to content
      </a>
      <div className="page pt-4">
        <HeaderBar accountsOpen={open} />
      </div>
      <main id="main" className="page flex flex-col gap-8 py-8">
        <header className="flex flex-col gap-3">
          <p className="m-0 font-mono text-mono text-ink-muted">Error 404</p>
          <h1 className="m-0 text-[32px] font-extrabold leading-10 tracking-[-1px] md:text-h1">This page is not in the directory</h1>
          <p className="m-0 max-w-[62ch] text-body text-ink-muted">
            The address may be mistyped, or the notice or call may no longer be listed. Try the search on one of the lists below.
          </p>
        </header>
        <ul className="m-0 grid list-none gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3">
          {LINKS.map((l) => (
            <li key={l.href} className="flex min-w-0 flex-col gap-1 rounded-lg bg-surface p-5">
              <Link href={l.href} className="text-body font-bold">{l.label}</Link>
              <span className="text-small text-ink-muted">{l.text}</span>
            </li>
          ))}
        </ul>
        <div>
          <Button href="/">Back to the home page</Button>
        </div>
      </main>
      <Footer />
    </>
  );
}
