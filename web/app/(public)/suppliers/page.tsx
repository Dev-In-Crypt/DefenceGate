import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';
import { ApiError, getSuppliers, getSupplierSummary } from '@/lib/api';
import { countryName, cpvDivisionLabel } from '@/lib/taxonomy';
import { formatDateUtc, formatNumber } from '@/lib/format';
import { MAX_PAGE, lastPage, type SearchParams } from '@/lib/filters';
import { MIN_LIST_ITEMS, buildMetadata } from '@/lib/seo';
import { cpvForWords } from '@/lib/cpv';
import { Breadcrumbs, EmptyState } from '@/components/dg/feedback';
import { Pagination } from '@/components/dg/pagination';
import { Button } from '@/components/dg/button';
import { CountryLabel } from '@/components/dg/data-display';
import { ScrollBox } from '@/components/dg/scroll-box';

export const revalidate = 300;

type Props = { searchParams: Promise<SearchParams> };

const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? '';

function parse(sp: SearchParams) {
  const q = first(sp.q).slice(0, 100).trim();
  const country = first(sp.country).toUpperCase().replace(/[^A-Z,]/g, '').slice(0, 20);
  const cpv = first(sp.cpv).replace(/[^0-9,]/g, '').slice(0, 40);
  const product = first(sp.product).replace(/[^\p{L}\p{N}\s-]/gu, ' ').replace(/\s+/g, ' ').trim().slice(0, 60);
  const sort = first(sp.sort) === 'name' ? ('name' as const) : ('awards' as const);
  const n = Number(first(sp.page));
  const page = Number.isFinite(n) && n >= 1 ? Math.min(Math.floor(n), MAX_PAGE) : 1;
  return { q, country, cpv, product, sort, page };
}

