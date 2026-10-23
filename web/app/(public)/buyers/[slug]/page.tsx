import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, permanentRedirect, redirect } from 'next/navigation';
import { getBuyer, getBuyerProfile, getBuyerSuppliers, getTenders, isBuyerSlug, REMOVED, whenRemoved } from '@/lib/api';
import { RemovedOnRequest } from '@/components/dg/removed';
import { displayName } from '@/lib/display-name';
import { formatDateUtc, formatNumber, variantsLine } from '@/lib/format';
import { MAX_PAGE, TENDER_PAGE_SIZE, lastPage, parseTenderFilters, toTenderQuery, type SearchParams } from '@/lib/filters';
import { TextInput } from '@/components/dg/form';
import { BuyerTopSuppliers } from '@/components/market/buyer-suppliers';
import { buildMetadata } from '@/lib/seo';
import { EmptyState } from '@/components/dg/feedback';
import { PageHeader } from '@/components/dg/page-header';
import { FactsGrid } from '@/components/dg/facts-grid';
import { ClassifiedNote } from '@/components/dg/basis-chips';
import { Tag } from '@/components/dg/tag';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { TenderCard } from '@/components/dg/cards';
import { Pagination } from '@/components/dg/pagination';
import { Button } from '@/components/dg/button';
import { FollowButton } from '@/components/account/save-button';
import { BuyerProfileSection } from '@/components/market/buyer-profile';

export const revalidate = 300;
type Props = { params: Promise<{ slug: string }>; searchParams: Promise<SearchParams> };

/** Open tenders are listed in full (up to this many), then the earlier ones page by page. */
const OPEN_LIMIT = 100;

function pageOf(sp: SearchParams): number {
  const raw = Array.isArray(sp.page) ? sp.page[0] : sp.page;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 1 ? Math.min(Math.floor(n), MAX_PAGE) : 1;
}

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const [{ slug }, sp] = await Promise.all([params, searchParams]);
  const buyer = await getBuyer(slug).catch(whenRemoved);
  if (buyer === REMOVED) return { title: 'Removed on request', robots: { index: false } };
  if (!buyer) return { title: 'Buyer not found', robots: { index: false } };
  const name = displayName(buyer.name, 'title');
  return buildMetadata({
    title: name,
    description: `${name}: ${buyer.tenderCount} defence tenders in the archive, ${buyer.openCount} open now.`,
    path: `/buyers/${buyer.slug}`,
    noindex: pageOf(sp) > 1 || buyer.tenderCount === 0,
  });
}

