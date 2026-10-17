import Link from 'next/link';
import { TriangleAlert } from 'lucide-react';
import { cn } from '@/lib/utils';
import { callStatusKind, getCallDeadline, getTenderDeadline, localDeadline, now } from '@/lib/deadline';
import { formatDateUtc, funderLine, isPlaceholderAmount, openingPhrase, variantsLine } from '@/lib/format';
import { TENDER_CHANGED_LABEL, anomalyNotes, isLongRunning, tenderStatusView } from '@/lib/tender-status';
import { PROGRAMMES, REGIMES, isNonEnglish } from '@/lib/taxonomy';
import { displayName } from '@/lib/display-name';
import { cpvLabel } from '@/lib/taxonomy';
import { matchedCpv } from '@/lib/tender-basis';
import type { Buyer, Call, Tender } from '@/lib/types';
import { Tag, StatusPill } from './tag';
import { AmountDisplay, CountryLabel, FactCell, LangLabel } from './data-display';
import { Icon } from './icon';
import { SourceBadge } from './source-badge';
import { BasisChips } from './basis-chips';
import { FitBadge } from '../funding/fit-badge';

const CARD = 'group relative flex flex-col gap-5 rounded-lg border-strong border-transparent bg-surface p-5 transition-colors duration-dg hover:border-ink-muted sm:p-6';
const TITLE_LINK = 'break-words text-inherit no-underline decoration-2 underline-offset-4 group-hover:underline after:absolute after:inset-0 after:rounded-lg after:content-[""]';

/** Whole card is one link (stretched title). "View original" sits above it. */
export function CallCard({ call, headingLevel = 'h2', budgetRepeated = false }: {
  call: Call; headingLevel?: 'h2' | 'h3';
  /** The call-level budget already appeared on an earlier card of this list: say it is shared instead of repeating it. */
  budgetRepeated?: boolean;
}) {
  const d = getCallDeadline(call);
  const closed = d.state === 'closed';
  const upcoming = call.status === 'forthcoming';
  // A call that has not opened yet is not under time pressure, whatever its deadline.
  const soon = !upcoming && (d.state === 'soon' || d.state === 'urgent');
  const nonEnglish = isNonEnglish(call.titleLanguage);
  const H = headingLevel;
  return (
    <article className={cn(CARD, closed ? 'text-ink-muted' : 'text-ink')}>
      <div className="flex flex-wrap items-center gap-2">
        <Tag kind="programme">{PROGRAMMES[call.programme].label}</Tag>
        <Tag>{REGIMES[call.regime]}</Tag>
        <Tag>{call.funderCountry}</Tag>
        {call.cascade === true && <Tag>Cascade funding</Tag>}
        <FitBadge id={call.id} />
        <span className="ml-auto"><StatusPill status={callStatusKind(call.status, d.state, call.openingDate)} /></span>
      </div>
      <div className="flex flex-col gap-1">
        <H lang={nonEnglish ? call.titleLanguage : undefined} className="m-0 text-[22px] font-bold leading-[30px] tracking-[-0.5px] sm:text-h2">
          <Link href={`/funding/${call.slug}`} className={TITLE_LINK}>{displayName(call.title)}</Link>
        </H>
        {nonEnglish && <LangLabel kind="language" code={call.titleLanguage} />}
        {call.originalTitle && (
          <span className="text-small text-ink-muted">
            <span lang={call.originalLanguage ?? undefined}>{displayName(call.originalTitle)}</span>
            {' · '}<LangLabel kind="title" code={call.originalLanguage} />
          </span>
        )}
        <span className="text-small text-ink-muted">{funderLine(call)}</span>
      </div>
      {call.status === 'open' && call.sourceStatus === 'forthcoming' && (
        <p className="m-0 text-small text-ink-muted">The source still lists this call as forthcoming; its opening date has passed and its deadline is ahead.</p>
      )}
      {upcoming && call.openingDate && (
        <p className="m-0 text-body font-bold text-ink">
          {openingPhrase(call.openingDate, now()).lead}{' '}
          <time dateTime={call.openingDate}>{openingPhrase(call.openingDate, now()).date}</time>
        </p>
      )}
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3">
        <FactCell label={d.rolling ? 'Submission' : soon ? 'Closing soon' : 'Deadline'} tone={soon ? 'soon' : closed ? 'closed' : 'default'}>
          {d.rolling && d.iso ? (
            <>
              <span className="font-sans">Open: rolling submission</span>
              <div className="font-sans text-small font-normal text-ink-muted">Last cut-off <time dateTime={d.iso}>{d.utc}</time></div>
            </>
          ) : d.iso ? (
            <>
              <time dateTime={d.iso}>{d.utc}</time>
              {/* No countdown before the call opens, and none without a deadline. */}
              {!upcoming && d.countdown && (
                <div className={cn('font-sans text-small font-bold', closed ? 'text-ink-muted' : soon ? 'text-soon-fg' : 'text-accent-text')}>{d.countdown}</div>
              )}
            </>
          ) : (
            <span className="font-sans">{closed ? 'Closed' : 'No fixed deadline'}</span>
          )}
        </FactCell>
        <FactCell label={call.budgetScope === 'call' ? 'Call budget' : call.budgetScope === 'topic' ? 'Topic budget' : 'Budget'} tone={closed ? 'closed' : 'default'}>
          {budgetRepeated ? (
            <span className="font-sans text-body text-ink-muted">Shared with the other topics of this call</span>
          ) : (
            <>
              <AmountDisplay money={call.budget} />
              {call.budget && call.budgetScope === 'call' && (
                <div className="font-sans text-small font-normal text-ink-muted">Shared by several topics of this call</div>
              )}
            </>
          )}
        </FactCell>
        <FactCell label={call.callId ? 'Call ID' : 'Source ID'} tone={closed ? 'closed' : 'default'}>{call.callId ?? call.topicId}</FactCell>
      </dl>
      <SourceBadge source={call.source} variant="inline" />
    </article>
  );
}