function href(f: ReturnType<typeof parse>, page: number): string {
  const p = new URLSearchParams();
  if (f.q) p.set('q', f.q);
  if (f.country) p.set('country', f.country);
  if (f.cpv) p.set('cpv', f.cpv);
  if (f.product) p.set('product', f.product);
  if (f.sort !== 'awards') p.set('sort', f.sort);
  if (page > 1) p.set('page', String(page));
  return `/suppliers${p.size ? `?${p.toString()}` : ''}`;
}

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parse(await searchParams);
  let noindex = Boolean(f.q || f.country || f.cpv || f.product || f.page > 1 || f.sort !== 'awards');
  if (!noindex) {
    try { noindex = (await getSuppliers(withProduct(f).api)).items.length < MIN_LIST_ITEMS; } catch { noindex = true; }
  }
  return buildMetadata({
    title: 'Defence supplier map',
    description: 'Companies named as winners in TED result notices of defence-relevant contracts since 2023: where they are, what they won and who bought it. The open segment only.',
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
  return { match, none: match !== null && match.prefixes.length === 0, api: { ...f, cpv } };
}

const CARD = 'flex min-w-0 flex-col gap-3 rounded-lg bg-surface p-5 sm:p-6';
const INPUT = 'min-h-11 rounded-md border border-line bg-surface px-3 font-normal';

export default async function SuppliersPage({ searchParams }: Props) {
  const f = parse(await searchParams);
  const filtered = Boolean(f.q || f.country || f.cpv || f.product);
  const { match, none, api } = withProduct(f);
  let result;
  let summary;
  try {
    [result, summary] = await Promise.all([
      none ? Promise.resolve({ items: [], total: 0, page: 1, pageSize: 20 } as unknown as Awaited<ReturnType<typeof getSuppliers>>) : getSuppliers(api),
      f.page === 1 && !filtered ? getSupplierSummary() : Promise.resolve(null),
    ]);
  } catch (e) {
    // The list serves only its first positions (`maxOffset`): a page past them is not there, which is an answer, not a fault.
    if (e instanceof ApiError && e.status === 422) notFound();
    throw e;
  }
  const reachable = Math.min(result.total, result.maxOffset ?? result.total);
  const last = lastPage(reachable, result.pageSize);
  if (result.total > 0 && f.page > last) redirect(href(f, last));
  return (
    <>
      <Breadcrumbs items={[{ label: 'Home', href: '/' }, { label: 'Suppliers', href: '/suppliers' }]} />
      <header className="flex flex-col gap-3">
        <h1 className="m-0 text-[32px] font-extrabold leading-10 tracking-[-1px] md:text-h1">Defence supplier map</h1>
        <p className="m-0 max-w-[62ch] text-body text-ink-muted">
          Which companies have won defence-relevant contracts that a buyer published in TED, where they are and how often.
          This is the open segment of the market, not all of it.
        </p>
      </header>

      <section aria-labelledby="coverage" className={`${CARD} max-w-[75ch]`}>
        <h2 id="coverage" className="m-0 text-h3">What this map covers</h2>
        <p className="m-0 text-body">
          The winners named in TED result notices that our archive holds in the defence-relevant scope, from 2023. TED holds only part of
          European defence spending (a 2025 ECIPE policy brief puts it at about a tenth; we have not re-checked that figure), and contracts awarded outside it are not here, so a company missing from this map may win many.
          Before eForms became mandatory (25 October 2023) notices state no winner as data, so 2023 is thin.
        </p>
        {summary && (
          <p className="m-0 text-small text-ink-muted">
            {formatNumber(summary.suppliers)} suppliers and {formatNumber(summary.awards)} wins in {formatNumber(summary.noticesWithSupplier)} notices
            {summary.firstPublished && summary.lastPublished ? `, published ${formatDateUtc(summary.firstPublished)} to ${formatDateUtc(summary.lastPublished)} UTC` : ''}.
            {' '}{formatNumber(summary.skippedNaturalPersons)} winners that are natural persons (sole traders under their own name) are left out.
            Source: TED, © European Union. Names are as the buyer published them (<Link href="/methodology" className="font-semibold">methodology</Link>).
          </p>
        )}
      </section>

      {summary && summary.byCpv.length > 0 && (
        <section aria-labelledby="aggregate" className="flex flex-col gap-4">
          <h2 id="aggregate" className="m-0 text-h2">By product group and country</h2>
          <p className="m-0 max-w-[75ch] text-small text-ink-muted">
            Counts of suppliers and wins. A group of fewer than {summary.kMin} suppliers is not shown ({formatNumber(summary.suppressedGroups)} groups are
            held back), so that no figure describes one company, and the same holds for a list narrowed by country or product group. The map states no contract value per supplier and ranks nobody by value; a supplier's wins are a count of notices, each with its link.
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className={CARD}>
              <ScrollBox label="By CPV division">
                <table className="w-full border-collapse text-left text-small">
                  <caption className="mb-2 text-left text-h3">By CPV division</caption>
                  <thead>
                    <tr className="border-b border-line">
                      <th scope="col" className="py-1 pr-4 font-semibold">Product group</th>
                      <th scope="col" className="py-1 pr-4 text-right font-semibold">Suppliers</th>
                      <th scope="col" className="py-1 text-right font-semibold">Wins</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.byCpv.map((g) => (
                      <tr key={g.key} className="border-b border-line last:border-0">
                        <th scope="row" className="py-1 pr-4 font-normal">
                          <Link href={`/suppliers?cpv=${g.key}`}>{g.key} {cpvDivisionLabel(g.key) ?? ''}</Link>
                        </th>
                        <td className="py-1 pr-4 text-right font-mono tabular-nums">{formatNumber(g.suppliers)}</td>
                        <td className="py-1 text-right font-mono tabular-nums">{formatNumber(g.awards)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </ScrollBox>
            </div>
            <div className={CARD}>
              <ScrollBox label="By country of the supplier">
                <table className="w-full border-collapse text-left text-small">
                  <caption className="mb-2 text-left text-h3">By country of the supplier</caption>
                  <thead>
                    <tr className="border-b border-line">
                      <th scope="col" className="py-1 pr-4 font-semibold">Country</th>
                      <th scope="col" className="py-1 pr-4 text-right font-semibold">Suppliers</th>
                      <th scope="col" className="py-1 text-right font-semibold">Wins</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.byCountry.map((g) => (
                      <tr key={g.key} className="border-b border-line last:border-0">
                        <th scope="row" className="py-1 pr-4 font-normal"><Link href={`/suppliers?country=${g.key}`}>{countryName(g.key)}</Link></th>
                        <td className="py-1 pr-4 text-right font-mono tabular-nums">{formatNumber(g.suppliers)}</td>
                        <td className="py-1 text-right font-mono tabular-nums">{formatNumber(g.awards)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </ScrollBox>
            </div>
          </div>
        </section>
      )}

      <section aria-labelledby="results-heading" className="flex flex-col gap-4">
        <h2 id="results-heading" className="m-0 text-h2">
          {result.total === 0 ? 'No suppliers' : `Suppliers (${formatNumber(result.total)})`}
        </h2>
        <form method="get" action="/suppliers" role="search" aria-label="Find suppliers" className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-small font-semibold">Company name
            <input name="q" defaultValue={f.q} maxLength={100} className={INPUT} />
          </label>
          <label className="flex flex-col gap-1 text-small font-semibold">Country code, for example DE
            <input name="country" defaultValue={f.country} maxLength={20} className={`${INPUT} w-40`} />
          </label>
          <label className="flex flex-col gap-1 text-small font-semibold">Product, for example ammunition
            <input name="product" defaultValue={f.product} maxLength={60} className={`${INPUT} w-48`} aria-describedby="product-help" />
          </label>
          <label className="flex flex-col gap-1 text-small font-semibold">CPV code, for example 35
            <input name="cpv" defaultValue={f.cpv} maxLength={40} className={`${INPUT} w-40`} />
          </label>
          <label className="flex flex-col gap-1 text-small font-semibold">Order
            <select name="sort" defaultValue={f.sort} className={INPUT} aria-describedby="order-help">
              <option value="awards">Most wins first</option>
              <option value="name">Name, A to Z</option>
            </select>
          </label>
          <Button type="submit" variant="primary">Search</Button>
          {filtered && <Button variant="secondary" href="/suppliers">Clear</Button>}
        </form>
        <p id="product-help" className="m-0 max-w-[75ch] text-small text-ink-muted">
          A product word is read as CPV codes, from a short list of words for the main defence products (drone, explosives, body armour, tank, and a few more)
          and otherwise from the titles of the codes in the <Link href="/cpv" className="font-semibold">CPV finder</Link>; suppliers are
          listed that won notices whose main CPV code starts with one of them. The page shows the codes it used. Not sure of the word? Browse the finder and copy a code into the CPV box.
        </p>
        <p id="order-help" className="m-0 max-w-[75ch] text-small text-ink-muted">
          “Most wins first” is the number of wins in the notices we hold, nothing more: a count, not a ranking of size, quality or standing, and a small
          reseller with many small awards can come first. Choose “Name” for a neutral order.
        </p>
        {match && (
          <p role="status" className="m-0 max-w-[75ch] rounded-md bg-surface-inset px-4 py-3 text-small">
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
        {result.total === 0 ? (
          <EmptyState title={result.withheld ? 'This group is too small to list' : 'No suppliers match'} action={<Button variant="secondary" href="/suppliers">Clear filters</Button>}>
            {result.withheld
              ? `A country or product group with fewer than ${summary?.kMin ?? 3} suppliers is not listed, so that nothing describes one or two companies. Widen the filter, or search by company name without it.`
              : 'Only companies named as winners in a TED result notice of the defence-relevant scope are listed. Try a shorter name.'}
          </EmptyState>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {result.items.map((s) => (
              <li key={s.id} className="flex flex-col gap-1 rounded-lg bg-surface p-4">
                <Link href={`/suppliers/${s.slug}`} className="break-words text-h3 font-semibold">{s.name}</Link>
                <span className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-small text-ink-muted">
                  <CountryLabel code={s.country} />
                  <span>
                    {formatNumber(s.awardCount)} {s.awardCount === 1 ? 'win' : 'wins'}
                    {s.firstYear ? `, ${s.firstYear === s.lastYear ? s.firstYear : `${s.firstYear} to ${s.lastYear}`}` : ''}
                  </span>
                  {s.cpvDivisions.length > 0 && <span>CPV {s.cpvDivisions.join(', ')}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
        {result.maxOffset !== undefined && result.total > result.maxOffset && (
          <p className="m-0 max-w-[75ch] text-small text-ink-muted">
            The list shows the first {formatNumber(result.maxOffset)} of {formatNumber(result.total)}. Search by company name, or narrow by country or product group, to reach the others.
          </p>
        )}
        <Pagination page={result.page} total={reachable} pageSize={result.pageSize} hrefFor={(p) => href(f, p)} />
      </section>
    </>
  );
}
