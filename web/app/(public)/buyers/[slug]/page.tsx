import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, permanentRedirect, redirect } from 'next/navigation';
import { EndingRow } from '@/components/tenders/contract-period';
import { getBuyer, getBuyerProfile, getBuyerSuppliers, getEnding, getTenders, isBuyerSlug, PERSON, REMOVED, UNAVAILABLE, whenRemovedOrPerson } from '@/lib/api';
import { NotShownPerson, RemovedOnRequest } from '@/components/dg/removed';
import { displayName, shownVariants } from '@/lib/display-name';
import { formatDateUtc, formatNumber, plural, variantsLine } from '@/lib/format';
import { MAX_PAGE, TENDER_PAGE_SIZE, lastPage, parseTenderFilters, toTenderQuery, type SearchParams } from '@/lib/filters';
import { Select, TextInput } from '@/components/dg/form';
import { BuyerTopSuppliers } from '@/components/market/buyer-suppliers';
import { buildMetadata } from '@/lib/seo';
import { EmptyState } from '@/components/dg/feedback';
import { PageHeader } from '@/components/dg/page-header';
import { FactsGrid } from '@/components/dg/facts-grid';
import { ClassifiedNote } from '@/components/dg/basis-chips';
import { SCOPE_CHOICES } from '@/lib/taxonomy';
import { Tag } from '@/components/dg/tag';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { TenderCard } from '@/components/dg/cards';
import { Pagination } from '@/components/dg/pagination';
import { Button } from '@/components/dg/button';
import { FollowButton } from '@/components/account/save-button';
import { BuyerProfileSection } from '@/components/market/buyer-profile';
import { chosenUnit, unitName, unitOptions } from '@/lib/buyer-units';

export const revalidate = 300;
type Props = { params: Promise<{ slug: string }>; searchParams: Promise<SearchParams> };

/** Open tenders are listed in full (up to this many), then the earlier ones page by page. */
const OPEN_LIMIT = 100;
/** WP-120: without `?all=1` the page shows this many open and planned tenders, soonest deadline first, and a link to all of them
 * (round-6 audit: the Czech ministry's page was 262 KB of HTML with 100 open and 45 planned cards, p95 4.3 s for buyer pages). */
const OPEN_SHOWN = 20;
const PLANNED_SHOWN = 10;
/** WP-105: up to this many planned tenders are shown unfolded. */
const PLANNED_OPEN = 3;

function showAll(sp: SearchParams): boolean {
  return (Array.isArray(sp.all) ? sp.all[0] : sp.all) === '1';
}

function pageOf(sp: SearchParams): number {
  const raw = Array.isArray(sp.page) ? sp.page[0] : sp.page;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 1 ? Math.min(Math.floor(n), MAX_PAGE) : 1;
}

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const [{ slug }, sp] = await Promise.all([params, searchParams]);
  const buyer = await getBuyer(slug).catch(whenRemovedOrPerson);
  if (buyer === REMOVED) return { title: 'Removed on request', robots: { index: false } };
  if (buyer === PERSON) return { title: 'Name not shown', robots: { index: false } };
  if (!buyer) return { title: 'Buyer not found', robots: { index: false } };
  const name = displayName(buyer.name, 'title');
  return buildMetadata({
    title: name,
    description: buyer.scope === 'all'
      ? `${name}: ${formatNumber(buyer.tenderCount)} ${plural(buyer.tenderCount, 'notice')} outside the default scope, ${SCOPE_CHOICES.relevant.label}.`
      : `${name}: ${formatNumber(buyer.tenderCount)} defence ${plural(buyer.tenderCount, 'tender')} in the archive, ${formatNumber(buyer.openCount)} open now.`,
    path: `/buyers/${buyer.slug}`,
    // WP-144: one unit's view is not indexed (its canonical is the plain page); nor is a buyer whose notices are all outside
    // the default scope, as their notices' own pages are not (a notice page is indexed only in the core scope)
    noindex: pageOf(sp) > 1 || showAll(sp) || buyer.tenderCount === 0 || buyer.scope === 'all'
      || Boolean((Array.isArray(sp.unit) ? sp.unit[0] : sp.unit)?.trim()),
  });
}

