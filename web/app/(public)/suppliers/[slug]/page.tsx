import type { Metadata } from 'next';
import { SUSPECT_NOTE, SUSPECT_VALUE_MAX, VALUE_KIND_LABEL } from '@/lib/value-totals';
import Link from 'next/link';
import { notFound, permanentRedirect } from 'next/navigation';
import { getSupplier, isSupplierSlug, REMOVED, whenRemoved } from '@/lib/api';
import { RemovedOnRequest } from '@/components/dg/removed';
import { countryName, cpvDivisionLabel } from '@/lib/taxonomy';
import { displayName } from '@/lib/display-name';
import { PLACSP_CODES, sourceLabel } from '@/lib/supplier-sources';
import { AboutData } from '@/components/dg/about-data';
import type { Supplier } from '@/lib/types';
import { formatDateUtc, formatNumber } from '@/lib/format';
import { buildMetadata } from '@/lib/seo';
import { PageHeader } from '@/components/dg/page-header';
import { Card } from '@/components/dg/card';
import { AutoGrid } from '@/components/dg/auto-grid';
import { DataTable } from '@/components/dg/data-table';
import { FactsGrid } from '@/components/dg/facts-grid';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { ValueTotalsBlock } from '@/components/dg/value-totals';

export const revalidate = 300;
type Props = { params: Promise<{ slug: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> };

/** WP-89: the codes and countries the supplier report's link carries (`cpv`, `buyerCountry`), read as plain text and checked by the API. */
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v)?.slice(0, 200);

/** Whether this profile shows anything from PLACSP (WP-61): a notice from it, or a TED notice it also published. */
function fromPlacsp(s: Supplier): boolean {
  return s.notices.some((n) => PLACSP_CODES.includes(n.source ?? '') || (n.alsoPublished ?? []).some((r) => PLACSP_CODES.includes(r.source ?? '')));
}


export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const got = await getSupplier(slug).catch(whenRemoved);
  if (got === REMOVED) return { title: 'Removed on request', robots: { index: false } };
  if (!got) return { title: 'Supplier not found', robots: { index: false } };
  const s = { ...got, name: displayName(got.name, 'title') };
  return buildMetadata({
    title: s.name,
    description: `${s.name} (${s.country}): ${s.noticeCount} defence-relevant contracts of the last three years in ${fromPlacsp(s) ? 'TED and PLACSP' : 'TED'} result notices naming it as a winner. The open segment of the market only.`,
    path: `/suppliers/${s.slug}`,
    noindex: false,
  });
}

