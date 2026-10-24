import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';
import { ApiError, getSuppliers, getSupplierSummary } from '@/lib/api';
import { CURRENCIES, countryName, cpvDivisionLabel } from '@/lib/taxonomy';
import { formatDateTimeUtc, formatDateUtc, formatNumber, plural } from '@/lib/format';
import { staleNote } from '@/lib/source-status';
import { MAX_PAGE, ignoredFilters, lastPage, type SearchParams } from '@/lib/filters';
import { FilterNotices } from '@/components/dg/filter-notices';
import { MIN_LIST_ITEMS, buildMetadata, listViewTitle } from '@/lib/seo';
import { cpvForWords } from '@/lib/cpv';
import { parseCountries } from '@/lib/country-input';
import { displayName } from '@/lib/display-name';
import { coverageText, placspCredit, placspNote } from '@/lib/supplier-sources';
import { groupValueLine, listValueLine } from '@/lib/value-totals';
import { CoverageNote } from '@/components/dg/coverage-note';
import type { SupplierSort } from '@/lib/types';
import { EmptyState } from '@/components/dg/feedback';
import { PageHeader } from '@/components/dg/page-header';
import { CompaniesTabs, companyCrumbs } from '@/components/dg/companies-tabs';
import { Pagination } from '@/components/dg/pagination';
import { Button } from '@/components/dg/button';
import { CountryLabel } from '@/components/dg/data-display';
import { Card } from '@/components/dg/card';
import { AboutData } from '@/components/dg/about-data';
import { AutoGrid } from '@/components/dg/auto-grid';
import { DataTable } from '@/components/dg/data-table';
import { boxCls } from '@/components/dg/field';
import { ListboxSelect } from '@/components/dg/select';
import { LiveListScope, ResultsRegion } from '@/components/dg/live-list';
import { LiveForm } from '@/components/funding/filter-panel';
import { cn } from '@/lib/utils';

export const revalidate = 300;

type Props = { searchParams: Promise<SearchParams> };

const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? '';

