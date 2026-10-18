import Link from 'next/link';
import { Rss } from 'lucide-react';
import { DIGEST_COUNTRIES, SECTIONS, countsSentence, digestPath, truncation, weekLabel, type DigestFilters } from '@/lib/digest';
import { displayName } from '@/lib/display-name';
import { formatDateTimeUtc, formatDateUtc, formatMoney, formatNumber } from '@/lib/format';
import { countryName } from '@/lib/taxonomy';
import type { Digest, DigestCall, DigestTender, DigestWeek } from '@/lib/types';
import { cn } from '@/lib/utils';
import { Button } from '../dg/button';
import { Select } from '../dg/form';
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
    <article className="flex flex-col gap-2 rounded-lg bg-surface p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Tag kind="programme">{KIND_WORDS[c.kind]}</Tag>
        <Tag>{c.programmeName}</Tag>
        <Tag>{c.funderCountry}</Tag>
        {c.cascade === true && <Tag>Cascade funding</Tag>}
        <FitBadge id={c.id} />
      </div>
      <h3 className="m-0 break-words text-[20px] font-bold leading-[28px] tracking-[-0.4px]"><Link href={`/funding/${c.slug}`}>{displayName(c.title)}</Link></h3>
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
    </article>
  );
}

function TenderItem({ t }: { t: DigestTender }) {
  return (
    <article className="flex flex-col gap-2 rounded-lg bg-surface p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Tag kind="programme">{t.kind === 'new' ? 'New notice' : 'Amended notice'}</Tag>
        {t.country && <Tag>{t.country}</Tag>}
        <time dateTime={t.day} className="ml-auto font-mono text-mono text-ink-muted">{formatDateUtc(`${t.day}T00:00:00Z`)}</time>
      </div>
      <h3 className="m-0 break-words text-[20px] font-bold leading-[28px] tracking-[-0.4px]"><Link href={`/tenders/${t.slug}`}>{displayName(t.title)}</Link></h3>
      <p className="m-0 text-small font-semibold">{t.buyerName}{t.country ? ` (${countryName(t.country)})` : ''}</p>
      <p className="m-0 font-mono text-mono text-ink-muted">
        {t.deadline ? <>Deadline <time dateTime={t.deadline}>{formatDateUtc(t.deadline)}</time> UTC</> : 'No deadline stated'}
        {t.estimatedValue ? <> · {formatMoney(t.estimatedValue)}</> : null}
      </p>
      {t.changes.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-1 p-0">{t.changes.map((l, i) => <li key={`${l.field}-${i}`} className="min-w-0 text-body">{describeChange(l)}</li>)}</ul>
      )}
    </article>
  );
}

/**
 * One issue of the weekly digest. The same page for /digest (the latest issue) and /digest/[week].
 * `basePath` is where the country filter submits to; `feedHref` is the Atom feed for the same country.
 */
