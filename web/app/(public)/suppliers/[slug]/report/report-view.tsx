import 'server-only';
import Link from 'next/link';
import { getSupplier, getSupplierCompetition, isSupplierSlug, REMOVED, whenRemoved } from '@/lib/api';
import type { Supplier, SupplierCompetition } from '@/lib/types';
import { getFullCompetition, openReport, type ReportOpening, type UserState } from '@/lib/account';
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
import { CompetitorsCard, ShareCard, WhereItWins } from '@/components/dg/competition';
import { companyCrumbs } from '@/components/dg/companies-tabs';

/**
 * The company report's parts, shared by the page (GET: never counts) and its action (POST from the page's button: counts). See page.tsx.
 */
export type Loaded =
  | { kind: 'missing' } | { kind: 'removed' }
  | { kind: 'ok'; s: Supplier & { name: string }; c: SupplierCompetition; sample: string | null };

/** The supplier and its competition answer, or why there is no report (no such company, reports switched off, removed on request). */
export async function loadReport(slug: string): Promise<Loaded> {
  if (!isSupplierSlug(slug)) return { kind: 'missing' };
  const [got, c] = await Promise.all([getSupplier(slug).catch(whenRemoved), getSupplierCompetition(slug).catch(() => null)]);
  if (got === REMOVED) return { kind: 'removed' };
  if (!got || !c?.reportOpen) return { kind: 'missing' };
  return { kind: 'ok', s: { ...got, name: displayName(got.name, 'title') }, c, sample: c.isSample ? null : (c.sampleReport ?? null) };
}

export function Gate({ name, slug, sample, children }: { name: string; slug: string; sample?: string | null; children: React.ReactNode }) {
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

/**
 * Asks the API to open the report (POST /v1/account/suppliers/{slug}/report: counted once per company and month, never for the sample)
 * and renders it, or the refusal. Only the sample page and the page's action call this; a GET of a counted report never does.
 */
export async function openAndRender(l: Extract<Loaded, { kind: 'ok' }>, state: UserState): Promise<React.ReactNode> {
  const { s, c, sample } = l;
  if (state.kind === 'anonymous' || state.kind === 'unauthorized') {
    return <Gate name={s.name} slug={s.slug} sample={sample}><p className="m-0">The company report is for signed-in accounts. <Link href={`/signin?next=/suppliers/${s.slug}/report`} className="font-semibold">Sign in</Link>, then open this page again.</p></Gate>;
  }
  const unread = <Gate name={s.name} slug={s.slug} sample={sample}><p className="m-0">Your account could not be read just now. Try again in a moment.</p></Gate>;
  if (state.kind !== 'ok') return unread;
  // WP-157: the client profile worked on (Consultant) goes on the report's head; a stale choice is asked again without it
  const { active } = await clientContext(state.user.features);
  let r = await openReport(s.slug, active?.id);
  if (active && !r.ok && r.status === 404) r = await openReport(s.slug);
  if (!r.ok && r.status === 402 && r.error === 'report_quota') {
    return <Gate name={s.name} slug={s.slug} sample={sample}><p className="m-0" data-report-quota>{quotaRefusal(r.message)}. Reports already opened this month open again; see <Link href="/app/billing" className="font-semibold">Billing</Link> for a plan with more.</p></Gate>;
  }
  if (!r.ok && r.status === 402) return <PlanGate name={s.name} slug={s.slug} sample={sample} />;
  if (!r.ok && r.status === 404) return <Gate name={s.name} slug={s.slug}><p className="m-0">There is no company report for this company.</p></Gate>;
  if (!r.ok) return unread;
  return <ReportBody l={l} opening={r.data} signedIn />;
}

export function PlanGate({ name, slug, sample }: { name: string; slug: string; sample: string | null }) {
  return <Gate name={name} slug={slug} sample={sample}><p className="m-0" data-report-plan>The company report comes with a paid plan (Pro, Team or Consultant). See <Link href="/app/billing" className="font-semibold">Billing</Link> in your account.</p></Gate>;
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

export async function ReportBody({ l, opening, signedIn }: { l: Extract<Loaded, { kind: 'ok' }>; opening: ReportOpening; signedIn: boolean }) {
  const { s, c } = l;
  const quota = quotaLine(opening);
  const [partners, full] = await Promise.all([getPartners(s.slug, { page: 1, pageSize: 20 }).catch(() => null), signedIn ? getFullCompetition(s.slug) : null]);
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
