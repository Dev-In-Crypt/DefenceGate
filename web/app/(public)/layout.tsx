import { HeaderBar } from '@/components/dg/header-bar';
import { Footer } from '@/components/dg/footer';

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-pill focus:bg-surface focus:px-5 focus:py-3 focus:font-bold">
        Skip to content
      </a>
      <div className="page pt-4">
        <HeaderBar />
      </div>
      <main id="main" className="page flex flex-col gap-8 py-8">
        {children}
      </main>
      <Footer />
    </>
  );
}
