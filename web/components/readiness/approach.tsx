'use client';

import Link from 'next/link';
import { approachOthersLine, primesOf, type ApproachWinner, type Demand } from '@/lib/demand';
import { formatDateUtc } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { countryName } from '@/lib/taxonomy';
import { Button } from '@/components/dg/button';
import { Tag } from '@/components/dg/tag';
import { ValueTotalsBlock } from '@/components/dg/value-totals';
import { ErrorState, Skeleton } from '@/components/dg/feedback';
import type { DemandState } from './use-readiness';

type Result = DemandState & { retry: () => void };

export const INDRA_SOURCE = 'https://www.eldiario.es/motor/sector_y_mercado/fabricar-coches-componentes-vehiculos-militares-indra-busca-proveedores-automocion_1_13308288.html';

/** Why this list comes first: the honest explainer of WP-80. */
export function ApproachExplainer() {
  return (
    <div className="flex max-w-prose flex-col gap-2 text-body" data-approach-explainer>
      <p className="m-0">
        Automotive suppliers usually enter defence as subcontractors: they sell to the prime contractors and their large suppliers, not to a ministry.
        In Spain, Indra opened a supplier selection for automotive firms in 2026 for its military vehicle programmes (
        <a href={INDRA_SOURCE} target="_blank" rel="noopener noreferrer">elDiario.es, 16 June 2026</a>).
      </p>
      <p className="m-0">
        Public notices miss most of that work: what a prime buys from its own suppliers is not published. The list below shows who won the published
        defence-scope contracts under your CPV codes; a company marked as a prime contractor or large defence group is one to offer your work to as a
        subcontractor; the others supply the buyers directly.
      </p>
    </div>
  );
}

function Winner({ w, scope }: { w: ApproachWinner; scope: string }) {
  const src = w.prime ? safeHttpUrl(w.prime.sourceUrl) : null;
  return (
    <li className="report-item flex flex-col gap-1.5 border-t border-line py-3 first:border-t-0" data-approach-winner={w.prime ? 'prime' : 'other'}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-body font-semibold">{w.slug ? <Link href={`/suppliers/${w.slug}`}>{w.name}</Link> : w.name}</span>
        {w.country && <span className="text-small text-ink-muted">({countryName(w.country)})</span>}
        {w.prime && <Tag wrap>{w.prime.jointVenture ? `Joint venture with ${w.prime.group}` : `Prime or large defence group: ${w.prime.group}`}</Tag>}
        {w.edfProjects > 0 && <Tag>{`EDF projects: ${w.edfProjects}`}</Tag>}
        {w.defenceBuyer && <Tag>Also a defence buyer</Tag>}
      </div>
      <p className="m-0 text-small" data-approach-facts>
        {w.contracts} {w.contracts === 1 ? 'contract' : 'contracts'} won in {w.countries.map(countryName).join(', ')}
        {w.lastAward ? `; latest notice published ${formatDateUtc(w.lastAward)}` : ''}.
      </p>
      {w.buyers.length > 0 && (
        <p className="m-0 text-small text-ink-muted">
          Wins most from:{' '}
          {w.buyers.map((b, i) => (
            <span key={b.slug}>{i > 0 && '; '}<Link href={`/buyers/${b.slug}`}>{b.name}</Link> ({b.contracts})</span>
          ))}
        </p>
      )}
      {w.values && <ValueTotalsBlock values={w.values} noun="contract" scope={scope} />}
      {w.prime && <p className="m-0 text-small text-ink-muted">Listed by name from: {src ? <a href={src} target="_blank" rel="noopener noreferrer">{w.prime.source}</a> : w.prime.source}.</p>}
    </li>
  );
}

/** WP-81: what the sums under each winner cover, the list's own period, countries and sources. */
function valueScope(d: Demand): string {
  return `The contracts of this list: ${formatDateUtc(d.since)} to ${formatDateUtc(d.until)}, in ${d.countries.map(countryName).join(', ')}, from ${d.sources.some((s) => s.code.startsWith('es_placsp')) ? 'TED and PLACSP' : 'TED'}.`;
}

