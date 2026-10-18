import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getDigest, getDigestWeeks } from '@/lib/api';
import { digestQuery, isWeek, parseDigestFilters, unknownDigestCountry, weekLabel } from '@/lib/digest';
import { formatDateTimeUtc } from '@/lib/format';
import type { SearchParams } from '@/lib/filters';
import { staleNote } from '@/lib/source-status';
import { buildMetadata } from '@/lib/seo';
import { Breadcrumbs } from '@/components/dg/feedback';
import { DigestView, WeekList } from '@/components/digest/digest-view';

export const revalidate = 300;

type Props = { params: Promise<{ week: string }>; searchParams: Promise<SearchParams> };

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const { week } = await params;
  const f = parseDigestFilters(await searchParams);
  if (!isWeek(week)) return { title: 'Issue not found', robots: { index: false } };
  const meta = buildMetadata({
    title: `Weekly digest, ${weekLabel(week)}`,
    description: `The week's new and amended defence notices, new, opened and closing funding calls and calls with cascade funding, from our archive. ${weekLabel(week)}.`,
    path: `/digest/${week}`,
    noindex: Boolean(f.country),
  });
  return { ...meta, alternates: { ...meta.alternates, types: { 'application/atom+xml': '/digest.atom' } } };
}

/** One earlier issue of the weekly digest. A week outside the archive, or not ended yet, is a 404. */
export default async function DigestWeekPage({ params, searchParams }: Props) {
  const { week } = await params;
  const sp = await searchParams;
  const filters = parseDigestFilters(sp);
  const unknown = unknownDigestCountry(sp);
  if (!isWeek(week)) notFound();
  const [issue, weeks] = await Promise.all([getDigest(week, filters.country).catch(() => null), getDigestWeeks().catch(() => [])]);
  if (!issue) notFound();
  return (
    <>
      <Breadcrumbs items={[{ label: 'Home', href: '/' }, { label: 'Weekly digest', href: '/digest' }, { label: weekLabel(week), href: `/digest/${week}${digestQuery(filters)}` }]} />
      {unknown && (
        <p role="status" className="m-0 rounded-md bg-surface-inset px-4 py-3 text-small text-ink">{`Ignored filter: country=${unknown} (not a country we list); showing every country.`}</p>
      )}
      {issue.staleAsOf && (
        <p role="status" className="m-0 rounded-md bg-surface-inset px-4 py-3 text-small text-ink">{staleNote(issue.staleAsOf, formatDateTimeUtc)}</p>
      )}
      <DigestView issue={issue} filters={filters} basePath={`/digest/${week}`} feedHref={`/digest.atom${digestQuery(filters)}`} />
      <WeekList weeks={weeks} current={issue.week} filters={filters} />
    </>
  );
}
