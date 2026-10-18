import type { Metadata } from 'next';
import { getDigest, getDigestWeeks } from '@/lib/api';
import { digestQuery, parseDigestFilters, unknownDigestCountry } from '@/lib/digest';
import { formatDateTimeUtc } from '@/lib/format';
import type { SearchParams } from '@/lib/filters';
import { staleNote } from '@/lib/source-status';
import { buildMetadata } from '@/lib/seo';
import { EmptyState } from '@/components/dg/feedback';
import { PageHeader } from '@/components/dg/page-header';
import { Button } from '@/components/dg/button';
import { DigestView, WeekList } from '@/components/digest/digest-view';

export const revalidate = 300;

type Props = { searchParams: Promise<SearchParams> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const f = parseDigestFilters(await searchParams);
  const meta = buildMetadata({
    title: 'Weekly digest of defence notices and funding calls',
    description: 'Each week: new and amended defence notices, new, opened and closing funding calls with the eligibility rules where we have read them, and calls with cascade funding. Free, with an Atom feed.',
    path: '/digest',
    noindex: Boolean(f.country),
  });
  return { ...meta, alternates: { ...meta.alternates, types: { 'application/atom+xml': '/digest.atom' } } };
}

/** The latest complete week. `/digest/[week]` is the same page for an earlier one. */
export default async function DigestPage({ searchParams }: Props) {
  const sp = await searchParams;
  const filters = parseDigestFilters(sp);
  const unknown = unknownDigestCountry(sp);
  const crumbs = [{ label: 'Home', href: '/' }, { label: 'Weekly digest', href: '/digest' }];
  const [issue, weeks] = await Promise.all([getDigest(undefined, filters.country).catch(() => null), getDigestWeeks().catch(() => [])]);
  if (!issue) {
    return (
      <>
        <PageHeader crumbs={crumbs} title="Weekly digest" />
        <EmptyState title="There is no issue to show right now" action={<Button variant="secondary" href={`/digest${digestQuery(filters)}`}>Try again</Button>}>
          The first issue appears when the first full week of our archive has ended, and the data service did not answer for this one.
          Nothing here means there is nothing to report: the issue could not be read. <a href="/changes" className="font-semibold">What changed</a> covers the last 14 days meanwhile.
        </EmptyState>
      </>
    );
  }
  return (
    <>
      <DigestView issue={issue} filters={filters} basePath="/digest" feedHref={`/digest.atom${digestQuery(filters)}`} crumbs={crumbs}
        notices={<>
        {unknown && (
          <p role="status" className="m-0 rounded-md bg-surface-inset px-4 py-3 text-small text-ink">{`Ignored filter: country=${unknown} (not a country we list); showing every country.`}</p>
        )}
        {issue.staleAsOf && (
          <p role="status" className="m-0 rounded-md bg-surface-inset px-4 py-3 text-small text-ink">{staleNote(issue.staleAsOf, formatDateTimeUtc)}</p>
        )}
      </>} />
      <WeekList weeks={weeks} current={issue.week} filters={filters} />
    </>
  );
}
