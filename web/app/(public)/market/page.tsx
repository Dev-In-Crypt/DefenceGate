import type { Metadata } from 'next';
import Link from 'next/link';
import { getMarketStats } from '@/lib/api';
import { MARKET_FIRST_YEAR, PARAM, parseMarketFilters, type SearchParams } from '@/lib/filters';
import { BUYER_COUNTRIES } from '@/lib/taxonomy';
import { Button } from '@/components/dg/button';
import { Select } from '@/components/dg/form';
import { cpvGroupName } from '@/lib/cpv';
import { formatDateTimeUtc, formatDateUtc, formatNumber, plural } from '@/lib/format';
import { daysText, monthLabel, percentText } from '@/lib/market';
import { buildMetadata } from '@/lib/seo';
import { AutoGrid } from '@/components/dg/auto-grid';
import { BarChart, RankTable } from '@/components/market/charts';
import { ContentPage, ContentSection } from '@/components/dg/content-page';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { EmptyState } from '@/components/dg/feedback';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Market overview',
  description: 'How many defence procurement notices are published, by month, country and subject. Counts of notices, not contract value.',
  path: '/market',
});

const BASIS = 'text-small text-ink-muted m-0 max-w-prose';
const LINK = 'font-semibold';

type Props = { searchParams: Promise<SearchParams> };