export function DigestView({ issue, filters, basePath, feedHref }: { issue: Digest; filters: DigestFilters; basePath: string; feedHref: string }) {
  const c = issue.counts;
  const country = filters.country ? DIGEST_COUNTRIES[filters.country] ?? filters.country : null;
  const empty = c.tendersNew + c.tendersAmended + c.callsNew + c.callsAmended + c.callsOpened + c.callsClosing === 0;
  const fundingQuiet = c.callsNew + c.callsAmended + c.callsOpened === 0;
  return (
    <>
      <header className="flex flex-col gap-3">
        <h1 className="m-0 text-[32px] font-extrabold leading-10 tracking-[-1px] md:text-h1">Weekly digest</h1>
        <p className="m-0 text-h3">
          <time dateTime={issue.weekFrom}>{weekLabel(issue.week)}</time>{country ? ` · ${country}` : ''}
        </p>
        <p className="m-0 max-w-[62ch] text-body text-ink-muted">
          What was new and what changed in the week, from the same archive as <Link href="/changes" className="font-semibold">What changed</Link> and the{' '}
          <Link href="/funding" className="font-semibold">funding calls</Link>: new and amended defence notices, funding calls that appeared, opened or had a date moved, calls closing in
          the two weeks after, and calls with cascade funding. Each item links to its page, which links to the source. No account is needed.
        </p>
      </header>

      <section aria-labelledby="numbers" className="flex flex-col gap-3 rounded-lg bg-surface p-5 sm:p-6">
        <h2 id="numbers" className="m-0 text-h3">The week in numbers</h2>
        <p className="m-0 text-body">{countsSentence(issue)}</p>
        <ul className="m-0 flex list-none flex-wrap gap-x-6 gap-y-1 p-0 text-small">
          {SECTIONS.map((s) => (
            <li key={s.id}><a href={`#${s.id}`} className="font-semibold">{s.title}</a> <span className="font-mono tabular-nums text-ink-muted">{formatNumber(c[s.count])}</span></li>
          ))}
        </ul>
        <p className="m-0 text-small text-ink-muted">
          Counted over the days {formatDateUtc(issue.weekFrom)} to {formatDateUtc(new Date(new Date(issue.weekTo).getTime() - 1).toISOString())} (UTC).
          Calls closing are those whose deadline falls before {formatDateUtc(issue.closingUntil)}. Built {formatDateTimeUtc(issue.generatedAt)}.
          A deadline or status can have moved since; the call page is current.
          {issue.cascadeOpenNow > 0 && <> {formatNumber(issue.cascadeOpenNow)} open {issue.cascadeOpenNow === 1 ? 'call has' : 'calls have'} cascade funding today: <Link href="/funding?cascade=true" className="font-semibold">see them</Link>.</>}
        </p>
        <div className="flex flex-wrap gap-x-6">
          <a href={feedHref} className="inline-flex min-h-11 items-center gap-2 text-small font-bold"><Icon icon={Rss} size="inline" />Atom feed of the weekly digest</a>
          <Link href="/changes" className="inline-flex min-h-11 items-center text-small font-bold">What changed (the last 14 days)</Link>
          <a href="#earlier" className="inline-flex min-h-11 items-center text-small font-bold">Earlier weeks</a>
        </div>
      </section>

      <form method="get" action={basePath} role="search" aria-label="Filter the digest" className="flex flex-col gap-4 rounded-lg bg-surface p-5 sm:flex-row sm:items-end">
        <Select name="country" label="Country" placeholder="All countries" defaultValue={filters.country ?? ''} className="sm:min-w-64"
          hint="A notice’s buyer country, or the funder country of a call."
          options={Object.entries(DIGEST_COUNTRIES).map(([code, name]) => ({ value: code, label: `${name} (${code})` }))} />
        <div className="flex items-center gap-3">
          <Button type="submit">Apply</Button>
          <Link href={basePath} className="inline-flex min-h-11 items-center text-small font-bold">Clear</Link>
        </div>
      </form>

      <details className="rounded-lg bg-surface px-5 sm:px-6">
        <summary className="flex min-h-12 cursor-pointer items-center py-3 text-body font-semibold">What “new” means here</summary>
        <div className="flex flex-col gap-2 pb-4 text-small">
          <p className="m-0"><strong>A new notice</strong> is one our archive collected for the first time in this week and that was published in it, or up to two days before it (TED notices are collected after their publication date). A notice that was published earlier and that we read in later is not new.</p>
          <p className="m-0"><strong>A new funding call</strong> is one collected for the first time in this week and published, or opened, no earlier than two days before it: a source’s first load of old calls is not news.</p>
          <p className="m-0">Our archive began in September 2026, so a call or notice that existed before then is never new here, only changed. This page shows the last complete week; the current week appears when it ends, and <Link href="/changes" className="font-semibold">What changed</Link> covers the last 14 days.</p>
        </div>
      </details>

      <FitFilter />

      {fundingQuiet && (
        <p role="status" className="m-0 rounded-md bg-surface-inset px-4 py-3 text-small text-ink">
          No funding call was new, opened or had a date moved{country ? ` for ${country}` : ''} in this week. That is a statement about this week only: calls that were already listed before it
          are not new even when they are open. {c.callsClosing > 0 ? `${formatNumber(c.callsClosing)} ${c.callsClosing === 1 ? 'call closes' : 'calls close'} within the next 14 days (below). ` : ''}
          The <Link href="/funding" className="font-semibold">funding list</Link> shows every open call.
        </p>
      )}

      {empty && (
        <p role="status" className="m-0 rounded-md bg-surface-inset px-4 py-3 text-small text-ink">
          Nothing was recorded for {country ?? 'any country'} in this week. Notices are collected once a day, so a quiet week is possible.
        </p>
      )}

      {SECTIONS.map((s) => {
        const items = issue[s.list] as (DigestCall | DigestTender)[];
        const n = c[s.count];
        const cut = truncation(items.length, n);
        const isTender = s.list === 'tendersNew' || s.list === 'tendersAmended';
        return (
          <section key={s.id} id={s.id} aria-labelledby={`${s.id}-h`} className="flex flex-col gap-3">
            <h2 id={`${s.id}-h`} className="m-0 text-h3">{s.title} <span className="font-mono tabular-nums text-ink-muted">({formatNumber(n)})</span></h2>
            {s.id === 'cascade' && (
              <p className="m-0 text-small text-ink-muted">
                Calls whose document or conditions say the funded projects may pass money to third parties, among those listed above. See the{' '}
                <Link href="/glossary#cascade-funding" className="font-semibold">glossary</Link>. A call not marked here may simply not say.
              </p>
            )}
            {items.length === 0 ? (
              <p className="m-0 text-body text-ink-muted">None{country ? ` for ${country}` : ''} this week.</p>
            ) : (
              <ul className={cn('m-0 flex list-none flex-col gap-3 p-0')}>
                {items.map((it) => (isTender
                  ? <li key={`${it.kind}-${it.id}`}><TenderItem t={it as DigestTender} /></li>
                  : <FitItem key={`${it.kind}-${it.id}`} id={it.id}><CallItem c={it as DigestCall} /></FitItem>))}
              </ul>
            )}
            {cut && (
              <p className="m-0 text-small text-ink-muted">
                {cut} {isTender ? <>The <Link href="/tenders" className="font-semibold">tender list</Link> has the rest.</> : <>The <Link href="/funding" className="font-semibold">funding list</Link> has the rest.</>}
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
