import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getUserState } from '@/lib/account';
import { getPublicSample } from '@/lib/sell-report-api';
import { ReportOpener } from '@/components/dg/report-opener';
import { Gate, SLUG } from './gate';
import { openSellReport } from './actions';

/**
 * WP-162, mode A: the "Who to sell to" report on a company in our data (a supplier with TED awards, or an organisation of EU-funded
 * projects). The button makes it (actions.tsx, a POST) and the API counts it once per company and calendar month (`sell_report.quota`);
 * opening the page never does, so a link from elsewhere cannot spend an account's reports (security review of 5 November 2026).
 */
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Who to sell to: company report', robots: { index: false, follow: false } };

export default async function CompanySellReportPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  if (!SLUG.test(slug) || !(await getPublicSample())) notFound();
  const state = await getUserState();
  if (state.kind !== 'ok') {
    return <Gate><p className="m-0">The report is for signed-in accounts. <Link href={`/signin?next=/reports/who-to-sell-to/company/${slug}`} className="font-semibold">Sign in</Link>, then open this page again.</p></Gate>;
  }
  if (!state.user.features.includes('sell_report')) {
    return <Gate><p className="m-0" data-sr-plan>The supplier report comes with a paid plan (Pro, Team or Consultant). See <Link href="/app/billing" className="font-semibold">Billing</Link>.</p></Gate>;
  }
  return (
    <ReportOpener slug={slug} open={openSellReport} label="Make the report">
      <Gate><p className="m-0" data-sr-ask>Who buys what this company makes, who wins those contracts and the open tenders and calls that fit it. Making the report counts as one of this month&rsquo;s supplier reports; a company already reported on this month opens again without counting.</p></Gate>
    </ReportOpener>
  );
}