export default async function MarketPage({ searchParams }: Props) {
  const filters = parseMarketFilters(await searchParams);
  const stats = await getMarketStats(filters).catch(() => null);
  const thisYear = new Date().getUTCFullYear();
  const yearOptions = Array.from({ length: thisYear - MARKET_FIRST_YEAR + 1 }, (_, i) => String(thisYear - i)).map((y) => ({ value: y, label: y }));
  const selectors = (
    <form method="get" action="/market" role="search" aria-label="Choose the year and the country" className="flex flex-col gap-4 rounded-lg border border-transparent bg-surface p-5 sm:flex-row sm:flex-wrap sm:items-end">
      <Select name={PARAM.year} label="Year of publication" placeholder="Last 12 months (moves daily)" defaultValue={filters.year ? String(filters.year) : ''}
        className="sm:min-w-56" options={yearOptions} />
      <Select name={PARAM.country} label="Buyer country" placeholder="All countries" defaultValue={filters.country ?? ''} className="sm:min-w-56"
        options={Object.entries(BUYER_COUNTRIES).map(([code, name]) => ({ value: code, label: `${name} (${code})` }))} />
      <div className="flex items-center gap-3">
        <Button type="submit">Show</Button>
        <Link href="/market" className="inline-flex min-h-11 items-center text-small font-bold">Clear</Link>
      </div>
    </form>
  );
  const crumbs = [{ label: 'Home', href: '/' }, { label: 'Market overview', href: '/market' }];
  if (!stats) {
    return (
      <ContentPage crumbs={crumbs} title="Market overview">
        {selectors}
        <EmptyState title="The overview is not available right now" action={<Button variant="secondary" href={`/market${filters.year || filters.country ? `?${new URLSearchParams({ ...(filters.year ? { year: String(filters.year) } : {}), ...(filters.country ? { country: filters.country } : {}) })}` : ''}`}>Try again</Button>}>
          The figures are computed by the data service and could not be read. Your choice is kept: try again in a minute, or see the <Link href="/data" className={LINK}>source status</Link>.
        </EmptyState>
      </ContentPage>
    );
  }

  const months = stats.months;
  const inMonths = months.reduce((n, m) => n + m.count, 0);
  const yearOf = stats.year ?? null;
  const where = stats.country ? ` in ${BUYER_COUNTRIES[stats.country] ?? stats.country}` : '';
  const monthsTitle = yearOf ? `Notices published per month, ${yearOf}${where}` : `Notices published per month, last 36 months${where}`;
  const from = formatDateUtc(stats.windowFrom);
  const to = formatDateUtc(stats.windowTo);
  const w = stats.responseWindow;
  const a = stats.amendments;

  return (
    <ContentPage
      wide
      crumbs={crumbs}
      title="Market overview"
      lead="How many defence procurement notices are published, by month, country and subject. Every figure counts notices published: none is contract value, spend or market size."
    >
      {selectors}

      <dl className="facts-grid m-0 border-b border-line">
        <FactCell label={`Notices, ${from} to ${to}${where}`}>{formatNumber(stats.countries.total)}</FactCell>
        <FactCell label={yearOf ? `Notices, ${yearOf}, by month below` : 'Notices, last 36 months'}>{formatNumber(inMonths)}</FactCell>
        <FactCell label="Sources that published them">{stats.sourceCount}</FactCell>
        <FactCell label="Typical response window">
          <span>{daysText(w.median)}</span>
          {w.p25 !== null && w.p75 !== null && <span className="block font-sans text-small font-normal text-ink-muted">Middle half: {w.p25} to {w.p75} {plural(w.p75, 'day')}</span>}
        </FactCell>
        <FactCell label="With an amendment">
          <span>{percentText(a.share)}</span>
          <span className="block font-sans text-small font-normal text-ink-muted">{formatNumber(a.amended)} of {formatNumber(a.notices)} {plural(a.notices, 'notice')}</span>
          <span className="block font-sans text-small font-normal text-ink-muted">Counted only from when we first saw each notice (September 2026 at the earliest), so it will rise as the archive ages.</span>
        </FactCell>
        <FactCell label="Figures as of"><time dateTime={stats.asOf}>{formatDateTimeUtc(stats.asOf)}</time></FactCell>
      </dl>

      <ContentSection title="Notices published per month">
        <BarChart
          id="months"
          title={monthsTitle}
          summary={`Bars for ${monthLabel(months[0]?.month ?? '')} to ${monthLabel(months[months.length - 1]?.month ?? '')}, ${formatNumber(inMonths)} ${plural(inMonths, 'notice')} in all. TED notices and notices from national sources are stacked.`}
          bars={months.map((m) => ({ label: monthLabel(m.month), primary: m.ted, secondary: Math.max(0, m.count - m.ted), partial: m.partial }))}
          primaryName="TED"
          secondaryName="National sources"
          labelHeader="Month"
        />
        <p className={BASIS}>{stats.basis.months}</p>
      </ContentSection>

      <AutoGrid min={460}>
        <ContentSection title="By country">
          <RankTable
            caption={`Notices published by buyer country, ${from} to ${to}`}
            labelHeader="Country"
            total={stats.countries.total}
            rows={[
              ...stats.countries.items.map((c) => ({
                key: c.country,
                // To the notices behind the number: the tender list, this country, every status, the market's own scope (core).
                label: <Link href={`/tenders?country=${c.country}&status=all&scope=core`} className={LINK}><CountryLabel code={c.country} /></Link>,
                count: c.count,
              })),
              ...(stats.countries.other > 0 ? [{ key: 'other', label: <span>Other countries, or none stated</span>, count: stats.countries.other }] : []),
            ]}
          />
          <p className={BASIS}>{stats.basis.countries}</p>
          <p className={BASIS}>
            A country row opens the tender list for that country with the market&rsquo;s own scope (core), every status and every year: the list has no publication-year filter, so a year&rsquo;s count is not reproduced there.
            The Polish figure includes the one-off Atlas dataset, which ends in December 2025, and TED notices before April 2024 are still being re-checked; see{' '}
            <Link href="/data" className={LINK}>source status</Link>.
          </p>
        </ContentSection>

        <ContentSection title="By subject">
          <RankTable
            caption={`Notices published by CPV group, ${from} to ${to}`}
            labelHeader="CPV group"
            rows={stats.cpvGroups.map((g) => {
              const title = cpvGroupName(g.group);
              return {
                key: g.group,
                label: <span><span className="font-mono tabular-nums">{g.group}</span> <span>{title ?? 'Group'}</span></span>,
                count: g.count,
              };
            })}
          />
          <p className={BASIS}>{stats.basis.cpvGroups}</p>
          <p className={BASIS}>
            Titles are from the <Link href="/cpv" className={LINK}>CPV vocabulary</Link>. Groups are the first three digits of a code.
          </p>
        </ContentSection>
      </AutoGrid>

      <ContentSection title="By source">
        <RankTable
          caption={`Notices published by source, ${from} to ${to}`}
          labelHeader="Source"
          total={stats.countries.total}
          rows={stats.sources.map((s) => ({ key: s.id, label: s.name, count: s.count }))}
        />
        <p className={BASIS}>{stats.basis.sources}</p>
      </ContentSection>

      <ContentSection title="Reading these figures" split>
        <ul className="m-0 flex list-disc flex-col gap-2 pl-5 text-body text-ink-muted">
          <li>They are counts of notices published. A notice can be a call for tender, a correction or an award; none states how much is spent.</li>
          <li>Only notices that state the defence and security directive, or carry a military product code, are counted. A military code bought by a municipal, health, education or fire body is not, and neither are notices listed only because their buyer is a defence body, notices whose only signal is the defence directive from a civil buyer, or notices whose only signal is a military product code from a police, prison, border, customs or tax body.</li>
          <li>
            Coverage differs by country and over time. Each source starts on a different date and some countries publish only nationally, so a country with fewer notices is not necessarily one that buys less.
            See <Link href="/data" className={LINK}>source status</Link> for what each source covers and from when.
          </li>
          <li>
            A rise or a fall in one month can be a source added, a backlog loaded or a source that ends, not more or less procurement.
            The national bars drop after December 2025 because the Polish Atlas dataset (January 2024 to December 2025) is a one-off load, not a live portal.
          </li>
          <li>
            The share with an amendment follows the notice page: a later version that changed something other than the publication date. It is counted only from the date we first saw each notice, so it is a floor that cannot be compared with earlier years.
            A correction published as a separate notice is not counted. How notices are collected and classified is in the <Link href="/methodology" className={LINK}>methodology</Link>.
          </li>
          <li>All dates are UTC. Figures are recalculated at most once an hour.</li>
        </ul>
      </ContentSection>
    </ContentPage>
  );
}
