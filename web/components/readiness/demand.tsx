'use client';

import Link from 'next/link';
import { cpvDictionaryTitle } from '@/lib/cpv';
import { allWinnersLabel, buyerLine, directiveShare, otherWinnersLine, winnersHref, type Demand, type DemandCountry, type DemandRef } from '@/lib/demand';
import { formatDateUtc } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { countryName } from '@/lib/taxonomy';
import { Button } from '@/components/dg/button';
import { DataTable } from '@/components/dg/data-table';
import { ErrorState, Skeleton } from '@/components/dg/feedback';
import { useCpvVocabulary, type DemandState } from './use-readiness';
import { AboutData } from '@/components/dg/about-data';

export type DemandResult = DemandState & { retry: () => void };

/** A notice: its page here and, for paper, its address at the source (the report's print rules print it after the link). */
function Ref({ r }: { r: DemandRef }) {
  const url = r.sourceUrl ? safeHttpUrl(r.sourceUrl) : null;
  return (
    <li className="report-item flex flex-col gap-0.5 border-t border-line py-2 first:border-t-0" data-demand-notice={r.id}>
      <Link href={`/tenders/${r.slug}`} className="font-semibold">{r.title || r.noticeId}</Link>
      <span className="text-small text-ink-muted">
        {[r.buyerName, r.publishedAt ? formatDateUtc(r.publishedAt) : null, r.noticeId, r.directive ? 'Directive 2009/81/EC' : null].filter(Boolean).join(' · ')}
        {url && <> · <a href={url} target="_blank" rel="noopener noreferrer">At the source</a></>}
      </span>
    </li>
  );
}

