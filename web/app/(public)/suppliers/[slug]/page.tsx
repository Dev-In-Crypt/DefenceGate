import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, permanentRedirect } from 'next/navigation';
import { getSupplier, isSupplierSlug, REMOVED, whenRemoved } from '@/lib/api';
import { RemovedOnRequest } from '@/components/dg/removed';
import { cpvDivisionLabel } from '@/lib/taxonomy';
import { formatDateUtc, formatNumber } from '@/lib/format';
import { buildMetadata } from '@/lib/seo';
import { PageHeader } from '@/components/dg/page-header';
import { Card } from '@/components/dg/card';
import { AutoGrid } from '@/components/dg/auto-grid';
import { DataTable } from '@/components/dg/data-table';
import { FactsGrid } from '@/components/dg/facts-grid';
import { CountryLabel, FactCell } from '@/components/dg/data-display';

export const revalidate = 300;
type Props = { params: Promise<{ slug: string }> };


export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const s = await getSupplier(slug).catch(whenRemoved);
  if (s === REMOVED) return { title: 'Removed on request', robots: { index: false } };
  if (!s) return { title: 'Supplier not found', robots: { index: false } };
  return buildMetadata({
    title: s.name,
    description: `${s.name} (${s.country}): ${s.noticeCount} defence-relevant TED result notices naming it as a winner. The open segment of the market only.`,
    path: `/suppliers/${s.slug}`,
    noindex: false,
  });
}

export default async function SupplierPage({ params }: Props) {
  const { slug } = await params;
  if (!isSupplierSlug(slug)) notFound();
  const s = await getSupplier(slug).catch(whenRemoved);
  if (s === REMOVED) return <RemovedOnRequest what="supplier" />;
  if (!s) notFound();
  if (s.slug !== slug && isSupplierSlug(s.slug)) permanentRedirect(`/suppliers/${s.slug}`);
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', href: '/' }, { label: 'Suppliers', href: '/suppliers' }, { label: s.name, href: `/suppliers/${s.slug}` }]} title={s.name}>
        <FactsGrid>
          <FactCell label="Country"><CountryLabel code={s.country} className="font-sans" /></FactCell>
          <FactCell label="Notices naming it a winner"><span className="tabular-nums">{formatNumber(s.noticeCount)}</span></FactCell>
          <FactCell label="Years">
            <span className="tabular-nums">{s.firstYear ? (s.firstYear === s.lastYear ? s.firstYear : `${s.firstYear} to ${s.lastYear}`) : 'Not stated'}</span>
          </FactCell>
          {s.identifiers.length > 0 && <FactCell label="Registration number as published">{s.identifiers.join(', ')}</FactCell>}
        </FactsGrid>
        {s.namesAsStated.length > 1 && (
          <p className="m-0 max-w-prose text-small text-ink-muted">Also published as: {s.namesAsStated.slice(1).join('; ')}.</p>
        )}
        <p className="m-0 max-w-prose text-small text-ink-muted">
          This is what buyers published in TED result notices of the defence-relevant scope, from 2023. TED holds only part of European defence
          spending (about a tenth, by a 2025 ECIPE brief we have not re-checked), so a company can have won far more than is shown here. There is no ranking, no share and no contract total: a value appears only on a notice
          that names one winner. {s.attribution} To ask for a removal, see the <Link href="/privacy" className="font-semibold">privacy notice</Link>.
        </p>
      </PageHeader>

      <AutoGrid min={380}>
        <Card title="Notices per year" id="by-year" className="self-start">
          <DataTable label={`Notices naming ${s.name} a winner, per year of publication`} minWidth={240}>
            <thead><tr><th scope="col">Year</th><th scope="col" className="text-right">Notices</th></tr></thead>
            <tbody>
              {s.byYear.map((y) => (
                <tr key={y.year}>
                  <th scope="row" className="font-normal tabular-nums">{y.year}</th>
                  <td className="text-right font-mono tabular-nums">{formatNumber(y.awards)}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </Card>
        <Card title="Product groups" id="by-cpv" className="self-start">
          <DataTable label={`Notices naming ${s.name} a winner, per CPV division`} minWidth={280}>
            <thead><tr><th scope="col">CPV division</th><th scope="col" className="text-right">Notices</th></tr></thead>
            <tbody>
              {s.byCpv.map((c) => (
                <tr key={c.division}>
                  <th scope="row" className="font-normal">{c.division} {cpvDivisionLabel(c.division) ?? ''}</th>
                  <td className="text-right font-mono tabular-nums">{formatNumber(c.awards)}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </Card>
      </AutoGrid>

      {s.buyers.length > 0 && (
        <Card title="Buyers" id="buyers">
          <DataTable label="Buyers whose notices name this supplier a winner" minWidth={420}>
            <thead>
              <tr><th scope="col" className="min-w-52">Buyer</th><th scope="col">Country</th><th scope="col" className="text-right">Notices</th></tr>
            </thead>
            <tbody>
              {s.buyers.map((b) => (
                <tr key={b.slug}>
                  <th scope="row" className="font-normal"><Link href={`/buyers/${b.slug}`} className="break-words">{b.name}</Link></th>
                  <td className="whitespace-nowrap font-mono tabular-nums">{b.country ?? ''}</td>
                  <td className="whitespace-nowrap text-right font-mono tabular-nums">{formatNumber(b.awards)}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </Card>
      )}

      <section aria-labelledby="notices" className="flex flex-col gap-4">
        <div className="flex flex-col gap-3">
          <h2 id="notices" className="m-0 text-h2">The notices</h2>
          <p className="m-0 max-w-prose text-small text-ink-muted">
            Newest first{s.noticeCount > s.notices.length ? `, the latest ${s.notices.length} of ${formatNumber(s.noticeCount)}` : ''}. Each links to its own page and to the notice at TED.
          </p>
        </div>
        <Card>
          <DataTable label="Result notices of this supplier" minWidth={760}>
            <caption className="sr-only">Result notices naming {s.name} a winner</caption>
            <thead>
              <tr>
                <th scope="col" className="min-w-56">Notice</th>
                <th scope="col" className="min-w-40">Buyer</th>
                <th scope="col" className="whitespace-nowrap">Published</th>
                <th scope="col">CPV</th>
                <th scope="col" className="min-w-28">Value</th>
              </tr>
            </thead>
            <tbody>
              {s.notices.map((n) => (
                <tr key={n.id}>
                  <th scope="row" className="font-normal">
                    <Link href={`/tenders/${n.slug}`} className="break-words">{n.title || n.noticeId}</Link>
                    <span className="block font-mono text-mono text-ink-muted">{n.noticeId}</span>
                  </th>
                  <td>{n.buyerName ?? 'Name withheld on request'}{n.buyerCountry ? ` (${n.buyerCountry})` : ''}</td>
                  <td className="whitespace-nowrap font-mono tabular-nums">{n.publishedAt ? formatDateUtc(n.publishedAt) : 'Not stated'}</td>
                  <td className="whitespace-nowrap font-mono tabular-nums">{n.cpv ?? 'Not stated'}</td>
                  <td className="font-mono tabular-nums">
                    {n.valueAmount !== null
                      ? `${formatNumber(n.valueAmount)} ${n.valueCurrency ?? ''}`
                      : n.winnersInNotice > 1 ? `Shared by ${n.winnersInNotice} winners` : 'Not stated'}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </Card>
      </section>
    </>
  );
}