export default async function BuyerDetailPage({ params, searchParams }: Props) {
  const [{ slug }, sp] = await Promise.all([params, searchParams]);
  if (!isBuyerSlug(slug)) notFound();
  const buyer = await getBuyer(slug).catch(whenRemoved);
  if (buyer === REMOVED) return <RemovedOnRequest what="buyer" />;
  if (!buyer) notFound();
  if (buyer.slug !== slug && isBuyerSlug(buyer.slug)) permanentRedirect(`/buyers/${buyer.slug}`);

  const page = pageOf(sp);
  // WP-90: a CPV filter on the buyer's own tenders (the tender list's reading: any code of a notice under the prefixes); the figures above stay all of them
  const cpv = parseTenderFilters(sp).cpv;
  const own = { buyer: buyer.id, scope: 'core' as const, cpv };
  const hrefOf = (p: number) => `/buyers/${buyer.slug}${toTenderQuery({ cpv, page: p, sort: undefined })}`;
  // Two fixed queries on the id the API gave us: open tenders first, then the history. No ordering across them is assumed.
  // All of them in the scope the counts above are in (`core`: the notice itself is defence). The lists used the site's default,
  // `relevant`, while "Open now" counted `core`, so a buyer could list more open tenders than it said it had (UX audit T14).
  const [open, planned, earlier, profile, suppliers] = await Promise.all([
    page === 1 && (buyer.openCount > 0 || cpv)
      ? getTenders({ ...own, status: 'open', pageSize: OPEN_LIMIT }, { cacheable: !cpv })
      : Promise.resolve(null),
    // A planned notice (prior information) is neither open nor closed since 19 October 2026; it is counted in "Tenders in archive".
    page === 1 ? getTenders({ ...own, status: 'planned', pageSize: OPEN_LIMIT }, { cacheable: !cpv }).catch(() => null) : Promise.resolve(null),
    getTenders({ ...own, status: 'closed', sort: 'published-desc', page, pageSize: TENDER_PAGE_SIZE }, { cacheable: page === 1 && !cpv }),
    // The profile is an extra: a buyer page still renders when the API cannot answer it.
    page === 1 && buyer.tenderCount > 0 ? getBuyerProfile(buyer) : Promise.resolve(null),
    page === 1 ? getBuyerSuppliers(buyer) : Promise.resolve(null),
  ]);

  // A page past the last one is the last one, not an empty list.
  if (page > 1 && earlier.items.length === 0 && earlier.total > 0) {
    redirect(hrefOf(lastPage(earlier.total, earlier.pageSize)));
  }
  const name = displayName(buyer.name, 'title');

  return (
    <>
      <PageHeader
        crumbs={[
          { label: 'Home', href: '/' }, { label: 'Buyers', href: '/buyers' },
          { label: name, href: `/buyers/${buyer.slug}` },
        ]}
        eyebrow={buyer.isDefenceBuyer ? <span className="self-start"><Tag>Defence body</Tag></span> : undefined}
        title={name}
      >
        <FollowButton kind="buyer" refId={buyer.id} label="Follow this buyer" />
        <FactsGrid className="facts-grid--4">
          <FactCell label="Country">
            {buyer.country ? <CountryLabel code={buyer.country} className="font-sans" /> : <span className="font-sans">Not stated</span>}
          </FactCell>
          {/* WP-87: the profile's total when there is one (notices shown once, the unit of every figure below), so the page has one number */}
          <FactCell label="Tenders in archive"><span className="tabular-nums">{profile?.tenderCount ?? buyer.tenderCount}</span></FactCell>
          <FactCell label="Open now"><span className="tabular-nums">{buyer.openCount}</span></FactCell>
          <FactCell label="Last published">
            {buyer.lastPublishedAt
              ? <time dateTime={buyer.lastPublishedAt}>{formatDateUtc(buyer.lastPublishedAt)} UTC</time>
              : <span className="font-sans">Not stated</span>}
          </FactCell>
        </FactsGrid>
        {variantsLine(buyer.nameVariants) && <p className="m-0 max-w-prose text-small text-ink-muted">{variantsLine(buyer.nameVariants)}</p>}
        <p className="m-0 max-w-prose text-small text-ink-muted">Counts cover defence notices only; each notice shows its own source.</p>
        {buyer.organisationSlug && (
          <p className="m-0 max-w-prose text-body">
            Also took part in funded projects: <Link href={`/organisations/${buyer.organisationSlug}`} className="font-semibold">see its projects, partners and EU funding</Link>.
          </p>
        )}
        {/* Said once for every card below instead of on each of them. */}
        {((open?.items.length ?? 0) > 0 || earlier.items.length > 0) && <ClassifiedNote tenders={[...(open?.items ?? []), ...(planned?.items ?? []), ...earlier.items]} />}
      </PageHeader>

      {profile && profile.tenderCount > 0 && <BuyerProfileSection profile={profile} name={name} />}

      {suppliers && suppliers.items.length > 0 && <BuyerTopSuppliers data={suppliers} name={name} />}

      {/* WP-90: the buyer's own tenders under a CPV code */}
      <form method="get" action={`/buyers/${buyer.slug}`} role="search" aria-label="Filter this buyer's tenders"
        className="flex flex-col gap-3 rounded-lg border border-transparent bg-surface p-5 sm:flex-row sm:items-end" data-buyer-cpv>
        <TextInput name="cpv" maxLength={200} label="This buyer's tenders under a CPV code" placeholder="For example 357 or 35700000"
          defaultValue={cpv?.join(', ') ?? ''} className="sm:min-w-72" hint="Starts with the digits you enter; separate several with commas. The figures above stay all of its tenders." />
        <div className="flex items-center gap-3">
          <Button type="submit">Show</Button>
          {cpv && <Link href={`/buyers/${buyer.slug}`} className="inline-flex min-h-11 items-center text-small font-bold">Clear</Link>}
        </div>
      </form>
      {cpv && (
        <p className="m-0 max-w-prose text-body" role="status">
          Showing this buyer&rsquo;s tenders with a code under {cpv.join(', ')}: {formatNumber(open?.total ?? 0)} open and {formatNumber(earlier.total)} earlier.
        </p>
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
                <p className="m-0 text-small text-ink-muted">Showing {open.items.length} of {open.total} open tenders.</p>
              )}
            </>
          ) : (
            <EmptyState title="No open tenders" action={<Button variant="secondary" href="/tenders">Browse current tenders</Button>}>
              This buyer has no open defence tender in our archive at the moment.
            </EmptyState>
          )}
        </section>
      )}

      {page === 1 && planned && planned.items.length > 0 && (
        <section aria-labelledby="planned-tenders" className="flex flex-col gap-4">
          <h2 id="planned-tenders" className="m-0 text-h2">Planned tenders</h2>
          <ul className="m-0 flex list-none flex-col gap-4 p-0">
            {planned.items.map((t) => <li key={t.id}><TenderCard tender={t} headingLevel="h3" classifiedNote={false} /></li>)}
          </ul>
          {planned.total > planned.items.length && (
            <p className="m-0 text-small text-ink-muted">Showing {planned.items.length} of {planned.total} planned tenders.</p>
          )}
        </section>
      )}

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