export default async function SupplierPage({ params, searchParams }: Props) {
  const { slug } = await params;
  if (!isSupplierSlug(slug)) notFound();
  const sp = await searchParams;
  const under = { cpv: one(sp.cpv), buyerCountry: one(sp.buyerCountry) };
  // an unreadable code list is the API's 422: the page then shows the total alone
  const got = await (under.cpv ? getSupplier(slug, under).catch(() => getSupplier(slug)) : getSupplier(slug)).catch(whenRemoved);
  if (got === REMOVED) return <RemovedOnRequest what="supplier" />;
  if (!got) notFound();
  const s = { ...got, name: displayName(got.name, 'title') };      // the case of the name is for the eye; the stored name is not changed
  if (s.slug !== slug && isSupplierSlug(s.slug)) permanentRedirect(`/suppliers/${s.slug}`);
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', href: '/' }, { label: 'Suppliers', href: '/suppliers' }, { label: s.name, href: `/suppliers/${s.slug}` }]} title={s.name}>
        <FactsGrid>
          <FactCell label="Country"><CountryLabel code={s.country} className="font-sans" /></FactCell>
          <FactCell label="Contracts won, last three years">
            <span className="tabular-nums">{formatNumber(s.noticeCount)}</span>
            {s.underCodes && (
              <span className="block font-sans text-small font-normal text-ink-muted" data-under-codes>
                {formatNumber(s.underCodes.contracts)} of them under your CPV codes{s.underCodes.buyerCountries.length ? `, in ${s.underCodes.buyerCountries.map(countryName).join(', ')}` : ''}, as in your supplier report
              </span>
            )}
          </FactCell>
          <FactCell label="Years">
            <span className="tabular-nums">{s.firstYear ? (s.firstYear === s.lastYear ? s.firstYear : `${s.firstYear} to ${s.lastYear}`) : 'Not stated'}</span>
          </FactCell>
          {s.identifiers.length > 0 && <FactCell label="Registration number as published">{s.identifiers.join(', ')}</FactCell>}
        </FactsGrid>
        {s.namesAsStated.length > 1 && (
          <p className="m-0 max-w-prose text-small text-ink-muted">Also published as: {s.namesAsStated.slice(1).join('; ')}.</p>
        )}
        {/* WP-88: one line; the coverage, the method and the removal route are in About this data. */}
        {/* WP-90: the open segment said where it cannot be missed, in one line; the coverage and the method stay in About this data */}
        <p className="m-0 max-w-prose rounded-md border-l-4 border-ink bg-surface-inset px-4 py-2.5 text-body font-semibold" data-open-segment>
          Open segment only: {fromPlacsp(s) ? 'TED and Spain’s PLACSP' : 'TED'} award notices of the last three years; the company&rsquo;s real volume is larger.
        </p>
        <p className="m-0 max-w-prose text-small text-ink-muted" data-attribution>{s.attribution}</p>
        <AboutData>
        <p className="m-0">
          This is what buyers published in TED result notices{fromPlacsp(s) ? " and in the award results of Spain's national procurement portal (PLACSP); an award published in both is counted once and listed under one of them," : ''} of the defence-relevant scope, published in the last three years:
          the same contracts the supplier report counts in “who to approach”. A contract published in several notices is counted once. TED holds only part of European defence
          spending (about a tenth, by a 2025 ECIPE brief we have not re-checked), so a company can have won far more than is shown here. There is no ranking and no share; a value appears only on a notice that names one
          winner, and Contract values sums those values per currency. To ask for a removal, see the <Link href="/privacy" className="font-semibold">privacy notice</Link>.
        </p>
        </AboutData>
        {s.values && (
          <ValueTotalsBlock
            values={s.values}
            noun="contract"
            scope={`All ${formatNumber(s.noticeCount)} contracts it won, not only the ones listed below: ${fromPlacsp(s) ? 'TED result notices and award results of Spain’s national portal' : 'TED result notices'} of the defence-relevant scope, published in the last three years.`}
          />
        )}
      </PageHeader>

      <AutoGrid min={380}>
        <Card title="Contracts per year" id="by-year" className="self-start">
          <DataTable label={`Contracts won by ${s.name}, per year of publication of the newest notice`} minWidth={240}>
            <thead><tr><th scope="col">Year</th><th scope="col" className="text-right">Contracts</th></tr></thead>
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
          <DataTable label={`Contracts won by ${s.name}, per main CPV division`} minWidth={280}>
            <thead><tr><th scope="col">Main CPV division</th><th scope="col" className="text-right">Contracts</th></tr></thead>
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
              <tr><th scope="col" className="min-w-52">Buyer</th><th scope="col">Country</th><th scope="col" className="text-right">Contracts</th></tr>
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
            Newest first{s.noticeCount > s.notices.length ? `, the latest ${s.notices.length} notices of its ${formatNumber(s.noticeCount)} contracts` : ''}. Each links to its own page{fromPlacsp(s) ? ', and names its source: TED or the Spanish portal' : ' and to the notice at TED'}.
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
                    <span className="block font-mono text-mono text-ink-muted">{fromPlacsp(s) ? `${sourceLabel(n.source)} ` : ''}{n.noticeId}</span>
                    {(n.alsoPublished ?? []).length > 0 && (
                      <span className="block text-small text-ink-muted">
                        Also published in {(n.alsoPublished ?? []).map((r, i) => (
                          <span key={`${r.source}-${r.noticeId}`}>
                            {i > 0 ? ', ' : ''}{sourceLabel(r.source)}{' '}
                            {r.sourceUrl ? <a href={r.sourceUrl} rel="noopener" className="font-mono">{r.noticeId}</a> : <span className="font-mono">{r.noticeId}</span>}
                          </span>
                        ))} (counted once)
                      </span>
                    )}
                    {n.framework && (
                      <span className="block text-small text-ink-muted" data-framework>
                        Call-off under the framework agreement{' '}
                        {n.framework.slug
                          ? <Link href={`/tenders/${n.framework.slug}`} className="font-mono">{n.framework.noticeId}</Link>
                          : <span className="font-mono">{n.framework.noticeId}</span>}
                      </span>
                    )}
                  </th>
                  <td>{n.buyerName ?? 'Name withheld on request'}{n.buyerCountry ? ` (${n.buyerCountry})` : ''}</td>
                  <td className="whitespace-nowrap font-mono tabular-nums">{n.publishedAt ? formatDateUtc(n.publishedAt) : 'Not stated'}</td>
                  <td className="whitespace-nowrap font-mono tabular-nums">{n.cpv ?? 'Not stated'}</td>
                  <td className="font-mono tabular-nums">
                    {n.valueAmount !== null
                      ? <>{`${formatNumber(n.valueAmount)} ${n.valueCurrency ?? ''}`}{(n.valueSuspect ?? n.valueAmount < SUSPECT_VALUE_MAX)
                        && <span className="block font-sans text-small text-ink-muted" data-value-suspect>{SUSPECT_NOTE}</span>}
                        {/* WP-95: a ceiling or an estimate says so, and is not in the sum */}
                        {n.valueKind && n.valueKind !== 'contract'
                          && <span className="block font-sans text-small text-ink-muted" data-value-kind={n.valueKind}>{VALUE_KIND_LABEL[n.valueKind]}, not in the sum</span>}</>
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
