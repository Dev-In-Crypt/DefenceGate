import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getUserState } from '@/lib/account';
import { getKeptForm, getPublicSample } from '@/lib/sell-report-api';
import { L } from '@/lib/sell-report';
import { PageHeader } from '@/components/dg/page-header';
import { Card } from '@/components/dg/card';
import { SellReportForm } from '@/components/sell-report/form';

/**
 * WP-162: the "Who to sell to" report for a company not in our data (mode B): the form, then the report on the same page. Signed-in
 * accounts with a plan that has `sell_report` (the API decides and counts). A 404 while reports are switched off.
 */
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Who to sell to: supplier report', robots: { index: false, follow: false } };

export default async function SellReportPage() {
  if (!(await getPublicSample())) notFound();          // reports switched off (DGATE_COMPANY_REPORT_OPEN)
  const state = await getUserState();
  return (
    <>
      <div className="print:hidden">
        <PageHeader crumbs={[{ label: 'Reports', href: '/reports/who-to-sell-to' }]} title={L.title}
          lead="For a maker that wants to supply European defence: who buys what you make, who wins those contracts, what is open now, what you lack to qualify, and what to do in the next 90 days. 3 to 5 printed pages."
          meta={<Link href="/reports/who-to-sell-to/sample" prefetch={false}>See the sample report</Link>} />
      </div>
      {state.kind === 'ok'
        ? <SellReportForm kept={await getKeptForm()} />
        : (
          <Card>
            <p className="m-0 text-body" data-sr-signin-gate>
              The report is for signed-in accounts. <Link href="/signin?next=/reports/who-to-sell-to" className="font-semibold">Sign in</Link>, then open this page
              again, or <Link href="/reports/who-to-sell-to/sample" prefetch={false} className="font-semibold">see the sample report</Link>.
            </p>
          </Card>
        )}
    </>
  );
}
