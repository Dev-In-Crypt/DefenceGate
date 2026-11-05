'use server';

/**
 * Mode A of "Who to sell to" is generated and counted here, from the page's button (a POST; Next.js checks Origin against Host first),
 * never by opening the page: a link or a redirect from another site must not spend an account's reports (security review of 5 Nov 2026).
 */
import Link from 'next/link';
import { getUserState } from '@/lib/account';
import { generateSellReport } from '@/lib/sell-report-api';
import { L } from '@/lib/sell-report';
import { PageHeader } from '@/components/dg/page-header';
import { PrintButton } from '@/components/dg/print-button';
import { SellReportView } from '@/components/sell-report/report';
import { Gate, SLUG } from './gate';

export async function openSellReport(slug: unknown): Promise<React.ReactNode> {
  if (typeof slug !== 'string' || !SLUG.test(slug)) return <Gate><p className="m-0">There is no company report at this address.</p></Gate>;
  const state = await getUserState();
  if (state.kind !== 'ok') {
    return <Gate><p className="m-0">The report is for signed-in accounts. <Link href={`/signin?next=/reports/who-to-sell-to/company/${slug}`} className="font-semibold">Sign in</Link>, then open this page again.</p></Gate>;
  }
  const r = await generateSellReport({ org: slug });
  if (!r.ok && r.status === 404) return <Gate><p className="m-0">There is no company report at this address.</p></Gate>;
  if (!r.ok && r.error === 'report_quota') return <Gate><p className="m-0" data-sr-quota>{(r.message ?? 'No supplier reports left').replace(/^./, (c) => c.toUpperCase())}. A company already reported on this month opens again.</p></Gate>;
  if (!r.ok && r.status === 402) return <Gate><p className="m-0" data-sr-plan>The supplier report comes with a paid plan (Pro, Team or Consultant). See <Link href="/app/billing" className="font-semibold">Billing</Link>.</p></Gate>;
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