/**
 * Status pills of a tender: Amended (when it changed), then the effective status in words
 * (Open, Closing soon, Closed, Awarded, Cancelled, Planned, Status unknown). See lib/tender-status.ts.
 */
export function TenderStatusPills({ tender }: { tender: Tender }) {
  const s = tenderStatusView(tender);
  return (
    <>
      {tender.amended && <StatusPill status="amended" />}
      <StatusPill status={s.kind}>{s.label}</StatusPill>
    </>
  );
}

/** What looks wrong in the source's own dates, in words. Renders nothing without a known anomaly. */
export function AnomalyNote({ tender, className }: { tender: Pick<Tender, 'anomalies'>; className?: string }) {
  const notes = anomalyNotes(tender);
  if (notes.length === 0) return null;
  return (
    <div className={cn('flex flex-col gap-0.5 text-small text-ink-muted', className)}>
      {notes.map((n) => (
        <p key={n} className="m-0 flex items-start gap-1.5"><Icon icon={TriangleAlert} size="inline" className="mt-0.5 shrink-0" /><span>{n}</span></p>
      ))}
    </div>
  );
}

/** Whole card is one link (stretched title). The buyer link and "View original" sit above it. */
export function TenderCard({ tender, headingLevel = 'h2', cpvFilter, valueNote }: {
  tender: Tender; headingLevel?: 'h2' | 'h3';
  /** The CPV prefixes the list is filtered by: a notice found through an additional code says so. */
  cpvFilter?: string[];
  /** Why the value is missing for this source ("Not stated by the buyer in 82 % of notices from this source"). */
  valueNote?: string | null;
}) {
  const d = getTenderDeadline(tender);
  const local = d.state === 'closed' ? null : localDeadline(d.iso, tender.country, d.dateOnly);
  const matched = matchedCpv(tender, cpvFilter);
  const mainName = tender.cpv ? cpvLabel(tender.cpv) : null;
  const closed = d.state === 'closed';
  const soon = d.state === 'soon' || d.state === 'urgent';
  const longRunning = isLongRunning(tender) && !closed;
  const nonEnglish = isNonEnglish(tender.titleLanguage);
  const H = headingLevel;
  return (
    <article className={cn(CARD, closed ? 'text-ink-muted' : 'text-ink')}>
      <div className="flex flex-wrap items-center gap-2">
        {tender.cpv && <Tag kind="programme">CPV {tender.cpv}</Tag>}
        {mainName && <span className="text-small text-ink-muted">{mainName.label}</span>}
        {tender.country && <Tag>{tender.country}</Tag>}
        <span className="ml-auto flex flex-wrap gap-2"><TenderStatusPills tender={tender} /></span>
      </div>
      {matched.length > 0 && (
        <p className="m-0 text-small text-ink-muted">
          Matches your code filter through {matched.length === 1 ? 'an additional code' : 'additional codes'}:{' '}
          {matched.map((c, i) => <span key={c}>{i > 0 && ', '}<span className="font-mono text-mono-strong">{c}</span>{cpvLabel(c) ? ` (${cpvLabel(c)?.label})` : ''}</span>)}
        </p>
      )}
      <div className="flex flex-col gap-1">
        <H lang={nonEnglish ? (tender.titleLanguage ?? undefined) : undefined} className="m-0 text-[22px] font-bold leading-[30px] tracking-[-0.5px] sm:text-h2">
          <Link href={`/tenders/${tender.slug}`} className={TITLE_LINK}>{displayName(tender.title)}</Link>
        </H>
        {nonEnglish && <LangLabel kind="language" code={tender.titleLanguage} />}
        {tender.originalTitle && (
          <span className="text-small text-ink-muted">
            <span lang={tender.originalLanguage ?? undefined}>{displayName(tender.originalTitle)}</span>
            {' · '}<LangLabel kind="title" code={tender.originalLanguage} />
          </span>
        )}
        {tender.buyerSlug ? (
          <Link href={`/buyers/${tender.buyerSlug}`} className="relative z-10 self-start text-small font-semibold">{displayName(tender.buyerName, 'title')}</Link>
        ) : (
          <span className="text-small font-semibold">{displayName(tender.buyerName, 'title')}</span>
        )}
      </div>
      <BasisChips tender={tender} lifted />
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3">
        <FactCell label={soon ? 'Closing soon' : longRunning ? 'Open until (long-running)' : 'Deadline'} tone={soon ? 'soon' : closed ? 'closed' : 'default'}>
          {d.iso ? (
            <>
              <time dateTime={d.iso}>{d.utc}</time>
              {local && <div className="font-sans text-small font-normal text-ink-muted">{local}</div>}
              {d.countdown && (
                <div className={cn('font-sans text-small font-bold', closed ? 'text-ink-muted' : soon ? 'text-soon-fg' : 'text-accent-text')}>{d.countdown}</div>
              )}
            </>
          ) : (
            <span className="font-sans">{closed ? 'Closed' : 'No deadline stated'}</span>
          )}
        </FactCell>
        <FactCell label="Estimated value" tone={closed ? 'closed' : 'default'}>
          <AmountDisplay money={tender.estimatedValue} />
          {valueNote && (!tender.estimatedValue || isPlaceholderAmount(tender.estimatedValue.amount)) && (
            <div className="font-sans text-small font-normal text-ink-muted">{valueNote}</div>
          )}
          {tender.estimatedValue && !isPlaceholderAmount(tender.estimatedValue.amount) && tender.valueKind === 'lot_sum' && (
            <div className="font-sans text-small font-normal text-ink-muted">Sum of the values the notice states for its lots</div>
          )}
        </FactCell>
        <FactCell label="Notice ID" tone={closed ? 'closed' : 'default'}>{tender.noticeId}</FactCell>
      </dl>
      <AnomalyNote tender={tender} />
      <SourceBadge source={tender.source} variant="inline" retrievedLabel={TENDER_CHANGED_LABEL} />
    </article>
  );
}

