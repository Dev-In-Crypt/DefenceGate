import { HeaderBar } from '@/components/dg/header-bar';
import { Footer } from '@/components/dg/footer';
import { getAccountStatus } from '@/lib/account';
import { getHealth } from '@/lib/api';
import { AccountsOpenProvider } from '@/components/account/accounts-open';
import { RouteFocus } from '@/components/dg/route-focus';
import { PrintOpenDetails } from '@/components/dg/print-open-details';

/**
 * Reads no cookie, so public pages stay statically renderable. The status call is cached for 60 seconds and any
 * failure means "not open": the header then keeps "What changed". WP-142: the footer's sources are read here too, so the
 * footer is not a part of the page that arrives on its own (components/dg/footer.tsx).
 */
export default async function PublicLayout({ children }: { children: React.ReactNode }) {
  const [{ open }, health] = await Promise.all([getAccountStatus(), getHealth()]);
  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-pill focus:bg-surface focus:px-5 focus:py-3 focus:font-bold print:hidden">
        Skip to content
      </a>
      <div className="page pt-4 print:hidden">
        <HeaderBar accountsOpen={open} />
      </div>
      <main id="main" className="page flex flex-col gap-8 py-8 md:gap-12 md:py-12 print:gap-4 print:py-0">
        <AccountsOpenProvider open={open}>{children}</AccountsOpenProvider>
      </main>
      <Footer health={health} />
      <RouteFocus />
      {/* WP-88: every collapsed "About this data" prints open, on every public page. */}
      <PrintOpenDetails />
    </>
  );
}
