import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getUserState } from '@/lib/account';
import { formatNumber } from '@/lib/format';
import { RemovedOnRequest } from '@/components/dg/removed';
import { ReportOpener } from '@/components/dg/report-opener';
import { Gate, PlanGate, ReportBody, loadReport, openAndRender } from './report-view';
import { openCompanyReport } from './actions';

/**
 * WP-152: the company report, print-ready (the browser's print dialog saves it as PDF): the supplier page's facts, its competitors,
 * where it wins, its share and its EU project partners. A paid feature: it exists only with DGATE_COMPANY_REPORT_OPEN=1 (the API's
 * `reportOpen`; off, this address is a 404) and opens for an account the API gives `company_report` (backend billing.may). The data
 * is the public pages' own; the report is their layout for one company.
 *
 * WP-155 (owner's plan split): Pro and up, so many a calendar month (UTC), counted by the API (POST /v1/account/suppliers/{slug}/report:
 * one company once a month); a refusal says when the count starts again. One company's report (DGATE_SAMPLE_REPORT_SLUG) is open to
 * everyone, uncounted, and every paywall links to it. A Consultant's own name (account settings, plain text) is printed in the head
 * beside our logo. Opening this page never counts a report: the button does (actions.tsx, a POST), so a link from elsewhere cannot spend
 * an account's reports (security review of 5 November 2026).
 */
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Company report', robots: { index: false, follow: false } };

type Props = { params: Promise<{ slug: string }> };

export default async function CompanyReportPage({ params }: Props) {
  const { slug } = await params;
  const l = await loadReport(slug);
  if (l.kind === 'removed') return <RemovedOnRequest what="supplier" />;
  if (l.kind === 'missing') notFound();
  const { s, c, sample } = l;
  // before the opening is counted: a report that cannot be shown is not one of the month's
  if (!c.available) {
    return <Gate name={s.name} slug={s.slug}><p className="m-0">The figures of this report are being renewed. Try again in a few minutes.</p></Gate>;
  }
  const state = await getUserState();
  if (c.isSample) {
    // never counted (the API): opened at once, with the account's name on it when signed in
    if (state.kind !== 'ok') return <ReportBody l={l} opening={{ sample: true, counted: false, used: null, limit: null, left: null, resetsAt: '', reportName: null }} signedIn={false} />;
    return openAndRender(l, state);
  }
  if (state.kind !== 'ok') return openAndRender(l, state);                          // sign in, or the account could not be read
  if (!state.user.features.includes('company_report')) return <PlanGate name={s.name} slug={s.slug} sample={sample} />;
  return (
    <ReportOpener slug={s.slug} open={openCompanyReport} label="Open the report">
      <Gate name={s.name} slug={s.slug} sample={sample}>
        <p className="m-0" data-report-ask>
          The report of {s.name}: its {formatNumber(s.noticeCount)} contracts won, its competitors, where it wins, its share and its EU project partners.
          Opening it counts as one of this month&rsquo;s company reports; a report already opened this month opens again without counting.
        </p>
      </Gate>
    </ReportOpener>
  );
}
