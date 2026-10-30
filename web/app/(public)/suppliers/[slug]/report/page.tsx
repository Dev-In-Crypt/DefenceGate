import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getSupplier, getSupplierCompetition, isSupplierSlug, REMOVED, whenRemoved } from '@/lib/api';
import { getFullCompetition, getUserState, openReport, type ReportOpening } from '@/lib/account';
import { clientContext } from '@/lib/workspace';
import { getPartners } from '@/lib/networks-api';
import type { PartnerPage } from '@/lib/networks-types';
import { displayName } from '@/lib/display-name';
import { formatDateUtc, formatNumber } from '@/lib/format';
import { countryName } from '@/lib/taxonomy';
import { PageHeader } from '@/components/dg/page-header';
import { Card } from '@/components/dg/card';
import { DataTable } from '@/components/dg/data-table';
import { FactsGrid } from '@/components/dg/facts-grid';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { NoteLine } from '@/components/dg/blocks';
import { PrintButton } from '@/components/dg/print-button';
import { Logo } from '@/components/dg/logo';
import { ValueTotalsBlock } from '@/components/dg/value-totals';
import { RemovedOnRequest } from '@/components/dg/removed';
import { CompetitorsCard, ShareCard, WhereItWins } from '@/components/dg/competition';
import { companyCrumbs } from '@/components/dg/companies-tabs';

/**
 * WP-152: the company report, print-ready (the browser's print dialog saves it as PDF): the supplier page's facts, its competitors,
 * where it wins, its share and its EU project partners. A paid feature: it exists only with DGATE_COMPANY_REPORT_OPEN=1 (the API's
 * `reportOpen`; off, this address is a 404) and opens for an account the API gives `company_report` (backend billing.may). The data
 * is the public pages' own; the report is their layout for one company.
 *
 * WP-155 (owner's plan split): Pro and up, so many a calendar month (UTC), counted by the API when the page opens (POST
 * /v1/account/suppliers/{slug}/report: one company once a month); a refusal says when the count starts again. One company's report
 * (DGATE_SAMPLE_REPORT_SLUG) is open to everyone, uncounted, and every paywall links to it. A Consultant's own name (account settings,
 * plain text) is printed in the head beside our logo.
 */
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Company report', robots: { index: false, follow: false } };

type Props = { params: Promise<{ slug: string }> };

function Gate({ name, slug, sample, children }: { name: string; slug: string; sample?: string | null; children: React.ReactNode }) {
  return (
    <>
      <PageHeader crumbs={[...companyCrumbs('suppliers'), { label: name, href: `/suppliers/${slug}` }, { label: 'Company report', href: `/suppliers/${slug}/report` }]}
        title={`Company report: ${name}`} />
      <Card>
        <div className="flex flex-col gap-3 text-body" data-report-gate>
          {children}
          {sample && <p className="m-0"><Link href={`/suppliers/${sample}/report`} prefetch={false} className="font-semibold" data-sample-link>See a sample report</Link></p>}
        </div>
      </Card>
    </>
  );
}

/** The API's refusal ("no company reports left this month: 3 of 3 opened; the count starts again on ..."), as a sentence. */
function quotaRefusal(message: string | undefined): string {
  const m = (message ?? 'no company reports left this month').replace(/[.\s]+$/, '');
  return m.charAt(0).toUpperCase() + m.slice(1);
}

/** "2 of 3 reports this month; the count starts again on 1 November 2026." */
function quotaLine(o: ReportOpening): string | null {
  if (o.sample) return 'A sample report: open to everyone, not counted against any plan.';
  if (o.limit === null || o.used === null) return null;
  return `${formatNumber(o.used)} of ${formatNumber(o.limit)} company reports this month opened; the count starts again on ${formatDateUtc(o.resetsAt)}.`;
}

