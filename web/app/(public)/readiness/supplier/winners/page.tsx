import type { Metadata } from 'next';
import { Breadcrumbs } from '@/components/dg/feedback';
import { AllWinners } from '@/components/readiness/winners';

export const metadata: Metadata = {
  title: 'Every winner for your codes',
  description: 'Every company that won defence-scope contracts under the CPV codes of your supplier profile, made in your browser.',
  // Private to the visitor and different for each: there is nothing here to index.
  robots: { index: false, follow: false },
};

/** WP-81: the full list behind "who to approach" (the report's list stops at 30 and the primes). */
export default function AllWinnersPage() {
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[
        { label: 'Home', href: '/' }, { label: 'Readiness check', href: '/readiness' }, { label: 'Supplier profile', href: '/readiness/supplier' },
        { label: 'Report', href: '/readiness/supplier/report' }, { label: 'Every winner', href: '/readiness/supplier/winners' },
      ]} />
      <h1 className="m-0 text-h1-sm md:text-h1">Every winner for your codes</h1>
      <AllWinners />
    </div>
  );
}