/** The full "who to approach" section of the report. */
export function ApproachMap({ result, hasCodes }: { result: Result; hasCodes: boolean }) {
  if (!hasCodes) {
    return (
      <div className="flex flex-col gap-3">
        <ApproachExplainer />
        <p className="m-0 text-body">Choose the CPV codes of what you make on your supplier profile, and this section lists the companies that win those contracts.</p>
        <div><Button href="/readiness/supplier" variant="secondary">Add CPV codes to my supplier profile</Button></div>
      </div>
    );
  }
  if (result.state === 'idle' || result.state === 'loading') return <div role="status" aria-label="Finding who wins these contracts"><Skeleton className="h-40" /></div>;
  if (result.state === 'error') return <ErrorState title="The list could not be computed" onRetry={result.retry}>{result.message}</ErrorState>;
  const d = result.data;
  const a = d.approach;
  const primes = primesOf(a);
  const others = approachOthersLine(a, d.kMin);
  return (
    <div className="flex flex-col gap-4" data-approach>
      <ApproachExplainer />
      <p className="m-0 max-w-prose text-body" data-approach-summary>
        From {formatDateUtc(d.since)} to {formatDateUtc(d.until)}, in {d.countries.map(countryName).join(', ')}: {d.total.winners}{' '}
        {d.total.winners === 1 ? 'company' : 'companies'} won defence-scope procurements under your codes. {a.winners.length === 0
          ? (d.kMin > 1 ? `None won ${d.kMin} or more, so none is named.` : 'None is named.')
          : d.kMin > 1
            ? `${a.winners.length} won ${d.kMin} or more and ${a.winners.length === 1 ? 'is' : 'are'} named below, most contracts first.`
            : `${a.winners.length} ${a.winners.length === 1 ? 'is' : 'are'} named below, most contracts first. A winner who is a natural person is never named.`}
      </p>
      <div className="flex flex-col gap-1" data-approach-primes>
        <h3 className="m-0 text-h4">Prime contractors and large defence groups among them</h3>
        {primes.length === 0 ? (
          <p className="m-0 max-w-prose text-body">
            None of the named winners is on our list of prime contractors and large defence groups (the European companies of the SIPRI Top 100 of
            2024, and Indra). Primes may still buy what you make from their own suppliers; that is not published.
          </p>
        ) : (
          <ul className="m-0 flex list-none flex-col p-0">{primes.map((w, i) => <Winner key={`p-${i}-${w.name}`} w={w} scope={valueScope(d)} />)}</ul>
        )}
      </div>
      {a.winners.length > primes.length && (
        <div className="flex flex-col gap-1">
          <h3 className="m-0 text-h4">{primes.length ? 'The other named winners' : 'The named winners'}</h3>
          <ul className="m-0 flex list-none flex-col p-0">{a.winners.filter((w) => !w.prime).map((w, i) => <Winner key={`${i}-${w.name}`} w={w} scope={valueScope(d)} />)}</ul>
        </div>
      )}
      {others && <p className="m-0 max-w-prose text-small text-ink-muted" data-approach-others>{others}</p>}
      <p className="m-0 max-w-prose text-small text-ink-muted">
        A contract here is a procurement with a published winner, counted once however many notices publish it. Under each company, Contract values sums the values of its contracts per currency. The
        latest notice is the newest publication among them: for Spain’s national portal (PLACSP) the date the procurement was published, since its
        award date is not stored. Marked by name: a group member that carries the group’s name; a subsidiary under another name is not marked.
      </p>
      <p className="m-0 max-w-prose text-small text-ink-muted">{d.winnersFrom} {d.coverage}</p>
    </div>
  );
}

/** The short version, first on the results page: the primes, then the first named winners, and the way to the report. */
export function ApproachSummary({ result }: { result: Result }) {
  if (result.state === 'idle') return null;
  return (
    <section aria-labelledby="approach" className="flex flex-col gap-3" data-approach-summary-section>
      <h2 id="approach" className="m-0 text-h2">Who to approach</h2>
      <ApproachExplainer />
      {result.state === 'loading' && <div role="status" aria-label="Finding who wins these contracts"><Skeleton className="h-40" /></div>}
      {result.state === 'error' && <ErrorState title="The list could not be computed" onRetry={result.retry}>{result.message}</ErrorState>}
      {result.state === 'done' && <ShortList d={result.data} />}
    </section>
  );
}

function ShortList({ d }: { d: Demand }) {
  const primes = primesOf(d.approach);
  const first = [...primes, ...d.approach.winners.filter((w) => !w.prime)].slice(0, 8);
  return (
    <>
      {first.length === 0 ? (
        <p className="m-0 max-w-prose text-body">{d.kMin > 1
          ? `No company won ${d.kMin} or more defence-scope procurements under your codes in the last three years, so none is named.`
          : 'No company won a defence-scope procurement under your codes in the last three years.'}</p>
      ) : (
        <ul className="m-0 flex list-none flex-col p-0">{first.map((w, i) => <Winner key={`${i}-${w.name}`} w={w} scope={valueScope(d)} />)}</ul>
      )}
      <div><Button href="/readiness/supplier/report#r-approach" variant="secondary">Every named winner in your supplier report</Button></div>
    </>
  );
}