function Country({ c, kMin }: { c: DemandCountry; kMin: number }) {
  const others = otherWinnersLine(c, kMin);
  return (
    <section aria-labelledby={`d-${c.country}`} className="report-row flex flex-col gap-3 border-t border-line pt-4" data-demand-country={c.country}>
      <h3 id={`d-${c.country}`} className="m-0 text-h3">{countryName(c.country)}</h3>
      {c.procurements === 0 ? (
        <p className="m-0 text-body">No defence-scope notice with these codes in the last three years.</p>
      ) : (
        <>
          <p className="m-0 max-w-prose text-body" data-demand-summary>
            {c.procurements} {c.procurements === 1 ? 'procurement' : 'procurements'} by {buyerLine(c)}; under Directive 2009/81/EC:{' '}
            {directiveShare(c)}; with a published winner: {c.awarded}.
          </p>
          {c.topBuyers.length > 0 && (
            <div className="flex flex-col gap-1">
              <h4 className="m-0 text-body font-bold">Buyers with the most procurements</h4>
              <ol className="m-0 flex list-decimal flex-col gap-1 pl-6 text-body">
                {c.topBuyers.map((b) => (
                  <li key={b.slug} data-demand-buyer={b.core ? 'core' : 'other'}>
                    <Link href={`/buyers/${b.slug}`}>{b.name}</Link>{' '}
                    <span className="text-small text-ink-muted">({b.core ? 'core defence buyer' : 'other defence-scope buyer'}, {b.procurements})</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
          <div className="flex flex-col gap-1">
            <h4 className="m-0 text-body font-bold">Who won</h4>
            {c.winners === 0 ? <p className="m-0 text-body">No winner is published for these procurements in the sources we read.</p> : (
              <>
                {c.topWinners.length > 0 && (
                  <ul className="m-0 flex list-none flex-col gap-2 p-0">
                    {c.topWinners.map((w, i) => (
                      <li key={`${i}-${w.name}`}className="report-item flex flex-col gap-1" data-demand-winner>
                        <span className="text-body"><strong>{w.name}</strong> ({countryName(w.country)}), {w.awards} awards</span>
                        <ul className="m-0 flex list-none flex-col p-0">{w.notices.map((r) => <Ref key={r.id} r={r} />)}</ul>
                      </li>
                    ))}
                  </ul>
                )}
                {others && <p className="m-0 max-w-prose text-small text-ink-muted" data-demand-others>{others}</p>}
                {c.otherWinners.winners > 0 && (
                  <p className="m-0 text-small" data-demand-all>
                    <a href={winnersHref(c.country)} className="font-semibold">{allWinnersLabel(c.winners, countryName(c.country))}</a>
                  </p>
                )}
              </>
            )}
          </div>
          {c.latest.length > 0 && (
            <div className="flex flex-col gap-1">
              <h4 className="m-0 text-body font-bold">Newest procurements</h4>
              <ul className="m-0 flex list-none flex-col p-0">{c.latest.map((r) => <Ref key={r.id} r={r} />)}</ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function Coverage({ d }: { d: Demand }) {
  return <AboutData summary="How we count"><p className="m-0" data-demand-coverage>{d.coverage}</p></AboutData>;
}

/** The whole map, for the printable report. `result`: the one demand request of the page (WP-80: "who to approach" reads it too). */
export function DemandMap({ result }: { result: DemandResult }) {
  const vocab = useCpvVocabulary();
  if (result.state === 'idle' || result.state === 'loading') return <div role="status" aria-label="Computing the demand map"><Skeleton className="h-40" /></div>;
  if (result.state === 'error') return <ErrorState title="The demand map could not be computed" onRetry={result.retry}>{result.message}</ErrorState>;
  const d = result.data;
  return (
    <div className="flex flex-col gap-4" data-demand>
      <p className="m-0 max-w-prose text-body">
        Defence-scope notices from {formatDateUtc(d.since)} to {formatDateUtc(d.until)} with a code under one of your CPV codes, in{' '}
        {d.countries.map(countryName).join(', ')}: {d.total.procurements} procurements by {buyerLine(d.total)}; under Directive 2009/81/EC:{' '}
        {directiveShare(d.total)}.
      </p>
      <Coverage d={d} />
      <ul className="m-0 flex list-none flex-col gap-1 p-0 text-small">
        {d.codes.map((c) => (
          <li key={c.code} data-demand-code={c.code}><span className="font-mono">{c.code}</span> {vocab?.get(c.code) ?? cpvDictionaryTitle(c.code) ?? ''}: {c.procurements}</li>
        ))}
      </ul>
      {d.byCountry.map((c) => <Country key={c.country} c={c} kMin={d.kMin} />)}
      <AboutData summary="Sources and what the counts mean">
        <p className="m-0">{d.winnersFrom} {d.notice}</p>
        <p className="m-0">{d.sources.map((s) => s.attribution).join(' ')}</p>
      </AboutData>
    </div>
  );
}

/** The short version for the results page: one row per country, the coverage line, and the way to the full map. */
export function DemandSummary({ result }: { result: DemandResult }) {
  if (result.state === 'idle') return null;
  return (
    <section aria-labelledby="demand" className="flex flex-col gap-3" data-demand-summary-section>
      <h2 id="demand" className="m-0 text-h2">Who buys what you make</h2>
      {result.state === 'loading' && <div role="status" aria-label="Computing the demand map"><Skeleton className="h-40" /></div>}
      {result.state === 'error' && <ErrorState title="The demand map could not be computed" onRetry={result.retry}>{result.message}</ErrorState>}
      {result.state === 'done' && (
        <>
          <p className="m-0 max-w-prose text-body">
            Defence-scope procurements with a code under your {result.data.codes.length} CPV {result.data.codes.length === 1 ? 'code' : 'codes'} in
            the last three years, by country.
          </p>
          <DataTable label="Who buys what you make, by country" minWidth={520}>
            <thead>
              <tr><th scope="col">Country</th><th scope="col">Procurements</th><th scope="col">Under Directive 2009/81/EC</th><th scope="col">Buyers (core / other)</th><th scope="col">With a published winner</th></tr>
            </thead>
            <tbody>
              {result.data.byCountry.map((c) => (
                <tr key={c.country} data-demand-row={c.country}>
                  <th scope="row" className="font-semibold">{countryName(c.country)}</th>
                  <td>{c.procurements}</td>
                  <td>{directiveShare(c)}</td>
                  <td>{c.coreBuyers} / {c.otherBuyers}</td>
                  <td>{c.awarded}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
          <Coverage d={result.data} />
          <div><Button href="/readiness/supplier/report#r-demand" variant="secondary">Buyers and notices in your supplier report</Button></div>
        </>
      )}
    </section>
  );
}