/** A procurement body. Counts are core-scope notices only (API_CONTRACT.md). */
export function BuyerCard({ buyer, headingLevel = 'h2' }: { buyer: Buyer; headingLevel?: 'h2' | 'h3' }) {
  const H = headingLevel;
  const variants = variantsLine(buyer.nameVariants);
  return (
    <article className={cn(CARD, 'text-ink')}>
      <div className="flex flex-col gap-2">
        {buyer.isDefenceBuyer && <span className="self-start"><Tag>Defence body</Tag></span>}
        <H className="m-0 text-[22px] font-bold leading-[30px] tracking-[-0.5px] sm:text-h2">
          <Link href={`/buyers/${buyer.slug}`} className={TITLE_LINK}>{displayName(buyer.name, 'title')}</Link>
        </H>
        {buyer.country && <span className="text-small text-ink-muted"><CountryLabel code={buyer.country} /></span>}
        {variants && <p className="m-0 text-small text-ink-muted">{variants}</p>}
      </div>
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-3">
        <FactCell label="Tenders in archive"><span className="tabular-nums">{buyer.tenderCount}</span></FactCell>
        <FactCell label="Open now" tone={buyer.openCount === 0 ? 'closed' : 'default'}><span className="tabular-nums">{buyer.openCount}</span></FactCell>
        <FactCell label="Last published">
          {buyer.lastPublishedAt
            ? <time dateTime={buyer.lastPublishedAt}>{formatDateUtc(buyer.lastPublishedAt)} UTC</time>
            : <span className="font-sans">Not stated</span>}
        </FactCell>
      </dl>
    </article>
  );
}