export default async function BuyerDetailPage({ params, searchParams }: Props) {
  const [{ slug }, sp] = await Promise.all([params, searchParams]);
  if (!isBuyerSlug(slug)) notFound();
  const buyer = await getBuyer(slug).catch(whenRemovedOrPerson);
  if (buyer === REMOVED) return <RemovedOnRequest what="buyer" />;
  if (buyer === PERSON) return <NotShownPerson />;
  if (!buyer) notFound();
  if (buyer.slug !== slug && isBuyerSlug(buyer.slug)) permanentRedirect(`/buyers/${buyer.slug}`);

  const page = pageOf(sp);
  // WP-90: a CPV filter on the buyer's own tenders (the tender list's reading: any code of a notice under the prefixes); the figures above stay all of them
  const cpv = parseTenderFilters(sp).cpv;
  // WP-144: one unit of the buyer (a name its notices state), chosen from its own units; an unknown one shows them all
  const unit = chosenUnit(buyer.units, sp.unit);
  // WP-144 item 5: a buyer whose defence notices are all outside the default scope (dual-use) lists them under All notices
  const outside = buyer.scope === 'all';
  const own = { buyer: buyer.id, cpv, unit: unit?.key, ...(outside ? { scope: 'all' as const } : {}) };
  const narrowed = Boolean(cpv || unit);
  const hrefOf = (p: number) => `/buyers/${buyer.slug}${toTenderQuery({ cpv, unit: unit?.key, page: p, sort: undefined })}`;
  const all = showAll(sp);
  const allHref = (() => {
    const q = new URLSearchParams(toTenderQuery({ cpv, unit: unit?.key, sort: undefined }).replace(/^\?/, ''));
    q.set('all', '1');
    return `/buyers/${buyer.slug}?${q.toString()}`;
  })();
  const openSize = all ? OPEN_LIMIT : OPEN_SHOWN;
  const plannedSize = all ? OPEN_LIMIT : PLANNED_SHOWN;
  // Two fixed queries on the id the API gave us: open tenders first, then the history. No ordering across them is assumed.
  // All of them in the scope the counts above are in. WP-96: the tender list's default (All defence), as the counts now are:
  // the core scope left out a ministry's transport, catering and storage tenders (NL Ministry of Defence: 5 open against the
  // list's 27). The military goods and works among the open ones are counted beside "Open now".
  const [open, planned, earlier, profile, suppliers, ending] = await Promise.all([
    page === 1 && (buyer.openCount > 0 || cpv)
      ? getTenders({ ...own, status: 'open', pageSize: openSize }, { cacheable: !narrowed })
      : Promise.resolve(null),
    // A planned notice (prior information) is neither open nor closed since 19 October 2026; it is counted in "Tenders in archive".
    page === 1 ? getTenders({ ...own, status: 'planned', pageSize: plannedSize }, { cacheable: !narrowed }).catch(() => null) : Promise.resolve(null),
    getTenders({ ...own, status: 'closed', sort: 'published-desc', page, pageSize: TENDER_PAGE_SIZE }, { cacheable: page === 1 && !narrowed }),
    // The profile is an extra: a buyer page still renders when the API cannot answer it.
    page === 1 && buyer.tenderCount > 0 && !outside ? getBuyerProfile(buyer) : Promise.resolve(null),
    // WP-105: under the page's CPV filter too, with contract values
    page === 1 ? getBuyerSuppliers(buyer, cpv ?? undefined) : Promise.resolve(null),
    // WP-160: the buyer's contracts ending in the next 12 months, free in full (its first 20); an extra like the profile
    page === 1 ? getEnding({ within: 12, country: '', cpv: '', buyer: buyer.id, estimated: false }).catch(() => null) : Promise.resolve(null),
  ]);

  // A page past the last one is the last one, not an empty list.
  if (page > 1 && earlier.items.length === 0 && earlier.total > 0) {
    redirect(hrefOf(lastPage(earlier.total, earlier.pageSize)));
  }
  const name = displayName(buyer.name, 'title');
  const variants = shownVariants(buyer.variantNames ?? [], buyer.name);
  const units = buyer.units && buyer.units.length >= 2 ? buyer.units : [];

  return (
    <>
      <PageHeader
        crumbs={[
          { label: 'Home', href: '/' }, { label: 'Buyers', href: '/buyers' },
          { label: name, href: `/buyers/${buyer.slug}` },
        ]}
        eyebrow={buyer.isDefenceBuyer ? <span className="self-start"><Tag>Defence body</Tag></span> : undefined}
        title={name}
        sub={unit ? <span data-unit-shown>Unit: {unitName(unit)}</span> : undefined}
      >
        <FollowButton kind="buyer" refId={buyer.id} label="Follow this buyer" />
        <FactsGrid className="facts-grid--4">
          <FactCell label="Country">
            {buyer.country ? <CountryLabel code={buyer.country} className="font-sans" /> : <span className="font-sans">Not stated</span>}
          </FactCell>
          {/* WP-87: the profile's total when there is one (notices shown once, the unit of every figure below), so the page has one number */}
          <FactCell label="Tenders in archive"><span className="tabular-nums">{formatNumber(profile?.tenderCount ?? buyer.tenderCount)}</span></FactCell>
          <FactCell label="Open now">
            <span className="tabular-nums">{formatNumber(buyer.openCount)}</span>
            {typeof buyer.openCoreCount === 'number' && buyer.openCount > 0 && (
              <span className="block font-sans text-small text-ink-muted" data-open-core>
                {formatNumber(buyer.openCoreCount)} of them {SCOPE_CHOICES.core.label.toLowerCase()}
              </span>
            )}
          </FactCell>
          <FactCell label="Last published">
            {buyer.lastPublishedAt
              ? <time dateTime={buyer.lastPublishedAt}>{formatDateUtc(buyer.lastPublishedAt)} UTC</time>
              : <span className="font-sans">Not stated</span>}
          </FactCell>
        </FactsGrid>
        {variantsLine(buyer.nameVariants) && (variants.length > 0 ? (
          /* WP-111 (p04): the names themselves, so a reader sees which notices are this buyer's (WP-121: without the removal token) */
          <details className="max-w-prose text-small text-ink-muted" data-variant-names>
            <summary className="cursor-pointer">{variantsLine(buyer.nameVariants)}: show the names</summary>
            <ul className="m-0 mt-2 flex list-disc flex-col gap-1 pl-5">
              {variants.map((v) => <li key={v}>{v}</li>)}
            </ul>
          </details>
        ) : <p className="m-0 max-w-prose text-small text-ink-muted">{variantsLine(buyer.nameVariants)}</p>)}
        {outside ? (
          <p className="m-0 max-w-prose text-body" data-outside-scope>
            None of this buyer&rsquo;s notices is in the default scope, {SCOPE_CHOICES.relevant.label} ({SCOPE_CHOICES.core.label.toLowerCase()} and {SCOPE_CHOICES.supply.label.toLowerCase()}).
            The notices listed here are under {SCOPE_CHOICES.all.short}: {SCOPE_CHOICES.all.label.toLowerCase()}, for example a military product code bought by a civil buyer.
            The counts above are of them; the tender list shows them when you choose {SCOPE_CHOICES.all.short}.
          </p>
        ) : <p className="m-0 max-w-prose text-small text-ink-muted">
          Counts cover the notices the tender list shows for this buyer under {SCOPE_CHOICES.relevant.label}: {SCOPE_CHOICES.core.label.toLowerCase()} and {SCOPE_CHOICES.supply.label.toLowerCase()}. <span data-count-basis>A national notice that is a copy of a TED notice is counted once, so the count can be lower than the notices we hold.</span> Each notice shows its own source.
        </p>}
        {buyer.organisationSlug && (
          <p className="m-0 max-w-prose text-body">
            Also took part in funded projects: <Link href={`/organisations/${buyer.organisationSlug}`} className="font-semibold">see its projects, partners and EU funding</Link>.
          </p>
        )}
        {/* Said once for every card below instead of on each of them. */}
        {((open?.items.length ?? 0) > 0 || earlier.items.length > 0) && <ClassifiedNote tenders={[...(open?.items ?? []), ...(planned?.items ?? []), ...earlier.items]} />}
      </PageHeader>

      {/* WP-100: the open tenders before the profile's tables and charts (on a phone they started 3,900 px down, five screens) */}
      {/* WP-90: the buyer's own tenders under a CPV code */}
      {/* WP-144: one unit of the body (the names its notices state), each with its tenders; a GET form of its own (works without
          script), which carries the CPV filter, as the CPV form carries the unit */}
      {units.length > 0 && (
        <form method="get" action={`/buyers/${buyer.slug}`} aria-label="Choose a unit of this buyer"
          className="flex flex-col gap-3 rounded-lg border border-transparent bg-surface p-5 sm:flex-row sm:items-end" data-buyer-unit-form>
          <Select name="unit" label="Unit" placeholder={`All units (${formatNumber(buyer.tenderCount)})`} defaultValue={unit?.key ?? ''}
            options={unitOptions(units)} className="min-w-0 sm:min-w-72 sm:max-w-xl" data-buyer-unit />
          {cpv && <input type="hidden" name="cpv" value={cpv.join(',')} />}
          <Button type="submit">Show unit</Button>
        </form>
      )}
      <form method="get" action={`/buyers/${buyer.slug}`} role="search" aria-label="Filter this buyer's tenders"
        className="flex flex-col gap-3 rounded-lg border border-transparent bg-surface p-5 sm:flex-row sm:items-end" data-buyer-cpv>
        <TextInput name="cpv" maxLength={200} label="This buyer's tenders under a CPV code" placeholder="For example 357 or 35700000"
          defaultValue={cpv?.join(', ') ?? ''} className="sm:min-w-72" hint="Starts with the digits you enter; separate several with commas. The figures above stay all of its tenders." />
        {unit && <input type="hidden" name="unit" value={unit.key} />}
        <div className="flex items-center gap-3">
          <Button type="submit">Show</Button>
          {cpv && <Link href={`/buyers/${buyer.slug}${toTenderQuery({ unit: unit?.key, sort: undefined })}`} className="inline-flex min-h-11 items-center text-small font-bold">Clear</Link>}
        </div>
      </form>
      {narrowed && (
        <p className="m-0 max-w-prose text-body" role="status" data-buyer-narrowed>
          Showing {unit ? <>the tenders of {unitName(unit)}</> : <>this buyer&rsquo;s tenders</>}{cpv && <> with a code under {cpv.join(', ')}</>}: {formatNumber(open?.total ?? 0)} open and {formatNumber(earlier.total)} earlier.
          {unit && <> <Link href={`/buyers/${buyer.slug}${toTenderQuery({ cpv, sort: undefined })}`} className="font-semibold">Show all units</Link></>}
        </p>
      )}

      {/* WP-105 (p06: on a phone it started 81,000 px down, after 28 open and 100 planned cards): who wins, with the money, first */}
      {suppliers && suppliers !== UNAVAILABLE && suppliers.items.length > 0 && <BuyerTopSuppliers data={suppliers} name={name} cpv={cpv} />}
      {/* WP-111 (p03): a supplier table that could not be read is said, not left out (under a code filter it looked as if the filter emptied it) */}
      {suppliers === UNAVAILABLE && (
        <p className="m-0 max-w-prose text-body" role="status" data-top-suppliers-unavailable>
          The top suppliers of this buyer{cpv ? ` under ${cpv.join(', ')}` : ''} could not be loaded just now. Reload the page in a minute to see them.
        </p>
      )}
      {suppliers && suppliers !== UNAVAILABLE && suppliers.items.length === 0 && cpv && (
        <p className="m-0 max-w-prose text-body" data-top-suppliers-none>No published award of this buyer in the last three years names a winner under {cpv.join(', ')}.</p>
      )}

      {page === 1 && (
        <section aria-labelledby="open-tenders" className="flex flex-col gap-4">
          <h2 id="open-tenders" className="m-0 text-h2">Open tenders</h2>
          {open && open.items.length > 0 ? (
            <>
              <ul className="m-0 flex list-none flex-col gap-4 p-0">
                {open.items.map((t) => <li key={t.id}><TenderCard tender={t} headingLevel="h3" classifiedNote={false} /></li>)}
              </ul>
              {open.total > open.items.length && (
                <p className="m-0 text-small text-ink-muted" data-open-shown>
                  Showing {formatNumber(open.items.length)} of {formatNumber(open.total)} open tenders, soonest deadline first.
                  {!all && <> <Link href={allHref} className="font-semibold">Show all {open.total > OPEN_LIMIT ? `${formatNumber(OPEN_LIMIT)} of them` : formatNumber(open.total)}</Link></>}
                </p>
              )}
            </>
          ) : (
            <EmptyState title="No open tenders" action={<Button variant="secondary" href="/tenders">Browse current tenders</Button>}>
              {unit ? 'This unit' : 'This buyer'} has no open defence tender in our archive at the moment.
            </EmptyState>
          )}
        </section>
      )}

      {page === 1 && planned && planned.items.length > 0 && (
        <section aria-labelledby="planned-tenders" className="flex flex-col gap-4">
          <h2 id="planned-tenders" className="m-0 text-h2">Planned tenders</h2>
          {/* WP-105: folded when there are many (100 planned cards made the page 89,000 px tall on a phone) */}
          <details open={planned.items.length <= PLANNED_OPEN} data-planned-fold>
            <summary className="cursor-pointer text-body font-semibold">{`Show the ${formatNumber(planned.items.length)} planned ${planned.items.length === 1 ? 'tender' : 'tenders'}`}</summary>
            <ul className="m-0 mt-4 flex list-none flex-col gap-4 p-0">
              {planned.items.map((t) => <li key={t.id}><TenderCard tender={t} headingLevel="h3" classifiedNote={false} /></li>)}
            </ul>
          </details>
          {planned.total > planned.items.length && (
            <p className="m-0 text-small text-ink-muted" data-planned-shown>
              Showing {formatNumber(planned.items.length)} of {formatNumber(planned.total)} planned tenders.
              {!all && <> <Link href={allHref} className="font-semibold">Show {planned.total > OPEN_LIMIT ? `${formatNumber(OPEN_LIMIT)} of them` : 'all of them'}</Link></>}
            </p>
          )}
        </section>
      )}

      {ending && ending.items.length > 0 && (
        <section aria-labelledby="contracts-ending" className="flex flex-col gap-4" data-buyer-ending>
          <h2 id="contracts-ending" className="m-0 text-h2">Contracts ending in the next 12 months</h2>
          <p className="m-0 max-w-prose text-small text-ink-muted">When a contract ends, the buyer usually tenders again. Soonest first, from the contract periods the notices state.</p>
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {ending.items.map((t) => <EndingRow key={t.id} t={t} showBuyer={false} />)}
          </ul>
          <p className="m-0 text-small text-ink-muted">
            {ending.total > ending.items.length ? `The first ${formatNumber(ending.items.length)} of ${formatNumber(ending.total)}. ` : ''}
            <Link href={`/tenders/ending?buyer=${encodeURIComponent(buyer.id)}`} className="font-semibold">All contracts of this buyer ending soon</Link>
          </p>
        </section>
      )}

      {profile && profile.tenderCount > 0 && <BuyerProfileSection profile={profile} name={name} />}

      <section aria-labelledby="earlier-tenders" className="flex flex-col gap-4">
        <h2 id="earlier-tenders" className="m-0 text-h2">Earlier tenders</h2>
        {earlier.items.length > 0 ? (
          <>
            <ul className="m-0 flex list-none flex-col gap-4 p-0">
              {earlier.items.map((t) => <li key={t.id}><TenderCard tender={t} headingLevel="h3" classifiedNote={false} /></li>)}
            </ul>
            <Pagination page={earlier.page} total={earlier.total} pageSize={earlier.pageSize} hrefFor={hrefOf} />
          </>
        ) : (
          <EmptyState title="No earlier tenders">
            {page > 1 ? 'There are no more tenders on this page.' : 'Closed and awarded tenders from this buyer will appear here.'}
          </EmptyState>
        )}
      </section>
    </>
  );
}