function parse(sp: SearchParams) {
  const q = first(sp.q).slice(0, 100).trim();
  // A code, a three-letter code or an English name, as typed (lib/country-input.ts reads it); the API is asked with the codes.
  const country = first(sp.country).replace(/[^\p{L}\p{M}\s,.'’&-]/gu, '').replace(/\s+/g, ' ').trim().slice(0, 60);
  // WP-85: the buyer's country (the notice's), as the supplier report's countries; `country` stays the supplier's
  const buyerCountry = first(sp.buyerCountry).replace(/[^\p{L}\p{M}\s,.'’&-]/gu, '').replace(/\s+/g, ' ').trim().slice(0, 60);
  const cpv = first(sp.cpv).replace(/[^0-9,]/g, '').slice(0, 40);
  const product = first(sp.product).replace(/[^\p{L}\p{N}\s-]/gu, ' ').replace(/\s+/g, ' ').trim().slice(0, 60);
  // WP-98b: or the contract values in one currency, largest first
  const asked = first(sp.sort);
  const sort: SupplierSort = asked === 'name' ? 'name' : VALUE_SORTS.some((o) => o.value === asked) ? (asked as SupplierSort) : 'awards';
  // WP-98b (p07): TED's winners only, so countries can be compared on one source
  const source = first(sp.source) === 'ted' ? ('ted' as const) : undefined;
  const n = Number(first(sp.page));
  const page = Number.isFinite(n) && n >= 1 ? Math.min(Math.floor(n), MAX_PAGE) : 1;
  // WP-96: a curated company group (`/suppliers?group=rheinmetall`), its key as the API knows it
  const group = first(sp.group).toLowerCase().replace(/[^a-z]/g, '').slice(0, 40);
  return { q, country, buyerCountry, cpv, product, sort, source, page, group };
}

function href(f: ReturnType<typeof parse>, page: number): string {
  const p = new URLSearchParams();
  if (f.q) p.set('q', f.q);
  if (f.country) p.set('country', f.country);
  if (f.buyerCountry) p.set('buyerCountry', f.buyerCountry);
  if (f.cpv) p.set('cpv', f.cpv);
  if (f.product) p.set('product', f.product);
  if (f.group) p.set('group', f.group);
  if (f.source) p.set('source', f.source);
  if (f.sort !== 'awards') p.set('sort', f.sort);
  if (page > 1) p.set('page', String(page));
  return `/suppliers${p.size ? `?${p.toString()}` : ''}`;
}

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parse(await searchParams);
  let noindex = Boolean(f.q || f.country || f.buyerCountry || f.cpv || f.product || f.group || f.source || f.page > 1 || f.sort !== 'awards');
  if (!noindex) {
    try { noindex = (await getSuppliers(withProduct(f).api)).items.length < MIN_LIST_ITEMS; } catch { noindex = true; }
  }
  return buildMetadata({
    title: listViewTitle('Defence supplier map', 'Supplier map', {
      page: f.page, countries: parseCountries(f.country).codes, q: f.q, filters: [f.q, f.country, f.buyerCountry, f.cpv, f.product].filter(Boolean).length,
    }),
    description: 'Companies named as winners in TED result notices of defence-relevant contracts of the last three years: where they are, what they won and who bought it. The open segment only.',
    path: '/suppliers',
    noindex,
  });
}

/**
 * The filters as the API takes them. A product word is turned into CPV prefixes from the finder's vocabulary and replaces the CPV
 * codes typed; a product that matches no code gives no prefixes and an empty answer, never the unfiltered list.
 */
function withProduct(f: ReturnType<typeof parse>) {
  const match = f.product ? cpvForWords(f.product) : null;
  // A product word takes the place of the typed codes (the page says so): an intersection of two lists of prefixes is not what anyone means.
  const cpv = match ? match.prefixes.join(',') : f.cpv;
  // A country that is none of the three forms is an answer ("not a country"), never a 404 page and never the unfiltered list.
  const { codes, unknown: u1 } = parseCountries(f.country);
  const { codes: buyerCodes, unknown: u2 } = parseCountries(f.buyerCountry);
  const unknown = [...u1, ...u2];
  return { match, unknown, none: (match !== null && match.prefixes.length === 0) || unknown.length > 0, api: { ...f, cpv, country: codes.join(','), buyerCountry: buyerCodes.join(',') } };
}

const INPUT = 'min-h-11 rounded-md border border-input-edge bg-surface px-3 font-normal';
/** WP-98b: one order per currency the site shows amounts in; a sum in one currency is never set against another's. */
const VALUE_SORTS = CURRENCIES.map((c) => ({ value: `value-${c}`, label: `Contract values in ${c}, largest first` }));

export default async function SuppliersPage({ searchParams }: Props) {
  const sp = await searchParams;
  const f = parse(sp);
  const notices = ignoredFilters(sp, 'suppliers');
  const filtered = Boolean(f.q || f.country || f.buyerCountry || f.cpv || f.product || f.group || f.source);
  const { match, unknown, none, api } = withProduct(f);
  let result;
  let full;
  try {
    // The summary is asked on every page (cached): which sources the map holds decides what the coverage card says.
    [result, full] = await Promise.all([
      none ? Promise.resolve({ items: [], total: 0, page: 1, pageSize: 20 } as unknown as Awaited<ReturnType<typeof getSuppliers>>) : getSuppliers(api),
      getSupplierSummary(),
    ]);
  } catch (e) {
    // The list serves only its first positions (`maxOffset`): a page past them goes to the last page it serves, as the other lists
    // clamp (QA m-9).
    if (e instanceof ApiError && e.status === 422) {
      // a refusal of page 1 as well is not about the page: then the answer stays "not there"
      const head = none ? null : await getSuppliers({ ...api, page: 1 }).catch(() => null);
      if (!none && !head) notFound();
      redirect(href(f, head ? lastPage(Math.min(head.total, head.maxOffset ?? head.total), head.pageSize) : 1));
    }
    throw e;
  }
  const summary = f.page === 1 && !filtered ? full : null;
  const placsp = placspNote(full?.sources);
  const reachable = Math.min(result.total, result.maxOffset ?? result.total);
  const last = lastPage(reachable, result.pageSize);
  if (result.total > 0 && f.page > last) redirect(href(f, last));
  return (
    <>
      {/* WP-86: the Won contracts tab of Companies; what the map covers and does not is the card under it. */}
      <PageHeader crumbs={companyCrumbs('suppliers')} title="Companies"><CompaniesTabs current="suppliers" /></PageHeader>
      {result.staleAsOf && <p role="status" className="m-0 max-w-prose rounded-md bg-surface-inset px-4 py-3 text-small text-ink">{staleNote(result.staleAsOf, formatDateTimeUtc)}</p>}
      <FilterNotices notices={notices} />

      {/* WP-88: what the map covers, its counts, sources and licences are one collapsed block; the page opens with the list. */}
      <AboutData summary="How we count">
        <p className="m-0" id="coverage">{coverageText(Boolean(placsp))}</p>
        {summary && (
          <p className="m-0">
            {formatNumber(summary.suppliers)} {plural(summary.suppliers, 'supplier')} and {formatNumber(summary.awards)} {plural(summary.awards, 'win')} in {formatNumber(summary.noticesWithSupplier)} {plural(summary.noticesWithSupplier, 'contract')}
            {summary.firstPublished && summary.lastPublished ? `, published ${formatDateUtc(summary.firstPublished)} to ${formatDateUtc(summary.lastPublished)} UTC` : ''}.
            {' '}{formatNumber(summary.skippedNaturalPersons)} {summary.skippedNaturalPersons === 1 ? 'winner that is a natural person (a sole trader under their own name) is' : 'winners that are natural persons (sole traders under their own name) are'} left out.
          </p>
        )}
        <p className="m-0">
          Counts of suppliers and wins, every group shown however small. Winners that are natural persons are counted, never named. A supplier's wins
          are a count of contracts, each with its notice and link; its contract values are the sums of the values of the notices that name it alone, per currency.
          The list is ordered by value only when you choose it.
          A contract is in every CPV division its notice has a code in, so the divisions add up to more than the total.
        </p>
        <p className="m-0">Names are as the buyer published them (<Link href="/methodology" className="font-semibold">methodology</Link>).</p>
      </AboutData>
      <LiveListScope>
      <section aria-labelledby="results-heading" className="flex flex-col gap-4">
        <h2 id="results-heading" className="m-0 text-h2">
          {result.total === 0 ? 'No suppliers' : `Suppliers (${formatNumber(result.total)})`}
        </h2>
        {/* WP-98c: a value order read from the stored sums that an award load has overtaken says so */}
        {result.valuesBehind && result.valuesAsOf && (
          <p className="m-0 max-w-prose text-small text-ink-muted" data-values-behind>
            Ordered by the contract values as summed on {formatDateTimeUtc(result.valuesAsOf)}; contracts read since then join the order at the next
            update (each company&rsquo;s own values below are current).
          </p>
        )}
        {f.group && (
          <p role="status" className="m-0 max-w-prose rounded-md bg-surface-inset px-4 py-3 text-small" data-group-view>
            The companies of a curated company group (a parent and its subsidiaries, from the source named on each company&rsquo;s page). Each
            is a company of its own with its own contracts; nothing is merged across them. <Link href="/suppliers" className="font-semibold">Show every supplier</Link>
          </p>
        )}
        {f.group && groupValueLine(result.groupTotals) && (
          <p className="m-0 max-w-prose text-small text-ink" data-group-total>{groupValueLine(result.groupTotals)}</p>
        )}
        <LiveForm defaults={{ sort: 'awards' }}>
        <form method="get" action="/suppliers" role="search" aria-label="Find suppliers" className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-small font-semibold">Company name
            <input name="q" defaultValue={f.q} maxLength={100} className={INPUT} />
          </label>
          <label className="flex flex-col gap-1 text-small font-semibold">Supplier's country, for example DE
            <input name="country" defaultValue={f.country} maxLength={20} className={`${INPUT} w-40`} />
          </label>
          <label className="flex flex-col gap-1 text-small font-semibold">Buyer's country, for example ES
            <input name="buyerCountry" defaultValue={f.buyerCountry} maxLength={20} className={`${INPUT} w-40`} aria-describedby="country-help" />
          </label>
          <label className="flex flex-col gap-1 text-small font-semibold">Product, for example ammunition
            <input name="product" defaultValue={f.product} maxLength={60} className={`${INPUT} w-48`} aria-describedby="product-help" />
          </label>
          <label className="flex flex-col gap-1 text-small font-semibold">CPV code, for example 35
            <input name="cpv" defaultValue={f.cpv} maxLength={40} className={`${INPUT} w-40`} />
          </label>
          <label className="flex flex-col gap-1 text-small font-semibold">Order
            <span className={cn(boxCls(), 'relative text-small font-normal')}>
              <ListboxSelect name="sort" defaultValue={f.sort} aria-describedby="order-help" accessibleName="Order"
                className="text-small font-normal"
                options={[{ value: 'awards', label: 'Most wins first' }, { value: 'name', label: 'Name, A to Z' }, ...VALUE_SORTS]} />
            </span>
          </label>
          {(placsp || f.source) && (
            <label className="flex flex-col gap-1 text-small font-semibold">Sources
              <span className={cn(boxCls(), 'relative text-small font-normal')}>
                <ListboxSelect name="source" defaultValue={f.source ?? ''} aria-describedby="source-help" accessibleName="Sources"
                  className="text-small font-normal"
                  options={[{ value: '', label: 'TED and PLACSP' }, { value: 'ted', label: 'TED only (compare countries)' }]} />
              </span>
            </label>
          )}
          <Button type="submit" variant="primary">Search</Button>
          {filtered && <Button variant="secondary" href="/suppliers">Clear</Button>}
        </form>
        </LiveForm>
        <AboutData summary="How the search works">
          <p id="product-help" className="m-0">
            A product word is read as CPV codes, from a short list of words for the main defence products (drone, explosives, body armour, tank, and a few more)
            and otherwise from the titles of the codes in the <Link href="/cpv" className="font-semibold">CPV finder</Link>; suppliers are
            listed that won notices with any CPV code starting with one of them. The page shows the codes it used. Not sure of the word? Browse the finder and copy a code into the CPV box.
          </p>
          <p id="country-help" className="m-0">
            The supplier's country is where the winner is registered, as the notice states it. The buyer's country is the country of the
            buyer that awarded the contract: the countries of the supplier report. With the report's CPV codes and countries the list gives
            each company the number of contracts “who to approach” gives it.
          </p>
          <p id="order-help" className="m-0">
            “Most wins first” is the number of wins in the notices we hold, nothing more: a count, not a ranking of size, quality or standing, and a small
            reseller with many small awards can come first. Choose “Name” for a neutral order. “Contract values in EUR” orders by the sum of the contract
            values the notices state for the company alone, in that currency only (nothing is converted; a company with none in it comes last): many
            contracts state no value, so it is not a ranking of size either.
          </p>
          <p id="source-help" className="m-0">
            Spain&rsquo;s national award results (PLACSP) are read and no other country&rsquo;s, so Spanish winners fill the list. “TED only” lists the winners of TED&rsquo;s
            result notices alone, the one source every country has, for a comparison between countries.
          </p>
        </AboutData>
        {match && (
          <p role="status" className="m-0 max-w-prose rounded-md bg-surface-inset px-4 py-3 text-small">
            {match.prefixes.length === 0
              ? <>No code in the CPV finder has “{f.product}” in its title. Try a shorter or more general word, or browse the <Link href="/cpv" className="font-semibold">CPV finder</Link>.</>
              : match.via === 'keyword'
                ? <>“{f.product}” is read as {match.codes.map((c) => `${c.code} ${c.title}`).join('; ')} (our list of product words, with the codes and titles of the CPV vocabulary).
                  {' '}Filtering by the prefixes {match.prefixes.join(', ')}{match.truncated ? ` (the first ${match.prefixes.length})` : ''}.
                  {match.note ? ` ${match.note}` : ''}
                  {f.cpv ? ' The CPV box is ignored while a product is given.' : ''}</>
                : <>“{f.product}” matches {match.matched} {match.matched === 1 ? 'code' : 'codes'} of the finder, for example {match.codes.slice(0, 3).map((c) => `${c.code} ${c.title}`).join('; ')}.
                {' '}Filtering by the prefixes {match.prefixes.join(', ')}{match.truncated ? ` (the first ${match.prefixes.length}; use a narrower word for the rest)` : ''}.
                {f.cpv ? ' The CPV box is ignored while a product is given.' : ''}</>}
          </p>
        )}
        {/* WP-98b: whose award results are read for the countries asked (the buyer's, else the supplier's), above an empty list too */}
        <CoverageNote countries={(api.buyerCountry || api.country).split(',').filter(Boolean)} kind="awards" />
        {placsp && !f.source && (api.buyerCountry || api.country) && (
          <p className="m-0 max-w-prose text-small text-ink-muted" data-ted-only-link>
            Comparing countries? <Link href={href({ ...f, source: 'ted' }, 1)} className="font-semibold">Show TED&rsquo;s winners only</Link>, the one source every country has.
          </p>
        )}
        <ResultsRegion className="flex flex-col gap-4">
        {result.total === 0 ? (
          <EmptyState title={unknown.length > 0 ? 'Not a country' : 'No suppliers match'} action={<Button variant="secondary" href="/suppliers">Clear filters</Button>}>
            {unknown.length > 0
              ? `“${unknown.join(', ')}” is not a country code or an English country name. Use a code such as DE or DEU, or a name such as Germany.`
              : `Only companies named as winners in a TED result notice${placsp && !f.source ? ' or an award result of Spain’s national procurement portal' : ''} of the defence-relevant scope, published in the last three years, are listed. Try a shorter name.`}
          </EmptyState>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {result.items.map((s) => (
              <li key={s.id} className="flex flex-col gap-1 rounded-lg border border-transparent bg-surface p-4">
                <Link href={`/suppliers/${s.slug}`} className="inline-flex min-h-8 items-center break-words text-h3 font-semibold">{displayName(s.name, 'title')}</Link>
                <span className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-small text-ink-muted">
                  <CountryLabel code={s.country} />
                  <span>
                    {formatNumber(s.awardCount)} {s.awardCount === 1 ? 'win' : 'wins'}
                    {s.firstYear ? `, ${s.firstYear === s.lastYear ? s.firstYear : `${s.firstYear} to ${s.lastYear}`}` : ''}
                  </span>
                  {s.cpvDivisions.length > 0 && <span>CPV {s.cpvDivisions.join(', ')}</span>}
                </span>
                {/* WP-98b: the contract values of these wins (WP-95: contract values only), per currency */}
                {s.contractValues && <span className="text-small text-ink" data-contract-values>{listValueLine(s.contractValues, s.awardCount)}</span>}
              </li>
            ))}
          </ul>
        )}
        {result.maxOffset !== undefined && result.total > result.maxOffset && (
          <p className="m-0 max-w-prose text-small text-ink-muted">
            The list shows the first {formatNumber(result.maxOffset)} of {formatNumber(result.total)}. Search by company name, or narrow by country or product group, to reach the others.
          </p>
        )}
        <Pagination page={result.page} total={reachable} pageSize={result.pageSize} hrefFor={(p) => href(f, p)} />
        {/* WP-88: the attribution the sources' terms ask for stays on screen, never only in a collapsed block. */}
        <p className="m-0 max-w-prose text-small text-ink-muted" data-attribution>Source: TED, © European Union.{placsp ? ` ${placspCredit(placsp, formatDateUtc)}` : ''}</p>
        </ResultsRegion>
      </section>
      </LiveListScope>
      {summary && summary.byCpv.length > 0 && (
        <section aria-labelledby="aggregate" className="flex flex-col gap-4">
          <h2 id="aggregate" className="m-0 text-h2">By product group and country</h2>
          <AutoGrid min={420}>
            <Card title="By CPV division" headingLevel="h3" className="self-start">
              <DataTable label="Suppliers and wins per CPV division" minWidth={380}>
                <thead>
                  <tr>
                    <th scope="col">Product group</th>
                    <th scope="col" className="text-right">Suppliers</th>
                    <th scope="col" className="text-right">Wins</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.byCpv.map((g) => (
                    <tr key={g.key}>
                      <th scope="row" className="min-w-44 font-normal">
                        <Link href={`/suppliers?cpv=${g.key}`}>{g.key} {cpvDivisionLabel(g.key) ?? ''}</Link>
                      </th>
                      <td className="text-right font-mono tabular-nums">{formatNumber(g.suppliers)}</td>
                      <td className="text-right font-mono tabular-nums">{formatNumber(g.awards)}</td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            </Card>
            <Card title="By country of the supplier" headingLevel="h3" className="self-start">
              <DataTable label="Suppliers and wins per country of the supplier" minWidth={380}>
                <thead>
                  <tr>
                    <th scope="col">Country</th>
                    <th scope="col" className="text-right">Suppliers</th>
                    <th scope="col" className="text-right">Wins</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.byCountry.map((g) => (
                    <tr key={g.key}>
                      <th scope="row" className="min-w-44 font-normal"><Link href={`/suppliers?country=${g.key}`}>{countryName(g.key)}</Link></th>
                      <td className="text-right font-mono tabular-nums">{formatNumber(g.suppliers)}</td>
                      <td className="text-right font-mono tabular-nums">{formatNumber(g.awards)}</td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            </Card>
          </AutoGrid>
        </section>
      )}

    </>
  );
}
