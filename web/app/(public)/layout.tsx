import { HeaderBar } from '@/components/dg/header-bar';
import { Footer } from '@/components/dg/footer';
import { getAccountStatus } from '@/lib/account';
import { AccountsOpenProvider } from '@/components/account/accounts-open';

/**
 * Reads no cookie, so public pages stay statically renderable. The status call is cached for 60 seconds and any
 * failure means "not open": the header then keeps "What changed".
 */
export default async function PublicLayout({ children }: { children: React.ReactNode }) {
  const { open } = await getAccountStatus();
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
      <Footer />
    </>
  );
}
