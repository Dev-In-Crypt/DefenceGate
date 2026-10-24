import Link from 'next/link';
import { Rss } from 'lucide-react';
import { DIGEST_COUNTRIES, SECTIONS, cancelledSince, countsSentence, splitByRegime, digestPath, noticesIn, repeatsLabel, restOfTendersHref, truncation, weekLabel, weekOf, type DigestFilters } from '@/lib/digest';
import { now } from '@/lib/deadline';
import { displayName } from '@/lib/display-name';
import { formatDateTimeUtc, formatDateUtc, formatMoney, formatNumber } from '@/lib/format';
import { countryName } from '@/lib/taxonomy';
import type { Digest, DigestCall, DigestTender, DigestWeek } from '@/lib/types';
import type { Crumb } from '@/lib/seo';
import { AutoGrid } from '../dg/auto-grid';
import { Button } from '../dg/button';
import { Card } from '../dg/card';
import { PageHeader } from '../dg/page-header';
import { Select, TextInput } from '../dg/form';
import { Icon } from '../dg/icon';
import { Tag } from '../dg/tag';
import { describeChange } from '../dg/version-timeline';
import { FitBadge, FitFilter, FitItem } from '../funding/fit-badge';

const KIND_WORDS: Record<DigestCall['kind'], string> = {
  'call-new': 'New call', 'call-opened': 'Opened this week', 'call-amended': 'Date moved', 'call-closing': 'Closing soon',
};

/** The deadline of a call as the digest says it: the day, and the opening day for a call that opened. */
function CallDates({ c }: { c: DigestCall }) {
  return (
    <p className="m-0 font-mono text-mono text-ink-muted">
      {c.openingDate && <>Opens <time dateTime={c.openingDate}>{formatDateUtc(c.openingDate)}</time>{c.deadline ? ' · ' : ''}</>}
      {c.deadline ? <>Deadline <time dateTime={c.deadline}>{formatDateUtc(c.deadline)}</time> UTC</> : !c.openingDate ? 'No fixed deadline' : null}
    </p>
  );
}

function CallItem({ c }: { c: DigestCall }) {
  return (
    <Card as="article" className="h-full gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Tag kind="programme">{KIND_WORDS[c.kind]}</Tag>
        <Tag wrap>{c.programmeName}</Tag>
        <Tag>{c.funderCountry}</Tag>
        {c.cascade === true && <Tag>Cascade funding</Tag>}
        <FitBadge id={c.id} />
      </div>
      <h3 className="m-0 break-words text-h3"><Link href={`/funding/${c.slug}`}>{displayName(c.title)}</Link></h3>
      <p className="m-0 text-small font-semibold">{c.funder}</p>
      <CallDates c={c} />
      {c.changes.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-1 p-0">{c.changes.map((l, i) => <li key={`${l.field}-${i}`} className="min-w-0 text-body">{describeChange(l)}</li>)}</ul>
      )}
      {c.eligibility ? (
        <p className="m-0 text-body"><span className="font-semibold">Eligibility, read automatically:</span> {c.eligibility}</p>
      ) : c.eligibilityState === 'no_source' ? null : (
        <p className="m-0 text-small text-ink-muted">Eligibility rules: not read yet. See the call page for the source&rsquo;s own text.</p>
      )}
    </Card>
  );
}

function TenderItem({ t }: { t: DigestTender }) {
  return (
    <Card as="article" className="h-full gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Tag kind="programme">{t.kind === 'new' ? 'New notice' : 'Amended notice'}</Tag>
        {cancelledSince(t) && <span data-cancelled><Tag>Cancelled since</Tag></span>}
        {t.country && <Tag>{t.country}</Tag>}
        {repeatsLabel(t.repeats) && <Tag><span aria-hidden="true">{repeatsLabel(t.repeats)}</span><span className="sr-only">{t.repeats} identical notices</span></Tag>}
        <time dateTime={t.day} className="ml-auto font-mono text-mono text-ink-muted">{formatDateUtc(`${t.day}T00:00:00Z`)}</time>
      </div>
      <h3 className="m-0 break-words text-h3"><Link href={`/tenders/${t.slug}`}>{displayName(t.title)}</Link></h3>
      <p className="m-0 text-small font-semibold">{t.buyerName}{t.country ? ` (${countryName(t.country)})` : ''}</p>
      <p className="m-0 font-mono text-mono text-ink-muted">
        {t.deadline ? <>Deadline <time dateTime={t.deadline}>{formatDateUtc(t.deadline)}</time> UTC</> : 'No deadline stated'}
        {t.estimatedValue ? <> · {formatMoney(t.estimatedValue)}</> : null}
      </p>
      {t.changes.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-1 p-0">{t.changes.map((l, i) => <li key={`${l.field}-${i}`} className="min-w-0 text-body">{describeChange(l)}</li>)}</ul>
      )}
    </Card>
  );
}

