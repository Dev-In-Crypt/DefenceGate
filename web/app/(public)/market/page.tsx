import type { Metadata } from 'next';
import Link from 'next/link';
import { getMarketStats } from '@/lib/api';
import { cpvGroupTitle } from '@/lib/cpv';
import { formatDateTimeUtc, formatDateUtc, formatNumber } from '@/lib/format';
import { daysText, monthLabel, percentText } from '@/lib/market';
import { buildMetadata } from '@/lib/seo';
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

const BASIS = 'text-small text-ink-muted m-0 max-w-[75ch]';
const LINK = 'font-semibold';

export default async function MarketPage() {
  const stats = await getMarketStats();
  const crumbs = [{ label: 'Home', href: '/' }, { label: 'Market overview', href: '/market' }];
  if (!stats) {
    return (
      <ContentPage crumbs={crumbs} title="Market overview">
        <EmptyState title="The overview is not available right now">
          The figures are computed by the data service and could not be read. Try again in a few minutes, or see the <Link href="/data" className={LINK}>source status</Link>.
        </EmptyState>
      </ContentPage>
    );
  }

  const months = stats.months;
  const last36 = months.reduce((n, m) => n + m.count, 0);
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
      <dl className="m-0 grid grid-cols-2 gap-3 rounded-lg bg-surface p-4 lg:grid-cols-3">
        <FactCell label={`Notices, ${from} to ${to}`}>{formatNumber(stats.countries.total)}</FactCell>
        <FactCell label="Notices, last 36 months">{formatNumber(last36)}</FactCell>
        <FactCell label="Sources that published them">{stats.sourceCount}</FactCell>
        <FactCell label="Typical response window">
          <span>{daysText(w.median)}</span>
          {w.p25 !== null && w.p75 !== null && <span className="block font-sans text-small font-normal text-ink-muted">Middle half: {w.p25} to {w.p75} days</span>}
        </FactCell>
        <FactCell label="With an amendment">
          <span>{percentText(a.share)}</span>
          <span className="block font-sans text-small font-normal text-ink-muted">{formatNumber(a.amended)} of {formatNumber(a.notices)} notices</span>
          <span className="block font-sans text-small font-normal text-ink-muted">Counted only from when we first saw each notice (September 2026 at the earliest), so it will rise as the archive ages.</span>
        </FactCell>
        <FactCell label="Figures as of"><time dateTime={stats.asOf}>{formatDateTimeUtc(stats.asOf)}</time></FactCell>
      </dl>

      <ContentSection title="Notices published per month">
        <BarChart
          id="months"
          title="Notices published per month, last 36 months"
          summary={`Bars for ${monthLabel(months[0]?.month ?? '')} to ${monthLabel(months[months.length - 1]?.month ?? '')}, ${formatNumber(last36)} notices in all. TED notices and notices from national sources are stacked.`}
          bars={months.map((m) => ({ label: monthLabel(m.month), primary: m.ted, secondary: Math.max(0, m.count - m.ted), partial: m.partial }))}
          primaryName="TED"
          secondaryName="National sources"
          labelHeader="Month"
        />
        <p className={BASIS}>{stats.basis.months}</p>
      </ContentSection>

      <div className="grid gap-4 lg:grid-cols-2">
        <ContentSection title="By country">
          <RankTable
            caption={`Notices published by buyer country, ${from} to ${to}`}
            labelHeader="Country"
            total={stats.countries.total}
            rows={[
              ...stats.countries.items.map((c) => ({ key: c.country, label: <CountryLabel code={c.country} />, count: c.count })),
              ...(stats.countries.other > 0 ? [{ key: 'other', label: <span>Other countries, or none stated</span>, count: stats.countries.other }] : []),
            ]}
          />
          <p className={BASIS}>{stats.basis.countries}</p>
        </ContentSection>

        <ContentSection title="By subject">
          <RankTable
            caption={`Notices published by CPV group, ${from} to ${to}`}
            labelHeader="CPV group"
            rows={stats.cpvGroups.map((g) => {
              const title = cpvGroupTitle(g.group);
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
      </div>

      <ContentSection title="By source">
        <RankTable
          caption={`Notices published by source, ${from} to ${to}`}
          labelHeader="Source"
          total={stats.countries.total}
          rows={stats.sources.map((s) => ({ key: s.id, label: s.name, count: s.count }))}
        />
        <p className={BASIS}>{stats.basis.sources}</p>
      </ContentSection>

      <ContentSection title="Reading these figures">
        <ul className="m-0 flex list-disc flex-col gap-2 pl-5 text-body text-ink-muted">
          <li>They are counts of notices published. A notice can be a call for tender, a correction or an award; none states how much is spent.</li>
          <li>Only notices that state the defence and security directive, or carry a military product code, are counted. A military code bought by a municipal, health, education or fire body is not, and neither are notices listed only because their buyer is a defence body.</li>
          <li>
            Coverage differs by country and over time. Each source starts on a different date and some countries publish only nationally, so a country with fewer notices is not necessarily one that buys less.
            See <Link href="/data" className={LINK}>source status</Link> for what each source covers and from when.
          </li>
          <li>A rise in one month can be a source added or a backlog loaded, not more procurement.</li>
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
