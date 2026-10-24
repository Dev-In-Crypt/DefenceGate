import type { Metadata } from 'next';
import Link from 'next/link';
import { getMarketStats } from '@/lib/api';
import { MARKET_FIRST_YEAR, PARAM, parseMarketFilters, type SearchParams } from '@/lib/filters';
import { BUYER_COUNTRIES, SCOPE_CHOICES } from '@/lib/taxonomy';
import { Button } from '@/components/dg/button';
import { Select, TextInput } from '@/components/dg/form';
import { cpvGroupName } from '@/lib/cpv';
import { formatDateTimeUtc, formatDateUtc, formatNumber, plural } from '@/lib/format';
import { amendmentsShown, daysText, monthLabel, percentText } from '@/lib/market';
import { buildMetadata } from '@/lib/seo';
import { AutoGrid } from '@/components/dg/auto-grid';
import { AboutData } from '@/components/dg/about-data';
import { BarChart, RankTable } from '@/components/market/charts';
import { ContentPage, ContentSection } from '@/components/dg/content-page';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { EmptyState } from '@/components/dg/feedback';
import { Icon } from '@/components/dg/icon';
import { Download } from 'lucide-react';
import { CoverageNote } from '@/components/dg/coverage-note';
import { DataTable } from '@/components/dg/data-table';
import { moneyLine, valuedShare } from '@/lib/market-money';
import type { MarketMoney, MoneyTotals } from '@/lib/types';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Market overview',
  description: 'How many defence procurement notices are published, by month, country and subject, and the contract values awarded by country, subject and buyer.',
  path: '/market',
});

// WP-88: the basis lines of each chart are in its How we count (components/dg/about-data.tsx).
const LINK = 'font-semibold';

type Props = { searchParams: Promise<SearchParams> };

