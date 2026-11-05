import Link from 'next/link';
import { L } from '@/lib/sell-report';
import { PageHeader } from '@/components/dg/page-header';
import { Card } from '@/components/dg/card';

/** A company's id, optionally with its name slug (the API resolves it). */
export const SLUG = /^\d{1,19}(-[a-z0-9-]{0,100})?$/;

export function Gate({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PageHeader crumbs={[{ label: 'Reports', href: '/reports/who-to-sell-to' }]} title={L.title} />
      <Card><div className="flex flex-col gap-3 text-body" data-sr-gate>{children}
        <p className="m-0"><Link href="/reports/who-to-sell-to/sample" prefetch={false} className="font-semibold">See the sample report</Link></p></div></Card>
    </>
  );
}
