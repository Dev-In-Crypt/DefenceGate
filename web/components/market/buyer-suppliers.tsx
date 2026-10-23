import Link from 'next/link';
import { displayName } from '@/lib/display-name';
import { formatNumber, plural } from '@/lib/format';
import type { BuyerSuppliers } from '@/lib/types';
import { AboutData } from '@/components/dg/about-data';
import { CountryLabel } from '@/components/dg/data-display';
import { DataTable } from '@/components/dg/data-table';

/**
 * WP-90: who won this buyer's contracts, from the supplier map's award set (GET /v1/buyers/{slug}/suppliers): one sentence, the
 * table, the method collapsed (WP-88), the attribution on screen. Natural persons are never named (the API leaves them out).
 */
export function BuyerTopSuppliers({ data, name }: { data: BuyerSuppliers; name: string }) {
  return (
    <section aria-labelledby="top-suppliers" className="flex flex-col gap-3" data-top-suppliers>
      <h2 id="top-suppliers" className="m-0 text-h2">Top suppliers of this buyer</h2>
      <p className="m-0 max-w-prose text-body">
        {formatNumber(data.suppliers)} {plural(data.suppliers, 'company', 'companies')} won {name}&rsquo;s {formatNumber(data.contracts)} {plural(data.contracts, 'contract')} in
        published award notices of the last three years{data.items.length < data.suppliers ? `; the ${data.items.length} with the most` : ''}.
      </p>
      <DataTable label={`Top suppliers of ${name}`} minWidth={320}>
        <thead><tr><th scope="col">Supplier</th><th scope="col">Country</th><th scope="col" className="text-right">Contracts</th></tr></thead>
        <tbody>
          {data.items.map((s) => (
            <tr key={s.slug}>
              <th scope="row" className="font-normal"><Link href={`/suppliers/${s.slug}`} className="font-semibold">{displayName(s.name, 'title')}</Link></th>
              <td>{s.country ? <CountryLabel code={s.country} /> : 'Not stated'}</td>
              <td className="text-right font-mono tabular-nums">{formatNumber(s.awards)}</td>
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
      </AboutData>
    </section>
  );
}
