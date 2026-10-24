import Link from 'next/link';
import { displayName } from '@/lib/display-name';
import { formatNumber, plural } from '@/lib/format';
import { moneyLine } from '@/lib/market-money';
import { restNote } from '@/lib/value-totals';
import type { BuyerSuppliers } from '@/lib/types';
import { AboutData } from '@/components/dg/about-data';
import { CountryLabel } from '@/components/dg/data-display';
import { DataTable } from '@/components/dg/data-table';

/**
 * WP-90: who won this buyer's contracts, from the supplier map's award set (GET /v1/buyers/{slug}/suppliers): one sentence, the
 * table, the method collapsed (WP-88), the attribution on screen. Natural persons are never named (the API leaves them out).
 * WP-105 (persona round of 24 October 2026, p01, p03, p06): under the page's CPV filter, with each supplier's contract values and their
 * sum, and a sentence that adds up ("19 companies won 19 contracts" beside 3, 3, 2, 2, 2: a contract in lots has several winners).
 */
export function BuyerTopSuppliers({ data, name, cpv }: { data: BuyerSuppliers; name: string; cpv?: string[] | null }) {
  const under = data.cpv?.length ? data.cpv : cpv ?? [];
  const total = moneyLine(data.contractValues);
  const pairs = data.awardsWithSupplier ?? 0;
  return (
    <section aria-labelledby="top-suppliers" className="flex flex-col gap-3" data-top-suppliers data-top-suppliers-cpv={under.join(',') || undefined}>
      <h2 id="top-suppliers" className="m-0 text-h2">{under.length ? `Top suppliers of this buyer under ${under.join(', ')}` : 'Top suppliers of this buyer'}</h2>
      <p className="m-0 max-w-prose text-body" data-top-suppliers-summary>
        {formatNumber(data.contracts)} {plural(data.contracts, 'contract')} of {name}{under.length ? ` with a code under ${under.join(', ')}` : ''} in
        published award notices of the last three years {data.contracts === 1 ? 'names' : 'name'} {formatNumber(data.suppliers)} {plural(data.suppliers, 'company', 'companies')} as {data.suppliers === 1 ? 'winner' : 'winners'}
        {pairs > data.contracts ? `; a contract split into lots or shared counts for each of its winners, so the companies’ counts add up to ${formatNumber(pairs)}` : ''}
        {data.items.length < data.suppliers ? `. The ${data.items.length} with the most contracts:` : '.'}
      </p>
      {total && (
        <p className="m-0 max-w-prose text-body" data-top-suppliers-total>
          <strong>Contract values awarded:</strong> {total}{typeof data.valued === 'number' && pairs > 0 ? ` (${formatNumber(data.valued)} of ${formatNumber(pairs)} contracts and winners state a contract value)` : ''}.
        </p>
      )}
      <DataTable label={`Top suppliers of ${name}`} minWidth={420}>
        <thead><tr><th scope="col">Supplier</th><th scope="col">Country</th><th scope="col" className="text-right">Contracts</th><th scope="col">Contract values</th></tr></thead>
        <tbody>
          {data.items.map((s) => (
            <tr key={s.slug}>
              <th scope="row" className="font-normal"><Link href={`/suppliers/${s.slug}`} className="font-semibold">{displayName(s.name, 'title')}</Link></th>
              <td>{s.country ? <CountryLabel code={s.country} /> : 'Not stated'}</td>
              <td className="text-right font-mono tabular-nums">{formatNumber(s.awards)}</td>
              <td className="text-small" data-top-supplier-value>{/* WP-112 (p06: Seko Benelux "EUR 24.3 M over 2 contracts" of 3): the cell accounts for every contract */}
                {moneyLine(s.contractValues)
                  ? `${moneyLine(s.contractValues)}${restNote((s.contractValues ?? []).reduce((k, v) => k + v.count, 0), s.awards)}`
                  : 'None stated (a framework ceiling or an estimate is not added)'}</td>
            </tr>
          ))}
        </tbody>
      </DataTable>
      <p className="m-0 max-w-prose text-small text-ink-muted" data-attribution>{data.attribution}</p>
      <AboutData summary="How we count">
        <p className="m-0">
          The same contracts the supplier map counts: winners a buyer named in a result notice of the defence-relevant scope, published in the last three
          years, under every name of this buyer. A contract published in several notices counts once; a company&rsquo;s count here is of this buyer only.
          Winners that are natural persons are never named. It is the open segment of the market: contracts awarded without a published notice are not here.
        </p>
        <p className="m-0">
          Contract values are summed as on each supplier&rsquo;s page: per currency, never converted, each contract once, only a value the notice gives
          to that one winner; framework ceilings, estimates and unit prices are never added.
        </p>
      </AboutData>
    </section>
  );
}
