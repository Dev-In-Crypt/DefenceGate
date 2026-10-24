import type { Metadata } from 'next';
import Link from 'next/link';
import { buildMetadata } from '@/lib/seo';
import { formatDateUtc, formatNumber, plural } from '@/lib/format';
import { countryName } from '@/lib/taxonomy';
import { displayName } from '@/lib/display-name';
import { getSearch, searchQuery, seeAllHref, type SearchGroup, type SiteSearch } from '@/lib/search';
import { PageHeader } from '@/components/dg/page-header';
import { Card } from '@/components/dg/card';
import { SiteSearchForm } from '@/components/dg/site-search';
import { ErrorState } from '@/components/dg/feedback';
import { AlsoSearched, CpvHints, GroupSuggestions } from '@/components/tenders/search-terms-note';
import { ApiError } from '@/lib/api';

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

// Every query is a page of its own: never indexed, never listed in the sitemap.
export const metadata: Metadata = buildMetadata({
  title: 'Search',
  description: 'Search tenders, funding calls, buyers and companies at once.',
  path: '/search',
  noindex: true,
});

type Key = keyof Omit<SiteSearch, 'q' | 'alsoSearched' | 'searchGroups' | 'buyerNamed' | 'cpvHints'>;
interface Row { href: string; title: string; line: string }

const where = (country: string | null | undefined) => (country ? countryName(country) : null);
const join = (...parts: (string | null | undefined)[]) => parts.filter(Boolean).join(' · ');

/** Each group's rows: the name or title, and one line of what the list card says first. */
function rows(s: SiteSearch, key: Key): Row[] {
  switch (key) {
    case 'tenders': return s.tenders.items.map((t) => ({ href: `/tenders/${t.slug}`, title: t.title,
      line: join(displayName(t.buyerName), where(t.country), t.deadline ? `Deadline ${formatDateUtc(t.deadline)}` : 'No deadline stated') }));
    case 'funding': return s.funding.items.map((c) => ({ href: `/funding/${c.slug}`, title: c.title,
      line: join(c.programmeName, c.deadline ? `Deadline ${formatDateUtc(c.deadline)}` : 'No fixed deadline') }));
    case 'buyers': return s.buyers.items.map((b) => ({ href: `/buyers/${b.slug}`, title: displayName(b.name),
      line: join(where(b.country), `${formatNumber(b.tenderCount)} ${plural(b.tenderCount, 'tender')}, ${formatNumber(b.openCount)} open`) }));
    // WP-110 (p07): a company found by a name it was published under says that name ("Leonardo" found Megmar as a consortium partner)
    case 'suppliers': return s.suppliers.items.map((x) => ({ href: `/suppliers/${x.slug}`, title: displayName(x.name),
      line: join(where(x.country), `${formatNumber(x.awardCount)} ${plural(x.awardCount, 'contract')} won`, x.matchedAs ? `named in an award as “${x.matchedAs}”` : null) }));
    case 'organisations': return s.organisations.items.map((o) => ({ href: `/organisations/${o.slug}`, title: displayName(o.name),
      line: join(where(o.country), `${formatNumber(o.defenceProjects)} defence ${plural(o.defenceProjects, 'project')}`) }));
  }
}

/** The groups in the menu's order; Companies is the two tabs of the Companies page. */
// WP-106 (p07): `one`, the noun of a total of one ("See all 1 companies")
const GROUPS: { title: string; parts: { key: Key; label?: string; noun: string; one: string }[] }[] = [
  { title: 'Tenders', parts: [{ key: 'tenders', noun: 'open tenders', one: 'open tender' }] },
  { title: 'Funding', parts: [{ key: 'funding', noun: 'open funding calls', one: 'open funding call' }] },
  { title: 'Buyers', parts: [{ key: 'buyers', noun: 'buyers', one: 'buyer' }] },
  { title: 'Companies', parts: [
    { key: 'suppliers', label: 'Won contracts', noun: 'companies that won contracts', one: 'company that won contracts' },
    { key: 'organisations', label: 'In EU-funded projects', noun: 'companies in EU-funded defence projects', one: 'company in EU-funded defence projects' },
  ] },
];

/**
 * WP-96: words that name a buyer (BAAINBw, Ministère de la Défense) find its tenders by the buyer, not by title words: the buyer's own
 * open count (its whole family, the tender list's default scope), linked to its page. Only when the words name few buyers.
 */
function BuyerTenders({ s }: { s: SiteSearch }) {
  // WP-98: also when many buyers match, if the first is the one the words name (BAAINBw, DMO, "Ministère de la Défense")
  const b = s.buyers.error || ((s.buyers.total ?? 0) > 3 && !s.buyerNamed) ? undefined : s.buyers.items[0];
  if (!b || b.openCount === 0) return null;
  return (
    <p className="m-0 text-body" data-buyer-tenders>
      <Link href={`/buyers/${b.slug}`} className="font-semibold">{displayName(b.name)}: {formatNumber(b.openCount)} open {plural(b.openCount, 'tender')}</Link>
      <span className="block text-small text-ink-muted">All of this buyer&rsquo;s open tenders, whatever their titles say. The list below matches the words in titles.</span>
    </p>
  );
}

