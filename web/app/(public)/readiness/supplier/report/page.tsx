import type { Metadata } from 'next';
import { getRequirements } from '@/lib/readiness-api';
import { Breadcrumbs } from '@/components/dg/feedback';
import { SupplierReport } from '@/components/readiness/report';

export const metadata: Metadata = {
  title: 'Supplier readiness report',
  description: 'A printable report of your supplier profile, your readiness results and your supplier roadmap, made in your browser.',
  // Private to the visitor and different for each: there is nothing here to index.
  robots: { index: false, follow: false },
};

/** The requirement names of the public catalogue (no visitor data goes into this read); the report works without them. */
async function names(): Promise<Record<string, string>> {
  try {
    return Object.fromEntries((await getRequirements()).items.map((r) => [r.code, r.name]));
  } catch {
    return {};
  }
}

export default async function SupplierReportPage() {
  return (
    <>
      <div className="print:hidden">
        <Breadcrumbs items={[
          { label: 'Home', href: '/' }, { label: 'Readiness check', href: '/readiness' }, { label: 'Supplier profile', href: '/readiness/supplier' },
          { label: 'Report', href: '/readiness/supplier/report' },
        ]} />
      </div>
      <SupplierReport names={await names()} />
    </>
  );
}