/**
 * One issue of the weekly digest. The same page for /digest (the latest issue) and /digest/[week].
 * `basePath` is where the country filter submits to; `feedHref` is the Atom feed for the same country.
 */
/** WP-87: a section's defence calls, then its dual-use calls under their own heading (never dropped, never first). */
function CallParts({ calls }: { calls: DigestCall[] }) {
  const { defence, dualUse } = splitByRegime(calls);
  const grid = (list: DigestCall[]) => (
    <AutoGrid as="ul" min={420} pairs>
      {list.map((it) => <FitItem key={`${it.kind}-${it.id}`} id={it.id} className="min-w-0"><CallItem c={it} /></FitItem>)}
    </AutoGrid>
  );
  return (
    <>
      {defence.length > 0 && grid(defence)}
      {dualUse.length > 0 && (
        <div className="flex flex-col gap-3" data-dual-use>
          <h3 className="m-0 text-body font-semibold">Dual-use calls <span className="font-mono tabular-nums text-ink-muted">({formatNumber(dualUse.length)})</span></h3>
          {grid(dualUse)}
        </div>
      )}
    </>
  );
}

export function DigestView({ issue, filters, basePath, feedHref, crumbs, notices }: {
  issue: Digest; filters: DigestFilters; basePath: string; feedHref: string; crumbs: Crumb[];
  /** Status lines about the data, shown under the page header. */
  notices?: React.ReactNode;
}) {
  const c = issue.counts;
  const country = filters.country ? DIGEST_COUNTRIES[filters.country] ?? filters.country : null;
  const empty = c.tendersNew + c.tendersAmended + c.callsNew + c.callsAmended + c.callsOpened + c.callsClosing === 0;
  const fundingQuiet = c.callsNew + c.callsAmended + c.callsOpened === 0;
  return (
    <>
      <PageHeader crumbs={crumbs} title="Weekly digest"
        sub={<><time dateTime={issue.weekFrom}>{weekLabel(issue.week)}</time>{country ? ` · ${country}` : ''}</>}
        lead={<>
          What was new and what changed in the week, from the same archive as <Link href="/changes" className="font-semibold">What changed</Link> and the{' '}
          <Link href="/funding" className="font-semibold">funding calls</Link>: new and amended defence notices, funding calls that appeared, opened or had a date moved, calls closing in
          the two weeks after, and calls with cascade funding. Each item links to its page, which links to the source. No account is needed.
        </>} />
      {notices}

      {/* Text and counts at the left (one measure), the ways to follow at the right: the card is filled, not a strip of text in a wide box. */}
      <section aria-labelledby="numbers" className="grid gap-x-10 gap-y-4 rounded-lg border border-transparent bg-surface p-5 sm:p-7 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div className="flex min-w-0 flex-col gap-3">
        <h2 id="numbers" className="m-0 text-h3">The week in numbers</h2>
        <p className="m-0 max-w-prose text-body">{countsSentence(issue)}</p>
        <ul className="m-0 flex list-none flex-wrap gap-x-6 p-0 text-small">
          {SECTIONS.map((s) => (
            <li key={s.id}><a href={`#${s.id}`} className="inline-flex min-h-8 items-center font-semibold">{s.title}</a> <span className="font-mono tabular-nums text-ink-muted">{formatNumber(c[s.count])}</span></li>
          ))}
        </ul>
        <p className="m-0 max-w-prose text-small text-ink-muted">
          Counted over the days {formatDateUtc(issue.weekFrom)} to {formatDateUtc(new Date(new Date(issue.weekTo).getTime() - 1).toISOString())} (UTC).
          Calls closing are those whose deadline falls before {formatDateUtc(issue.closingUntil)}. Built {formatDateTimeUtc(issue.generatedAt)}.
          A deadline or status can have moved since; the call page is current.
          {issue.cascadeOpenNow > 0 && <> {formatNumber(issue.cascadeOpenNow)} open {issue.cascadeOpenNow === 1 ? 'call has' : 'calls have'} cascade funding today: <Link href="/funding?cascade=true" className="font-semibold">see them</Link>.</>}
        </p>
        </div>
        <nav aria-label="Follow the digest" className="flex flex-col lg:border-l lg:border-line lg:pl-6">
          <a href={feedHref} className="inline-flex min-h-11 items-center gap-2 text-small font-bold"><Icon icon={Rss} size="inline" />Atom feed of the weekly digest</a>
          {/* WP-90: the week under way, which has no issue yet: its changes so far */}
          <Link href={`/changes?week=${weekOf(now())}`} className="inline-flex min-h-11 items-center text-small font-bold" data-week-so-far>This week so far, in What changed</Link>
          <Link href="/changes" className="inline-flex min-h-11 items-center text-small font-bold">What changed (the last 14 days)</Link>
          <a href="#earlier" className="inline-flex min-h-11 items-center text-small font-bold">Earlier weeks</a>
        </nav>
      </section>

      <form method="get" action={basePath} role="search" aria-label="Filter the digest" className="flex flex-col gap-4 rounded-lg border border-transparent bg-surface p-5 sm:flex-row sm:items-end">
        <Select name="country" label="Country" placeholder="All countries" defaultValue={filters.country ?? ''} className="sm:min-w-64"
          hint="A notice’s buyer country, or the funder country of a call."
          options={Object.entries(DIGEST_COUNTRIES).map(([code, name]) => ({ value: code, label: `${name} (${code})` }))} />
        {/* WP-106 (p04): the tender sections by product code, read as the tender list reads `cpv` */}
        <TextInput name="cpv" maxLength={200} label="CPV code" placeholder="For example 353, 2461" defaultValue={filters.cpv?.join(', ') ?? ''}
          className="sm:min-w-48" hint="Narrows the notices; funding calls have no code." />
        <div className="flex items-center gap-3">
          <Button type="submit">Apply</Button>
          <Link href={basePath} className="inline-flex min-h-11 items-center text-small font-bold">Clear</Link>
        </div>
      </form>

      <details className="rounded-lg border border-transparent bg-surface px-5 sm:px-7">
        <summary className="flex min-h-12 cursor-pointer items-center py-3 text-body font-semibold">What “new” means here</summary>
        <div className="flex max-w-prose flex-col gap-2 pb-4 text-small">
          <p className="m-0"><strong>A new notice</strong> is one our archive collected for the first time in this week and that was published in it, or up to two days before it (TED notices are collected after their publication date). A notice that was published earlier and that we read in later is not new.</p>
          <p className="m-0"><strong>A new funding call</strong> is one collected for the first time in this week and published, or opened, no earlier than two days before it: a source’s first load of old calls is not news.</p>
          <p className="m-0">Our archive began in September 2026, so a call or notice that existed before then is never new here, only changed. This page shows the last complete week; the current week appears when it ends, and <Link href="/changes" className="font-semibold">What changed</Link> covers the last 14 days.</p>
        </div>
      </details>

      <FitFilter />

      {(issue.cpv?.length ?? 0) > 0 && (
        <p role="status" className="m-0 max-w-prose rounded-md bg-surface-inset px-4 py-3 text-small text-ink" data-digest-cpv>
          The notices are those with a CPV code under {issue.cpv!.join(', ')}. Funding calls have no product code: they are all listed, as without the filter.
        </p>
      )}

      {fundingQuiet && (
        <p role="status" className="m-0 max-w-prose rounded-md bg-surface-inset px-4 py-3 text-small text-ink">
          No funding call was new, opened or had a date moved{country ? ` for ${country}` : ''} in this week. That is a statement about this week only: calls that were already listed before it
          are not new even when they are open. {c.callsClosing > 0 ? `${formatNumber(c.callsClosing)} ${c.callsClosing === 1 ? 'call closes' : 'calls close'} within the next 14 days (below). ` : ''}
          The <Link href="/funding" className="font-semibold">funding list</Link> shows every open call.
        </p>
      )}

      {empty && (
        <p role="status" className="m-0 max-w-prose rounded-md bg-surface-inset px-4 py-3 text-small text-ink">
          Nothing was recorded for {country ?? 'any country'} in this week. Notices are collected once a day, so a quiet week is possible.
        </p>
      )}

      {SECTIONS.map((s) => {
        const items = issue[s.list] as (DigestCall | DigestTender)[];
        const n = c[s.count];
        const isTender = s.list === 'tendersNew' || s.list === 'tendersAmended';
        // A row that stands for 13 identical notices is 13 of the count (the API merges them; `repeats` says how many).
        const cut = truncation(isTender ? noticesIn(items as DigestTender[]) : items.length, n);
        return (
          <section key={s.id} id={s.id} aria-labelledby={`${s.id}-h`} className="flex flex-col gap-3">
            <h2 id={`${s.id}-h`} className="m-0 text-h3">{s.title} <span className="font-mono tabular-nums text-ink-muted">({formatNumber(n)})</span></h2>
            {s.id === 'cascade' && (
              <p className="m-0 max-w-prose text-small text-ink-muted">
                Calls whose document or conditions say the funded projects may pass money to third parties, among those listed above. See the{' '}
                <Link href="/glossary#cascade-funding" className="font-semibold">glossary</Link>. A call not marked here may simply not say.
              </p>
            )}
            {items.length === 0 ? (
              <p className="m-0 text-body text-ink-muted">None{country ? ` for ${country}` : ''} this week.</p>
            ) : isTender ? (
              <AutoGrid as="ul" min={420} pairs>
                {items.map((it) => <li key={`${it.kind}-${it.id}`} className="min-w-0"><TenderItem t={it as DigestTender} /></li>)}
              </AutoGrid>
            ) : (
              <CallParts calls={items as DigestCall[]} />
            )}
            {cut && (
              <p className="m-0 text-small text-ink-muted">
                {cut} {isTender
                  ? <>The <Link href={restOfTendersHref(issue.week, s.list === 'tendersNew' ? 'new' : 'amended', filters.country, filters.cpv)} className="font-semibold">list of changes of this week</Link> has the rest.</>
                  : <>The <Link href="/funding" className="font-semibold">funding list</Link> has the rest.</>}
              </p>
            )}
          </section>
        );
      })}

      <nav aria-label="Other weeks" className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        {issue.previousWeek ? <Link href={digestPath(issue.previousWeek, filters)} className="inline-flex min-h-11 items-center font-bold">&larr; {weekLabel(issue.previousWeek)}</Link> : <span />}
        {issue.nextWeek ? <Link href={digestPath(issue.nextWeek, filters)} className="inline-flex min-h-11 items-center font-bold">{weekLabel(issue.nextWeek)} &rarr;</Link> : <span />}
      </nav>
    </>
  );
}

/** The earlier issues, newest first, with the counts of those already stored. */
export function WeekList({ weeks, current, filters }: { weeks: DigestWeek[]; current: string; filters: DigestFilters }) {
  if (weeks.length === 0) return null;
  return (
    <section id="earlier" aria-labelledby="earlier-h" className="flex flex-col gap-3">
      <h2 id="earlier-h" className="m-0 text-h3">Earlier weeks</h2>
      <ul className="m-0 flex list-none flex-col gap-1 p-0">
        {weeks.map((w) => (
          <li key={w.week}>
            {w.week === current ? (
              <span className="inline-flex min-h-11 items-center font-semibold" aria-current="page">{weekLabel(w.week)}</span>
            ) : (
              <Link href={digestPath(w.week, filters)} className="inline-flex min-h-11 items-center font-semibold">{weekLabel(w.week)}</Link>
            )}
            {w.counts && <span className="ml-2 text-small text-ink-muted">{formatNumber(w.counts.callsNew)} new calls, {formatNumber(w.counts.tendersNew)} new notices</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