const cpvHref = (prefix: string) => `/tenders?${new URLSearchParams({ cpv: prefix })}`;

function Part({ s, part }: { s: SiteSearch; part: (typeof GROUPS)[number]['parts'][number] }) {
  const g: SearchGroup<unknown> = s[part.key];
  const all = seeAllHref(part.key, s.q);
  const total = g.total === null ? '' : `${g.atLeast ? 'at least ' : ''}${formatNumber(g.total)}`;
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {part.label && <h3 className="m-0 text-h4">{part.label}</h3>}
      {part.key === 'tenders' && <BuyerTenders s={s} />}
      {g.error ? (
        <p className="m-0 text-body text-ink-muted">
          {g.error === 'slow' ? 'This part of the search took too long.' : g.error === 'busy' ? 'This part of the search is busy right now.' : 'This list does not search for these words.'}{' '}
          <Link href={all} className="font-semibold">Search the list itself</Link>
        </p>
      ) : g.total === 0 ? (
        <div className="m-0 text-body text-ink-muted">
          No {part.noun} match.
          {part.key === 'tenders' && <AlsoSearched also={s.alsoSearched} />}
          {part.key === 'tenders' && <CpvHints hints={s.cpvHints} hrefFor={cpvHref} />}
          {part.key === 'tenders' && <GroupSuggestions groups={s.searchGroups} hrefFor={(cpv) => `/tenders?${new URLSearchParams({ cpv: cpv.join(',') })}`} />}
        </div>
      ) : (
        <>
          <ul className="m-0 flex list-none flex-col p-0">
            {rows(s, part.key).map((r) => (
              <li key={r.href} className="border-t border-line first:border-t-0">
                <Link href={r.href} className="flex min-h-11 flex-col justify-center py-2 no-underline hover:underline">
                  <span className="text-body font-semibold text-ink [overflow-wrap:anywhere]">{r.title}</span>
                  {r.line && <span className="text-small text-ink-muted">{r.line}</span>}
                </Link>
              </li>
            ))}
          </ul>
          <Link href={all} className="inline-flex min-h-11 items-center self-start text-small font-bold">See {g.total === 1 && !g.atLeast ? 'the' : 'all'} {total} {g.total === 1 && !g.atLeast ? part.one : part.noun}</Link>
          {part.key === 'tenders' && <AlsoSearched also={s.alsoSearched} />}
          {part.key === 'tenders' && <CpvHints hints={s.cpvHints} hrefFor={cpvHref} />}
        </>
      )}
    </div>
  );
}

export default async function SearchPage({ searchParams }: Props) {
  const q = searchQuery((await searchParams).q);
  // A search the data service did not answer (busy, too many searches from one address) says so; the lists still work.
  // WP-110: too many searches from one address (429: the round-4 auditors were ten on one address) is said as such.
  const result = q ? await getSearch(q).catch((e) => (e instanceof ApiError && e.status === 429 ? 'limited' as const : 'failed' as const)) : null;
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', href: '/' }, { label: 'Search', href: '/search' }]} title="Search"
        lead={q ? undefined : 'One search over tenders, funding calls, buyers and companies. Each part shows its first five matches and leads to the full list.'}>
        <SiteSearchForm id="page-search" defaultValue={q} className="max-w-2xl" />
      </PageHeader>
      {(result === 'failed' || result === 'limited') && (
        <ErrorState title={result === 'limited' ? 'Too many searches from your network just now' : 'The search is not available right now'} retryHref={`/search?${new URLSearchParams({ q })}`}>
          {result === 'limited' ? 'The number of searches a minute from one internet address is limited, and an office behind one address shares the limit. ' : ''}Try again in a minute, or search one list: <Link href={seeAllHref('tenders', q)} className="font-semibold">tenders</Link>, <Link href={seeAllHref('funding', q)} className="font-semibold">funding</Link>, <Link href={seeAllHref('buyers', q)} className="font-semibold">buyers</Link> or <Link href={seeAllHref('suppliers', q)} className="font-semibold">companies</Link>.
        </ErrorState>
      )}
      {result && result !== 'failed' && result !== 'limited' && (
        <section aria-labelledby="results-heading" className="flex flex-col gap-4">
          <h2 id="results-heading" className="m-0 text-h2">Results for “{result.q}”</h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {GROUPS.map((g) => (
              <Card key={g.title} title={g.title} id={`group-${g.title.toLowerCase()}`} className={g.parts.length > 1 ? 'lg:col-span-2' : undefined}
                bodyClassName={g.parts.length > 1 ? 'grid gap-6 lg:grid-cols-2' : undefined}>
                {g.parts.map((p) => <Part key={p.key} s={result} part={p} />)}
              </Card>
            ))}
          </div>
          <p className="m-0 max-w-prose text-small text-ink-muted">
            Tenders and funding calls are the open ones, as their lists open; companies in EU-funded projects are those of the defence programmes. Each list can widen the search.
          </p>
        </section>
      )}
    </>
  );
}
