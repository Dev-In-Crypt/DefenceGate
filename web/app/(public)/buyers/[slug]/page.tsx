import type { Metadata } from 'next';
import { notFound, permanentRedirect, redirect } from 'next/navigation';
import { getBuyer, getBuyerProfile, getTenders, isBuyerSlug } from '@/lib/api';
import { displayName } from '@/lib/display-name';
import { formatDateUtc } from '@/lib/format';
import { MAX_PAGE, TENDER_PAGE_SIZE, lastPage, type SearchParams } from '@/lib/filters';
import { buildMetadata } from '@/lib/seo';
import { Breadcrumbs, EmptyState } from '@/components/dg/feedback';
import { Tag } from '@/components/dg/tag';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { TenderCard } from '@/components/dg/cards';
import { Pagination } from '@/components/dg/pagination';
import { Button } from '@/components/dg/button';
import { FollowButton } from '@/components/account/save-button';
import { BuyerProfileSection } from '@/components/market/buyer-profile';

export const revalidate = 3600;
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
  const buyer = await getBuyer(slug);
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
  const buyer = await getBuyer(slug);
  if (!buyer) notFound();
  if (buyer.slug !== slug && isBuyerSlug(buyer.slug)) permanentRedirect(`/buyers/${buyer.slug}`);

  const page = pageOf(sp);
  // Two fixed queries on the id the API gave us: open tenders first, then the history. No ordering across them is assumed.
  const [open, earlier, profile] = await Promise.all([
    page === 1 && buyer.openCount > 0
      ? getTenders({ buyer: buyer.id, status: 'open', pageSize: OPEN_LIMIT }, { cacheable: true })
      : Promise.resolve(null),
    getTenders({ buyer: buyer.id, status: 'closed', sort: 'published-desc', page, pageSize: TENDER_PAGE_SIZE }, { cacheable: page === 1 }),
    // The profile is an extra: a buyer page still renders when the API cannot answer it.
    page === 1 && buyer.tenderCount > 0 ? getBuyerProfile(buyer) : Promise.resolve(null),
  ]);

  // A page past the last one is the last one, not an empty list.
  if (page > 1 && earlier.items.length === 0 && earlier.total > 0) {
    const last = lastPage(earlier.total, earlier.pageSize);
    redirect(last > 1 ? `/buyers/${buyer.slug}?page=${last}` : `/buyers/${buyer.slug}`);
  }
  const name = displayName(buyer.name, 'title');

  return (
    <>
      <Breadcrumbs items={[
        { label: 'Home', href: '/' }, { label: 'Buyers', href: '/buyers' },
        { label: name, href: `/buyers/${buyer.slug}` },
      ]} />

      <header className="flex flex-col gap-4">
        {buyer.isDefenceBuyer && <span className="self-start"><Tag>Defence body</Tag></span>}
        <h1 className="m-0 break-words text-[32px] font-extrabold leading-10 tracking-[-1px] md:text-h1">{name}</h1>
        <FollowButton kind="buyer" refId={buyer.id} label="Follow this buyer" />
        <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
          <FactCell label="Country">
            {buyer.country ? <CountryLabel code={buyer.country} className="font-sans" /> : <span className="font-sans">Not stated</span>}
          </FactCell>
          <FactCell label="Tenders in archive"><span className="tabular-nums">{buyer.tenderCount}</span></FactCell>
          <FactCell label="Open now"><span className="tabular-nums">{buyer.openCount}</span></FactCell>
          <FactCell label="Last published">
            {buyer.lastPublishedAt
              ? <time dateTime={buyer.lastPublishedAt}>{formatDateUtc(buyer.lastPublishedAt)} UTC</time>
              : <span className="font-sans">Not stated</span>}
          </FactCell>
        </dl>
        <p className="m-0 max-w-[62ch] text-small text-ink-muted">Counts cover defence notices only. Each notice below shows its own source.</p>
      </header>

      {profile && profile.tenderCount > 0 && <BuyerProfileSection profile={profile} name={name} />}

      {page === 1 && (
        <section aria-labelledby="open-tenders" className="flex flex-col gap-4">
          <h2 id="open-tenders" className="m-0 text-h2">Open tenders</h2>
          {open && open.items.length > 0 ? (
            <>
              <ul className="m-0 flex list-none flex-col gap-4 p-0">
                {open.items.map((t) => <li key={t.id}><TenderCard tender={t} headingLevel="h3" /></li>)}
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

      <section aria-labelledby="earlier-tenders" className="flex flex-col gap-4">
        <h2 id="earlier-tenders" className="m-0 text-h2">Earlier tenders</h2>
        {earlier.items.length > 0 ? (
          <>
            <ul className="m-0 flex list-none flex-col gap-4 p-0">
              {earlier.items.map((t) => <li key={t.id}><TenderCard tender={t} headingLevel="h3" /></li>)}
            </ul>
            <Pagination page={earlier.page} total={earlier.total} pageSize={earlier.pageSize}
              hrefFor={(p) => (p > 1 ? `/buyers/${buyer.slug}?page=${p}` : `/buyers/${buyer.slug}`)} />
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
