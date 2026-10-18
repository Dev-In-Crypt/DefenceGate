import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, permanentRedirect } from 'next/navigation';
import { getSupplier, isSupplierSlug, REMOVED, whenRemoved } from '@/lib/api';
import { RemovedOnRequest } from '@/components/dg/removed';
import { cpvDivisionLabel } from '@/lib/taxonomy';
import { formatDateUtc, formatNumber } from '@/lib/format';
import { buildMetadata } from '@/lib/seo';
import { Breadcrumbs } from '@/components/dg/feedback';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { ScrollBox } from '@/components/dg/scroll-box';

export const revalidate = 300;
type Props = { params: Promise<{ slug: string }> };

const CARD = 'flex min-w-0 flex-col gap-3 rounded-lg border border-edge bg-surface p-5 sm:p-6';
const TH = 'py-1 pr-4 font-semibold';

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
      <Breadcrumbs items={[{ label: 'Home', href: '/' }, { label: 'Suppliers', href: '/suppliers' }, { label: s.name, href: `/suppliers/${s.slug}` }]} />
      <header className="flex flex-col gap-4">
        <h1 className="m-0 break-words page-title">{s.name}</h1>
        <dl className="facts-grid m-0 border-b border-line">
          <FactCell label="Country"><CountryLabel code={s.country} className="font-sans" /></FactCell>
          <FactCell label="Notices naming it a winner"><span className="tabular-nums">{formatNumber(s.noticeCount)}</span></FactCell>
          <FactCell label="Years">
            <span className="tabular-nums">{s.firstYear ? (s.firstYear === s.lastYear ? s.firstYear : `${s.firstYear} to ${s.lastYear}`) : 'Not stated'}</span>
          </FactCell>
          {s.identifiers.length > 0 && <FactCell label="Registration number as published">{s.identifiers.join(', ')}</FactCell>}
        </dl>
        {s.namesAsStated.length > 1 && (
          <p className="m-0 text-small text-ink-muted">Also published as: {s.namesAsStated.slice(1).join('; ')}.</p>
        )}
        <p className="m-0 max-w-prose text-small text-ink-muted">
          This is what buyers published in TED result notices of the defence-relevant scope, from 2023. TED holds only part of European defence
          spending (about a tenth, by a 2025 ECIPE brief we have not re-checked), so a company can have won far more than is shown here. There is no ranking, no share and no contract total: a value appears only on a notice
          that names one winner. {s.attribution} To ask for a removal, see the <Link href="/privacy" className="font-semibold">privacy notice</Link>.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-labelledby="by-year" className={CARD}>
          <h2 id="by-year" className="m-0 text-h3">Notices per year</h2>
          <table className="w-full min-w-[420px] border-collapse text-left text-small">
            <caption className="sr-only">Notices naming {s.name} a winner, per year of publication</caption>
            <thead><tr className="border-b border-line"><th scope="col" className={TH}>Year</th><th scope="col" className="py-2 text-right font-semibold">Notices</th></tr></thead>
            <tbody>
              {s.byYear.map((y) => (
                <tr key={y.year} className="border-b border-line last:border-0">
                  <th scope="row" className="py-2 pr-4 font-normal">{y.year}</th>
                  <td className="py-2 text-right font-mono tabular-nums">{formatNumber(y.awards)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section aria-labelledby="by-cpv" className={CARD}>
          <h2 id="by-cpv" className="m-0 text-h3">Product groups</h2>
          <table className="w-full min-w-[420px] border-collapse text-left text-small">
            <caption className="sr-only">Notices naming {s.name} a winner, per CPV division</caption>
            <thead><tr className="border-b border-line"><th scope="col" className={TH}>CPV division</th><th scope="col" className="py-2 text-right font-semibold">Notices</th></tr></thead>
            <tbody>
              {s.byCpv.map((c) => (
                <tr key={c.division} className="border-b border-line last:border-0">
                  <th scope="row" className="py-2 pr-4 font-normal">{c.division} {cpvDivisionLabel(c.division) ?? ''}</th>
                  <td className="py-2 text-right font-mono tabular-nums">{formatNumber(c.awards)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      {s.buyers.length > 0 && (
        <section aria-labelledby="buyers" className={CARD}>
          <h2 id="buyers" className="m-0 text-h3">Buyers</h2>
          <ul className="m-0 flex list-none flex-col gap-1 p-0 text-body">
            {s.buyers.map((b) => (
              <li key={b.slug}>
                <Link href={`/buyers/${b.slug}`} className="break-words">{b.name}</Link>
                {b.country ? ` (${b.country})` : ''}, {formatNumber(b.awards)} {b.awards === 1 ? 'notice' : 'notices'}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="notices" className="flex flex-col gap-3">
        <h2 id="notices" className="m-0 text-h2">The notices</h2>
        <p className="m-0 max-w-prose text-small text-ink-muted">
          Newest first{s.noticeCount > s.notices.length ? `, the latest ${s.notices.length} of ${formatNumber(s.noticeCount)}` : ''}. Each links to its own page and to the notice at TED.
        </p>
        <ScrollBox label="Result notices of this supplier">
          <table className="w-full min-w-[420px] border-collapse text-left text-small">
            <caption className="sr-only">Result notices naming {s.name} a winner</caption>
            <thead>
              <tr className="border-b border-line">
                <th scope="col" className={TH}>Notice</th>
                <th scope="col" className={TH}>Buyer</th>
                <th scope="col" className={TH}>Published</th>
                <th scope="col" className={TH}>CPV</th>
                <th scope="col" className="py-2 font-semibold">Value</th>
              </tr>
            </thead>
            <tbody>
              {s.notices.map((n) => (
                <tr key={n.id} className="border-b border-line align-top last:border-0">
                  <th scope="row" className="py-2 pr-4 font-normal">
                    <Link href={`/tenders/${n.slug}`} className="break-words">{n.title || n.noticeId}</Link>
                    <span className="block font-mono text-mono text-ink-muted">{n.noticeId}</span>
                  </th>
                  <td className="py-2 pr-4">{n.buyerName ?? 'Name withheld on request'}{n.buyerCountry ? ` (${n.buyerCountry})` : ''}</td>
                  <td className="py-2 pr-4 font-mono tabular-nums">{n.publishedAt ? formatDateUtc(n.publishedAt) : 'Not stated'}</td>
                  <td className="py-2 pr-4 font-mono tabular-nums">{n.cpv ?? 'Not stated'}</td>
                  <td className="py-2 font-mono tabular-nums">
                    {n.valueAmount !== null
                      ? `${formatNumber(n.valueAmount)} ${n.valueCurrency ?? ''}`
                      : n.winnersInNotice > 1 ? `Shared by ${n.winnersInNotice} winners` : 'Not stated'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollBox>
      </section>
    </>
  );
}
