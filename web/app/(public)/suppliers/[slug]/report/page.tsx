import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getSupplier, getSupplierCompetition, isSupplierSlug, REMOVED, whenRemoved } from '@/lib/api';
import { getUserState } from '@/lib/account';
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
 */
export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Company report', robots: { index: false, follow: false } };

type Props = { params: Promise<{ slug: string }> };

function Gate({ name, slug, children }: { name: string; slug: string; children: React.ReactNode }) {
  return (
    <>
      <PageHeader crumbs={[...companyCrumbs('suppliers'), { label: name, href: `/suppliers/${slug}` }, { label: 'Company report', href: `/suppliers/${slug}/report` }]}
        title={`Company report: ${name}`} />
      <Card><div className="flex flex-col gap-3 text-body" data-report-gate>{children}</div></Card>
    </>
  );
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
  const state = await getUserState();
  if (state.kind === 'anonymous' || state.kind === 'unauthorized') {
    return <Gate name={s.name} slug={s.slug}><p className="m-0">The company report is for signed-in accounts. <Link href="/signin" className="font-semibold">Sign in</Link>, then open this page again.</p></Gate>;
  }
  if (state.kind === 'unavailable') {
    return <Gate name={s.name} slug={s.slug}><p className="m-0">Your account could not be read just now. Try again in a moment.</p></Gate>;
  }
  if (!state.user.features.includes('company_report')) {
    return <Gate name={s.name} slug={s.slug}><p className="m-0" data-report-plan>The company report comes with a paid plan. See <Link href="/app/billing" className="font-semibold">Billing</Link> in your account.</p></Gate>;
  }
  if (!c.available) {
    return <Gate name={s.name} slug={s.slug}><p className="m-0">The figures of this report are being renewed. Try again in a few minutes.</p></Gate>;
  }
  const partners = await getPartners(s.slug, { page: 1, pageSize: 20 }).catch(() => null);
  return (
    <>
      <div className="print:hidden">
        <PageHeader crumbs={[...companyCrumbs('suppliers'), { label: s.name, href: `/suppliers/${s.slug}` }, { label: 'Company report', href: `/suppliers/${s.slug}/report` }]}
          title={`Company report: ${s.name}`}>
          <PrintButton className="self-start">Print or save as PDF</PrintButton>
        </PageHeader>
      </div>
      <header className="hidden flex-col gap-2 print:flex">
        <Logo />
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
      <CompetitorsCard c={c} name={s.name} />
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