/** WP-105: the market's contract values: in all, by buyer country, by CPV group and for the buyers with the most valued contracts. */
function Money({ m, basis, cpvLink }: { m: MarketMoney; basis: string; cpvLink: string }) {
  const cell = (t: MoneyTotals) => <td className="text-small" data-money-cell>{moneyLine(t.byCurrency) ?? 'None stated'}</td>;
  const share = (t: MoneyTotals) => <td className="text-small text-ink-muted">{valuedShare(t.of, t.withoutValue)}</td>;
  if (m.total.of === 0) {
    return (
      <p className="m-0 max-w-prose text-body" data-market-money-empty>
        No awarded contract of the supplier map falls in this choice: the contract values cover the award notices of the last three years.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4" data-market-money>
      <p className="m-0 max-w-prose text-body" data-market-money-total>
        {formatDateUtc(m.since)} to {formatDateUtc(m.until)}: <strong>{moneyLine(m.total.byCurrency) ?? 'no contract value stated'}</strong>{' '}
        (of the {formatNumber(m.total.of)} contracts and their winners in the award notices we read, {formatNumber(m.total.of - m.total.withoutValue)} state a contract value).
      </p>
      <AutoGrid min={460}>
        <DataTable label="Contract values awarded by buyer country" minWidth={420}>
          <thead><tr><th scope="col">Buyer country</th><th scope="col">Contract values</th><th scope="col">Coverage</th></tr></thead>
          <tbody>
            {m.byCountry.map((c) => (
              <tr key={c.country} data-money-country={c.country}>
                <th scope="row" className="font-normal"><Link href={`/suppliers?buyerCountry=${c.country}${cpvLink}`} className={LINK}><CountryLabel code={c.country} /></Link></th>
                {cell(c)}{share(c)}
              </tr>
            ))}
          </tbody>
        </DataTable>
        <DataTable label="Contract values awarded by CPV group" minWidth={420}>
          <thead><tr><th scope="col">CPV group</th><th scope="col">Contract values</th><th scope="col">Coverage</th></tr></thead>
          <tbody>
            {m.byCpvGroup.map((g) => (
              <tr key={g.group} data-money-group={g.group}>
                <th scope="row" className="font-normal"><span className="font-mono tabular-nums">{g.group}</span> {cpvGroupName(g.group) ?? 'Group'}</th>
                {cell(g)}{share(g)}
              </tr>
            ))}
          </tbody>
        </DataTable>
      </AutoGrid>
      {m.byBuyer.length > 0 && (
        <DataTable label="Buyers with the most contracts that state a value" minWidth={420}>
          <thead><tr><th scope="col">Buyer</th><th scope="col">Country</th><th scope="col">Contract values</th><th scope="col">Coverage</th></tr></thead>
          <tbody>
            {m.byBuyer.map((b) => (
              <tr key={b.slug} data-money-buyer>
                <th scope="row" className="font-normal"><Link href={`/buyers/${b.slug}`} className={LINK}>{b.name}</Link></th>
                <td>{b.country ? <CountryLabel code={b.country} /> : 'Not stated'}</td>
                {cell(b)}{share(b)}
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
      <AboutData summary="How we count"><p className="m-0" data-money-basis>{basis}</p></AboutData>
    </div>
  );
}

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
      {/* WP-89: the market of one's own products (the tender list's CPV reading) */}
      <TextInput name={PARAM.cpv} maxLength={200} label="CPV code (optional)" placeholder="For example 343 or 34320000" className="sm:min-w-56"
        defaultValue={filters.cpv?.join(', ') ?? ''} />
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
        <EmptyState title="The overview is not available right now" action={<Button variant="secondary" href={`/market${filters.year || filters.country || filters.cpv ? `?${new URLSearchParams({ ...(filters.year ? { year: String(filters.year) } : {}), ...(filters.country ? { country: filters.country } : {}), ...(filters.cpv ? { cpv: filters.cpv.join(',') } : {}) })}` : ''}`}>Try again</Button>}>
          The figures are computed by the data service and could not be read. Your choice is kept: try again in a minute, or see the <Link href="/data" className={LINK}>source status</Link>.
        </EmptyState>
      </ContentPage>
    );
  }

  const months = stats.months;
  const inMonths = months.reduce((n, m) => n + m.count, 0);
  const yearOf = stats.year ?? null;
  const codes = stats.cpv?.length ? stats.cpv : filters.cpv;
  const where = `${stats.country ? ` in ${BUYER_COUNTRIES[stats.country] ?? stats.country}` : ''}${codes?.length ? `, CPV ${codes.join(', ')}` : ''}`;
  const cpvLink = codes?.length ? `&cpv=${codes.join(',')}` : '';
  const monthsTitle = yearOf ? `Notices published per month, ${yearOf}${where}` : `Notices published per month, last 36 months${where}`;
  const from = formatDateUtc(stats.windowFrom);
  const to = formatDateUtc(stats.windowTo);
  const w = stats.responseWindow;
  const a = stats.amendments;
  const watched = amendmentsShown(a, stats.asOf);
  const asked = new URLSearchParams({ ...(filters.year ? { year: String(filters.year) } : {}), ...(filters.country ? { country: filters.country } : {}), ...(filters.cpv?.length ? { cpv: filters.cpv.join(',') } : {}) });
  const marketQuery = asked.size > 0 ? `?${asked.toString()}` : '';

  return (
    <ContentPage
      wide
      crumbs={crumbs}
      title="Market overview"
      lead="How many defence procurement notices are published, by month, country and subject, and the contract values awarded in the contracts we read."
    >
      {selectors}

      {/* WP-96: the set every figure counts, named once beside them, with the tender list of the same set (the list opens on
          All defence and shows a notice published in two sources once, so its default count differs: NL 384 here, 524 there) */}
      <p className="m-0 max-w-prose text-body" data-market-scope>
        Every figure counts notices of <strong>{SCOPE_CHOICES.core.label.toLowerCase()}</strong> only, as each source published them: award notices
        and corrections included, and a notice published in TED and in a national portal counted once per source. The tender list opens
        on {SCOPE_CHOICES.relevant.label} and shows such a notice once, so its default count is not this one.{' '}
        <Link href={`/tenders?${new URLSearchParams({ ...(stats.country ? { country: stats.country } : {}), status: 'all', scope: 'core', ...(codes?.length ? { cpv: codes.join(',') } : {}) })}`} className={LINK}>
          Open {SCOPE_CHOICES.core.label.toLowerCase()} in the tender list
        </Link>.
      </p>

      {/* WP-98b (p06, p07): what we collect for the country, so a small count or a step in the months reads as coverage */}
      <CoverageNote countries={[stats.country ?? filters.country ?? '']} />

      <dl className="facts-grid m-0 border-b border-line">
        <FactCell label={`Notices of ${SCOPE_CHOICES.core.label.toLowerCase()}, ${from} to ${to}${where}`}>{formatNumber(stats.countries.total)}</FactCell>
        <FactCell label={yearOf ? `Notices, ${yearOf}, by month below` : 'Notices, last 36 months'}>{formatNumber(inMonths)}</FactCell>
        <FactCell label="Sources that published them">{stats.sourceCount}</FactCell>
        <FactCell label="Typical response window">
          <span>{daysText(w.median)}</span>
          {w.p25 !== null && w.p75 !== null && <span className="block font-sans text-small font-normal text-ink-muted">Middle half: {w.p25} to {w.p75} {plural(w.p75, 'day')}</span>}
        </FactCell>
        <FactCell label="With an amendment">
          {/* WP-96: the buyer page's rule: a share over a few weeks of watching says nothing, so it waits for six months */}
          {watched.shown ? (
            <>
              <span>{percentText(a.share)}</span>
              <span className="block font-sans text-small font-normal text-ink-muted">{formatNumber(a.amended)} of {formatNumber(a.notices)} {plural(a.notices, 'notice')}</span>
            </>
          ) : (
            <span className="block font-sans text-small font-normal text-ink-muted" data-amendments-pending>
              Not shown yet: we have watched these notices only since {watched.since}, too short to say how often they are amended. Shown after six months.
            </span>
          )}
        </FactCell>
        <FactCell label="Figures as of"><time dateTime={stats.asOf}>{formatDateTimeUtc(stats.asOf)}</time></FactCell>
      </dl>
      {/* WP-100: the tables below as one file, with the sources' licence and attribution on every row */}
      <a href={`/market/export.csv${marketQuery}`} download className="inline-flex min-h-11 items-center gap-2 self-start text-small font-bold" data-market-csv>
        <Icon icon={Download} size="inline" />Download these tables (CSV)
      </a>

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
        <AboutData summary="How we count"><p className="m-0">{stats.basis.months}</p></AboutData>
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
                label: <Link href={`/tenders?country=${c.country}&status=all&scope=core${cpvLink}`} className={LINK}><CountryLabel code={c.country} /></Link>,
                count: c.count,
              })),
              ...(stats.countries.other > 0 ? [{ key: 'other', label: <span>Other countries, or none stated</span>, count: stats.countries.other }] : []),
            ]}
          />
          <AboutData summary="How we count">
          <p className="m-0">{stats.basis.countries}</p>
          <p className="m-0">
            A country row opens the tender list for that country with the market&rsquo;s own scope (core), every status and every year: the list has no publication-year filter, so a year&rsquo;s count is not reproduced there.
            The Polish figure includes the one-off Atlas dataset, which ends in December 2025, and TED notices before April 2024 are still being re-checked; see{' '}
            <Link href="/data" className={LINK}>source status</Link>.
          </p>
          </AboutData>
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
          <AboutData summary="How we count">
          <p className="m-0">{stats.basis.cpvGroups}</p>
          <p className="m-0">
            Titles are from the <Link href="/cpv" className={LINK}>CPV vocabulary</Link>. Groups are the first three digits of a code.
          </p>
          </AboutData>
        </ContentSection>
      </AutoGrid>

      <ContentSection title="By source">
        <RankTable
          caption={`Notices published by source, ${from} to ${to}`}
          labelHeader="Source"
          total={stats.countries.total}
          rows={stats.sources.map((s) => ({ key: s.id, label: s.name, count: s.count }))}
        />
        <AboutData summary="How we count"><p className="m-0">{stats.basis.sources}</p></AboutData>
      </ContentSection>

      {/* WP-105 (p07: "no spending totals by country, CPV or buyer"): the contract values awarded, contracts only, per currency */}
      <ContentSection title="Contract values awarded">
        {stats.money ? <Money m={stats.money} basis={stats.basisMoney ?? ''} cpvLink={cpvLink} /> : (
          <p className="m-0 max-w-prose text-body" data-market-money-none>The contract values are being summed; they are shown once the next computation is stored (within a few hours).</p>
        )}
      </ContentSection>

      <ContentSection title="Reading these figures" split>
        <AboutData summary="What these counts are and are not">
        <ul className="m-0 flex list-disc flex-col gap-2 pl-5">
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
          <li>The share with an amendment is counted only from when we first saw each notice (September 2026 at the earliest), so it will rise as the archive ages.</li>
        </ul>
        </AboutData>
      </ContentSection>
    </ContentPage>
  );
}
