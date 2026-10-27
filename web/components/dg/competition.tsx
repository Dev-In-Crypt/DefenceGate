import Link from 'next/link';
import type { CompetitionShare, SupplierCompetition } from '@/lib/types';
import { classLabel, countShare, sizeLine, valueShare } from '@/lib/competition';
import { displayName } from '@/lib/display-name';
import { formatNumber, plural } from '@/lib/format';
import { countryName } from '@/lib/taxonomy';
import { cpvGroupTitle, cpvTitle } from '@/lib/cpv';
import { AutoGrid } from './auto-grid';
import { NoteLine } from './blocks';
import { Card } from './card';
import { DataTable } from './data-table';

/**
 * WP-152: a company's competitor intelligence (backend/dgate/competition.py) on its supplier page and in its company report. Server
 * components. A CPV class is named by the selection's title of its code, else by its group's (`classLabel`).
 */
const cls = (k: string) => classLabel(k, cpvTitle, cpvGroupTitle);

export function CompetitorsCard({ c, name, action }: { c: SupplierCompetition; name: string; action?: React.ReactNode }) {
  return (
    <Card title="Competitors" id="competitors" action={action}>
      {c.competitors.length === 0 ? (
        <p className="m-0 text-body">No other company won a contract of the same buyer under the same CPV class in these three years.</p>
      ) : (
        <DataTable label={`Companies that won contracts of the same buyers under the same CPV classes as ${name}`} minWidth={620}>
          <thead>
            <tr>
              <th scope="col" className="min-w-52">Company</th>
              <th scope="col">Country</th>
              <th scope="col" className="text-right">Its contracts in shared markets</th>
              <th scope="col" className="text-right">Shared markets</th>
              <th scope="col" className="text-right">{name}&rsquo;s contracts there</th>
            </tr>
          </thead>
          <tbody>
            {c.competitors.map((r) => (
              <tr key={r.slug} data-competitor>
                <th scope="row" className="font-normal">
                  <Link href={`/suppliers/${r.slug}`} className="break-words">{displayName(r.name, 'title')}</Link>
                  {r.sameName && <span className="block text-small text-ink-muted" data-same-name>Same name and country: possibly this company under another record</span>}
                  {r.sameGroup && <span className="block text-small text-ink-muted" data-same-group>Same group: {r.sameGroup}</span>}
                </th>
                <td className="whitespace-nowrap font-mono tabular-nums">{r.country ?? ''}</td>
                <td className="text-right font-mono tabular-nums">{formatNumber(r.overlap)}</td>
                <td className="whitespace-nowrap text-right font-mono tabular-nums">{formatNumber(r.markets)} <span className="font-sans text-ink-muted">({formatNumber(r.buyers)} {plural(r.buyers, 'buyer')})</span></td>
                <td className="text-right font-mono tabular-nums">{formatNumber(r.ours)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
      <NoteLine data-competitors-note>
        {c.competitorCount > c.competitors.length ? `The ${c.competitors.length} of ${formatNumber(c.competitorCount)} companies with the most contracts in shared markets. ` : ''}
        A market is one buyer and one CPV class (the first four digits of a code); {name} won contracts in {formatNumber(c.markets)}. Records are never merged: a row
        marked &ldquo;same name&rdquo; may be this company under another registration number.
      </NoteLine>
    </Card>
  );
}

function Tally({ label, head, rows }: { label: string; head: string; rows: { label: string; contracts: number }[] }) {
  return (
    <DataTable label={label} minWidth={260}>
      <thead><tr><th scope="col">{head}</th><th scope="col" className="text-right">Contracts</th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label}>
            <th scope="row" className="font-normal">{r.label}</th>
            <td className="text-right font-mono tabular-nums">{formatNumber(r.contracts)}</td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}

export function WhereItWins({ c, name }: { c: SupplierCompetition; name: string }) {
  return (
    <section aria-labelledby="where-it-wins" className="flex flex-col gap-4">
      <h2 id="where-it-wins" className="m-0 text-h2">Where it wins</h2>
      <p className="m-0 max-w-prose text-body" data-typical-size><span className="font-semibold">Typical contract value: </span>{sizeLine(c)}</p>
      <AutoGrid min={320}>
        <Card title="Buyer countries" id="by-buyer-country" className="self-start">
          <Tally label={`Contracts won by ${name}, per buyer country`} head="Buyer country"
            rows={c.byCountry.map((r) => ({ label: countryName(r.key), contracts: r.contracts }))} />
        </Card>
        <Card title="CPV classes" id="by-cpv-class" className="self-start">
          <Tally label={`Contracts won by ${name}, per CPV class`} head="CPV class"
            rows={c.byClass.map((r) => ({ label: cls(r.key), contracts: r.contracts }))} />
          <NoteLine>A contract with codes of two classes is in both.</NoteLine>
        </Card>
      </AutoGrid>
    </section>
  );
}

function ShareRows({ rows, label }: { rows: CompetitionShare[]; label: (key: string) => string }) {
  return rows.map((s) => (
    <tr key={s.key} data-share>
      <th scope="row" className="font-normal">{label(s.key)}</th>
      <td className="font-mono tabular-nums">{countShare(s)}</td>
      <td className="font-mono tabular-nums">{valueShare(s) ?? 'No value stated'}</td>
    </tr>
  ));
}

export function ShareCard({ c, name }: { c: SupplierCompetition; name: string }) {
  return (
    <Card title="Its share" id="share">
      <DataTable label={`${name}'s share of the awarded contracts, per CPV class and buyer country`} minWidth={680}>
        <thead>
          <tr>
            <th scope="col" className="min-w-52">Where</th>
            <th scope="col" className="min-w-36">Its contracts, of all</th>
            <th scope="col" className="min-w-72">Its contract value, of all stated</th>
          </tr>
        </thead>
        <tbody>
          <ShareRows rows={c.shareByClass} label={(k) => `CPV class ${cls(k)}`} />
          <ShareRows rows={c.shareByCountry} label={(k) => `Buyers in ${countryName(k)}`} />
        </tbody>
      </DataTable>
      <NoteLine data-share-note>
        Out of every contract of the same award notices as this page (the open segment: defence-relevant, last three years, legal-entity winners), each counted once
        however many companies won it. Values are contract values in the commonest currency there, never converted, and many contracts state none. Contracts awarded
        outside these sources are in neither number.
      </NoteLine>
    </Card>
  );
}
