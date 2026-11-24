import type { Metadata } from 'next';
import { NOT_FOUND_META } from '@/lib/seo';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getUserState } from '@/lib/account';
import { getKeptForm, getPublicSample } from '@/lib/sell-report-api';
import { L, SR_CRUMBS } from '@/lib/sell-report';
import { PageHeader } from '@/components/dg/page-header';
import { Card } from '@/components/dg/card';
import { SellReportForm } from '@/components/sell-report/form';
import { PLANS_FROM } from '@/lib/plans';

/**
 * WP-162: the "Who to sell to" report for a company not in our data (mode B): the form, then the report on the same page. Signed-in
 * accounts with a plan that has `sell_report` (the API decides and counts). A 404 while reports are switched off.
 */
export const dynamic = 'force-dynamic';
// F-12: while reports are switched off the page is a 404, and its tab says so (it kept the report's title)
export async function generateMetadata(): Promise<Metadata> {
  return (await getPublicSample()) ? { title: 'Who to sell to: supplier report', robots: { index: false, follow: false } } : NOT_FOUND_META;
}

export default async function SellReportPage() {
  if (!(await getPublicSample())) notFound();          // reports switched off (DGATE_COMPANY_REPORT_OPEN)
  const state = await getUserState();
  return (
    <>
      <div className="print:hidden">
        <PageHeader crumbs={SR_CRUMBS} title={L.title}
          lead="For a maker that wants to supply European defence: who buys what you make, who wins those contracts, what is open now, what you lack to qualify, and what to do in the next 90 days. 3 to 5 printed pages."
          meta={<Link href="/reports/who-to-sell-to/sample" prefetch={false}>See the sample report</Link>} />
      </div>
      {state.kind === 'ok' && state.user.features.includes('sell_report')
        ? <SellReportForm kept={await getKeptForm()} />
        : state.kind === 'ok' ? (
          // E-03: a plan without the report is told so before the form, not after it is filled in
          <Card>
            <p className="m-0 text-body" data-sr-plan-gate>
              The report is part of the {PLANS_FROM.pro}. See <Link href="/app/billing" className="font-semibold">Billing</Link> in your account,
              or <Link href="/reports/who-to-sell-to/sample" prefetch={false} className="font-semibold">see the sample report</Link>.
            </p>
          </Card>
        ) : (
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