function Partners({ p }: { p: PartnerPage | null }) {
  return (
    <Card title="EU project partners" id="partners">
      {!p || p.items.length === 0 ? (
        <p className="m-0 text-body">No EU-funded project lists this company&rsquo;s record as a participant.</p>
      ) : (
        <DataTable label="Organisations that took part in the same EU-funded projects" minWidth={560}>
          <thead>
            <tr><th scope="col" className="min-w-52">Organisation</th><th scope="col">Country</th><th scope="col" className="text-right">Shared projects</th><th scope="col">Years</th><th scope="col">Programmes</th></tr>
          </thead>
          <tbody>
            {p.items.map((r) => (
              <tr key={r.organisation.slug ?? r.organisation.name} data-partner>
                <th scope="row" className="font-normal">
                  {r.organisation.slug ? <Link href={`/organisations/${r.organisation.slug}`} className="break-words">{r.organisation.name}</Link> : r.organisation.name}
                </th>
                <td className="whitespace-nowrap font-mono tabular-nums">{r.organisation.country ?? ''}</td>
                <td className="text-right font-mono tabular-nums">{formatNumber(r.shared)}</td>
                <td className="whitespace-nowrap font-mono tabular-nums">{r.firstYear === r.lastYear ? (r.firstYear ?? '') : `${r.firstYear}–${r.lastYear}`}</td>
                <td>{r.programmes.join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
      {p && p.total > p.items.length && <NoteLine>The {p.items.length} of {formatNumber(p.total)} partners with the most shared projects.</NoteLine>}
    </Card>
  );
}

export default async function CompanyReportPage({ params }: Props) {
  const { slug } = await params;
  if (!isSupplierSlug(slug)) notFound();
  const [got, c] = await Promise.all([getSupplier(slug).catch(whenRemoved), getSupplierCompetition(slug).catch(() => null)]);
  if (got === REMOVED) return <RemovedOnRequest what="supplier" />;
  if (!got || !c?.reportOpen) notFound();
  const s = { ...got, name: displayName(got.name, 'title') };
  const sample = c.isSample ? null : (c.sampleReport ?? null);
  // before the opening is counted: a report that cannot be shown is not one of the month's
  if (!c.available) {
    return <Gate name={s.name} slug={s.slug}><p className="m-0">The figures of this report are being renewed. Try again in a few minutes.</p></Gate>;
  }
  const state = await getUserState();
  let opening: ReportOpening = { sample: true, counted: false, used: null, limit: null, left: null, resetsAt: '', reportName: null };
  if (!c.isSample || state.kind === 'ok') {
    if (state.kind === 'anonymous' || state.kind === 'unauthorized') {
      return <Gate name={s.name} slug={s.slug} sample={sample}><p className="m-0">The company report is for signed-in accounts. <Link href={`/signin?next=/suppliers/${s.slug}/report`} className="font-semibold">Sign in</Link>, then open this page again.</p></Gate>;
    }
    if (state.kind === 'unavailable') {
      return <Gate name={s.name} slug={s.slug} sample={sample}><p className="m-0">Your account could not be read just now. Try again in a moment.</p></Gate>;
    }
    // WP-157: the client profile worked on (Consultant) goes on the report's head; a stale choice is asked again without it
    const { active } = await clientContext(state.user.features);
    let r = await openReport(s.slug, active?.id);
    if (active && !r.ok && r.status === 404) r = await openReport(s.slug);
    if (!r.ok && r.status === 402 && r.error === 'report_quota') {
      return <Gate name={s.name} slug={s.slug} sample={sample}><p className="m-0" data-report-quota>{quotaRefusal(r.message)}. Reports already opened this month open again; see <Link href="/app/billing" className="font-semibold">Billing</Link> for a plan with more.</p></Gate>;
    }
    if (!r.ok && r.status === 402) {
      return <Gate name={s.name} slug={s.slug} sample={sample}><p className="m-0" data-report-plan>The company report comes with a paid plan (Pro, Team or Consultant). See <Link href="/app/billing" className="font-semibold">Billing</Link> in your account.</p></Gate>;
    }
    if (!r.ok && r.status === 404) notFound();
    if (!r.ok) {
      return <Gate name={s.name} slug={s.slug} sample={sample}><p className="m-0">Your account could not be read just now. Try again in a moment.</p></Gate>;
    }
    opening = r.data;
  }
  const quota = quotaLine(opening);
  const [partners, full] = await Promise.all([getPartners(s.slug, { page: 1, pageSize: 20 }).catch(() => null), state.kind === 'ok' ? getFullCompetition(s.slug) : null]);
  // WP-155: the whole competitor list when the plan has it (Pro and up), else the public first five
  const comp = full?.ok && full.data.available ? full.data : c;
  return (
    <>
      <div className="print:hidden">
        <PageHeader crumbs={[...companyCrumbs('suppliers'), { label: s.name, href: `/suppliers/${s.slug}` }, { label: 'Company report', href: `/suppliers/${s.slug}/report` }]}
          title={`Company report: ${s.name}`}>
          <PrintButton className="self-start">Print or save as PDF</PrintButton>
          {quota && <p className="m-0 text-small text-ink-muted" data-report-quota-line>{quota}</p>}
          {opening.reportName && <p className="m-0 text-small" data-report-name-screen>Printed with your name: {opening.reportName}</p>}
          {opening.clientName && <p className="m-0 text-small" data-report-client-screen>Prepared for: {opening.clientName} (change it under <Link href="/app/clients" className="font-semibold">Clients</Link>)</p>}
        </PageHeader>
      </div>
      <header className="hidden flex-col gap-2 print:flex">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Logo />
          {opening.reportName && <p className="m-0 text-h3 font-bold" data-report-name>{opening.reportName}</p>}
        </div>
        {opening.clientName && <p className="m-0 text-body" data-report-client>Prepared for {opening.clientName}</p>}

        <p className="m-0 text-small font-bold uppercase tracking-wide">Company report, {formatDateUtc(new Date().toISOString())}</p>
        <h1 className="m-0 text-h1">{s.name}</h1>
      </header>
      <section aria-label="The company" className="flex flex-col gap-4" data-company-report>
        <FactsGrid>
          <FactCell label="Country"><CountryLabel code={s.country} className="font-sans" /></FactCell>
          <FactCell label="Contracts won, last three years"><span className="tabular-nums">{formatNumber(s.noticeCount)}</span></FactCell>
          <FactCell label="Years"><span className="tabular-nums">{s.firstYear ? (s.firstYear === s.lastYear ? s.firstYear : `${s.firstYear} to ${s.lastYear}`) : 'Not stated'}</span></FactCell>
          {s.identifiers.length > 0 && <FactCell label="Registration number as published">{s.identifiers.join(', ')}</FactCell>}
        </FactsGrid>
        {s.values && <ValueTotalsBlock values={s.values} noun="contract" scope={`All ${formatNumber(s.noticeCount)} contracts it won in the award notices behind this report.`} />}
      </section>
      <CompetitorsCard c={comp} name={s.name} />
      <WhereItWins c={c} name={s.name} />
      <ShareCard c={c} name={s.name} />
      {s.buyers.length > 0 && (
        <Card title="Main buyers" id="buyers">
          <DataTable label="Buyers whose notices name this company a winner" minWidth={420}>
            <thead><tr><th scope="col" className="min-w-52">Buyer</th><th scope="col">Country</th><th scope="col" className="text-right">Contracts</th></tr></thead>
            <tbody>
              {s.buyers.map((b) => (
                <tr key={b.slug}>
                  <th scope="row" className="font-normal"><Link href={`/buyers/${b.slug}`} className="break-words">{b.name}</Link></th>
                  <td className="whitespace-nowrap">{b.country ? countryName(b.country) : ''}</td>
                  <td className="text-right font-mono tabular-nums">{formatNumber(b.awards)}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </Card>
      )}
      <Partners p={partners} />
      <footer className="flex flex-col gap-2 text-small text-ink-muted" data-report-sources>
        <p className="m-0">
          Open segment only: defence-relevant award notices of the last three years{c.since ? `, from ${formatDateUtc(c.since)}` : ''}; the company&rsquo;s real volume is larger.
          Figures as of {c.asOf ? formatDateUtc(c.asOf) : 'the latest renewal'}. Facts from public records; winners that are natural persons are counted, never named.
        </p>
        <p className="m-0">
          {s.attribution}
          {partners && <> EU project partners as the European Commission&rsquo;s CORDIS database and the European Defence Fund factsheets state them; sources and licences on the <Link href={`/organisations/${partners.organisation.slug ?? s.slug}`}>organisation&rsquo;s page</Link>.</>}
        </p>
      </footer>
    </>
  );
}
