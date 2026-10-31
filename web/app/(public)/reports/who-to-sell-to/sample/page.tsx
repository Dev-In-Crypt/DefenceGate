import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getUserState } from '@/lib/account';
import { getNamedSample, getPublicSample } from '@/lib/sell-report-api';
import { L } from '@/lib/sell-report';
import { PageHeader } from '@/components/dg/page-header';
import { PrintButton } from '@/components/dg/print-button';
import { SellReportView } from '@/components/sell-report/report';

/**
 * WP-162: the free sample of the "Who to sell to" report, for a fictitious demo company: open to everyone, never counted. A visitor who is
 * not signed in sees no company named in section 3; a signed-in account sees the names the mosaic rule allows. A 404 while reports are
 * switched off (DGATE_COMPANY_REPORT_OPEN).
 */
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Who to sell to: sample report', robots: { index: false, follow: false } };

export default async function SellReportSamplePage() {
  const state = await getUserState();
  const named = state.kind === 'ok' ? await getNamedSample() : null;
  const r = named?.ok ? named.data : await getPublicSample();
  if (!r) notFound();
  return (
    <>
      <div className="print:hidden">
        <PageHeader crumbs={[{ label: 'Reports', href: '/reports/who-to-sell-to' }, { label: 'Sample', href: '/reports/who-to-sell-to/sample' }]}
          title={`${L.title}: sample report`}>
          <PrintButton className="self-start">{L.printButton}</PrintButton>
          <p className="m-0 text-small text-ink-muted">
            To make the report for your own company, <Link href="/reports/who-to-sell-to" prefetch={false} className="font-semibold">describe what it makes</Link>.
          </p>
        </PageHeader>
      </div>
      <SellReportView r={r} />
    </>
  );
}
