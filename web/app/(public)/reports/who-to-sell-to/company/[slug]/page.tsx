import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getUserState } from '@/lib/account';
import { generateSellReport, getPublicSample } from '@/lib/sell-report-api';
import { L } from '@/lib/sell-report';
import { PageHeader } from '@/components/dg/page-header';
import { Card } from '@/components/dg/card';
import { PrintButton } from '@/components/dg/print-button';
import { SellReportView } from '@/components/sell-report/report';

/**
 * WP-162, mode A: the "Who to sell to" report on a company in our data (a supplier with TED awards, or an organisation of EU-funded
 * projects). Opening the page generates it and counts it once per company and calendar month (the API, `sell_report.quota`).
 */
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Who to sell to: company report', robots: { index: false, follow: false } };

const SLUG = /^\d{1,19}(-[a-z0-9-]{0,100})?$/;

function Gate({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PageHeader crumbs={[{ label: 'Reports', href: '/reports/who-to-sell-to' }]} title={L.title} />
      <Card><div className="flex flex-col gap-3 text-body" data-sr-gate>{children}
        <p className="m-0"><Link href="/reports/who-to-sell-to/sample" prefetch={false} className="font-semibold">See the sample report</Link></p></div></Card>
    </>
  );
}

export default async function CompanySellReportPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  if (!SLUG.test(slug) || !(await getPublicSample())) notFound();
  const state = await getUserState();
  if (state.kind !== 'ok') {
    return <Gate><p className="m-0">The report is for signed-in accounts. <Link href={`/signin?next=/reports/who-to-sell-to/company/${slug}`} className="font-semibold">Sign in</Link>, then open this page again.</p></Gate>;
  }
  const r = await generateSellReport({ org: slug });
  if (!r.ok && r.status === 404) notFound();
  if (!r.ok && r.error === 'report_quota') return <Gate><p className="m-0" data-sr-quota>{(r.message ?? 'No supplier reports left').replace(/^./, (c) => c.toUpperCase())}. A company already reported on this month opens again.</p></Gate>;
  if (!r.ok && r.status === 402) return <Gate><p className="m-0">The supplier report comes with a paid plan (Pro, Team or Consultant). See <Link href="/app/billing" className="font-semibold">Billing</Link>.</p></Gate>;
  if (!r.ok && r.status === 410) return <Gate><p className="m-0">This company&rsquo;s record was removed on request.</p></Gate>;
  if (!r.ok) return <Gate><p className="m-0">The report could not be made just now. Try again in a moment.</p></Gate>;
  const q = r.data.quota;
  return (
    <>
      <div className="print:hidden">
        <PageHeader crumbs={[{ label: 'Reports', href: '/reports/who-to-sell-to' }]} title={`${L.title}: ${r.data.profile.name ?? ''}`}>
          <PrintButton className="self-start">{L.printButton}</PrintButton>
          {q && q.limit !== null && <p className="m-0 text-small text-ink-muted" data-sr-quota>{`${q.used} of ${q.limit} supplier reports used this ${q.per}.`}</p>}
        </PageHeader>
      </div>
      <SellReportView r={r.data} />
    </>
  );
}
