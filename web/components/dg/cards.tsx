import Link from 'next/link';
import { cn } from '@/lib/utils';
import { callStatusKind, getCallDeadline, getTenderDeadline, now } from '@/lib/deadline';
import { formatDateUtc, openingPhrase } from '@/lib/format';
import { PROGRAMMES, REGIMES, TENDER_SCOPES } from '@/lib/taxonomy';
import type { Buyer, Call, Tender } from '@/lib/types';
import { Tag, StatusPill } from './tag';
import { AmountDisplay, CountryLabel, FactCell, LangLabel } from './data-display';
import { SourceBadge } from './source-badge';

const CARD = 'group relative flex flex-col gap-5 rounded-lg border-strong border-transparent bg-surface p-5 transition-colors duration-dg hover:border-ink-muted sm:p-6';
const TITLE_LINK = 'text-inherit no-underline decoration-2 underline-offset-4 group-hover:underline after:absolute after:inset-0 after:rounded-lg after:content-[""]';

/** Whole card is one link (stretched title). "View original" sits above it. */
export function CallCard({ call, headingLevel = 'h2' }: { call: Call; headingLevel?: 'h2' | 'h3' }) {
  const d = getCallDeadline(call);
  const closed = d.state === 'closed';
  const upcoming = call.status === 'forthcoming';
  // A call that has not opened yet is not under time pressure, whatever its deadline.
  const soon = !upcoming && (d.state === 'soon' || d.state === 'urgent');
  const nonEnglish = call.titleLanguage !== 'en';
  const H = headingLevel;
  return (
    <article className={cn(CARD, closed ? 'text-ink-muted' : 'text-ink')}>
      <div className="flex flex-wrap items-center gap-2">
        <Tag kind="programme">{PROGRAMMES[call.programme].label}</Tag>
        <Tag>{REGIMES[call.regime]}</Tag>
        <Tag>{call.funderCountry}</Tag>
        <span className="ml-auto"><StatusPill status={callStatusKind(call.status, d.state)} /></span>
      </div>
      <div className="flex flex-col gap-1">
        <H lang={nonEnglish ? call.titleLanguage : undefined} className="m-0 text-[22px] font-bold leading-[30px] tracking-[-0.5px] sm:text-h2">
          <Link href={`/funding/${call.slug}`} className={TITLE_LINK}>{call.title}</Link>
        </H>
        {nonEnglish && <LangLabel kind="language" code={call.titleLanguage} />}
        {call.originalTitle && (
          <span className="text-small text-ink-muted">
            <span lang={call.originalLanguage ?? undefined}>{call.originalTitle}</span>
            {' · '}<LangLabel kind="title" code={call.originalLanguage} />
          </span>
        )}
      </div>
      {upcoming && call.openingDate && (
        <p className="m-0 text-body font-bold text-ink">
          {openingPhrase(call.openingDate, now()).lead}{' '}
          <time dateTime={call.openingDate}>{openingPhrase(call.openingDate, now()).date}</time>
        </p>
      )}
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3">
        <FactCell label={soon ? 'Closing soon' : 'Deadline'} tone={soon ? 'soon' : closed ? 'closed' : 'default'}>
          {d.iso ? (
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
        <FactCell label="Budget" tone={closed ? 'closed' : 'default'}><AmountDisplay money={call.budget} /></FactCell>
        <FactCell label={call.callId ? 'Call ID' : 'Source ID'} tone={closed ? 'closed' : 'default'}>{call.callId ?? call.topicId}</FactCell>
      </dl>
      <SourceBadge source={call.source} variant="inline" />
    </article>
  );
}

/** Status pills of a tender: Amended (when it changed), then Awarded / Cancelled / Closed / Closing soon / Open. */
export function TenderStatusPills({ tender }: { tender: Tender }) {
  const d = getTenderDeadline(tender);
  const native = tender.statusNative;
  // The source's own word wins over a bare "Closed".
  const label = tender.status === 'closed' ? (native === 'awarded' ? 'Awarded' : native === 'cancelled' ? 'Cancelled' : undefined) : undefined;
  return (
    <>
      {tender.amended && <StatusPill status="amended" />}
      <StatusPill status={callStatusKind(tender.status, d.state)}>{label}</StatusPill>
    </>
  );
}

/** Whole card is one link (stretched title). The buyer link and "View original" sit above it. */
export function TenderCard({ tender, headingLevel = 'h2' }: { tender: Tender; headingLevel?: 'h2' | 'h3' }) {
  const d = getTenderDeadline(tender);
  const closed = d.state === 'closed';
  const soon = d.state === 'soon' || d.state === 'urgent';
  const nonEnglish = tender.titleLanguage !== null && tender.titleLanguage !== 'en';
  const H = headingLevel;
  return (
    <article className={cn(CARD, closed ? 'text-ink-muted' : 'text-ink')}>
      <div className="flex flex-wrap items-center gap-2">
        {tender.cpv && <Tag kind="programme">CPV {tender.cpv}</Tag>}
        {tender.country && <Tag>{tender.country}</Tag>}
        <Tag>{TENDER_SCOPES[tender.scope].label}</Tag>
        <span className="ml-auto flex flex-wrap gap-2"><TenderStatusPills tender={tender} /></span>
      </div>
      <div className="flex flex-col gap-1">
        <H lang={nonEnglish ? (tender.titleLanguage ?? undefined) : undefined} className="m-0 text-[22px] font-bold leading-[30px] tracking-[-0.5px] sm:text-h2">
          <Link href={`/tenders/${tender.slug}`} className={TITLE_LINK}>{tender.title}</Link>
        </H>
        {nonEnglish && <LangLabel kind="language" code={tender.titleLanguage} />}
        {tender.originalTitle && (
          <span className="text-small text-ink-muted">
            <span lang={tender.originalLanguage ?? undefined}>{tender.originalTitle}</span>
            {' · '}<LangLabel kind="title" code={tender.originalLanguage} />
          </span>
        )}
        {tender.buyerSlug ? (
          <Link href={`/buyers/${tender.buyerSlug}`} className="relative z-10 self-start text-small font-semibold">{tender.buyerName}</Link>
        ) : (
          <span className="text-small font-semibold">{tender.buyerName}</span>
        )}
      </div>
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3">
        <FactCell label={soon ? 'Closing soon' : 'Deadline'} tone={soon ? 'soon' : closed ? 'closed' : 'default'}>
          {d.iso ? (
            <>
              <time dateTime={d.iso}>{d.utc}</time>
              {d.countdown && (
                <div className={cn('font-sans text-small font-bold', closed ? 'text-ink-muted' : soon ? 'text-soon-fg' : 'text-accent-text')}>{d.countdown}</div>
              )}
            </>
          ) : (
            <span className="font-sans">{closed ? 'Closed' : 'No deadline stated'}</span>
          )}
        </FactCell>
        <FactCell label="Estimated value" tone={closed ? 'closed' : 'default'}><AmountDisplay money={tender.estimatedValue} /></FactCell>
        <FactCell label="Notice ID" tone={closed ? 'closed' : 'default'}>{tender.noticeId}</FactCell>
      </dl>
      <SourceBadge source={tender.source} variant="inline" />
    </article>
  );
}

/** A procurement body. Counts are core-scope notices only (API_CONTRACT.md). */
export function BuyerCard({ buyer, headingLevel = 'h2' }: { buyer: Buyer; headingLevel?: 'h2' | 'h3' }) {
  const H = headingLevel;
  return (
    <article className={cn(CARD, 'text-ink')}>
      <div className="flex flex-col gap-2">
        {buyer.isDefenceBuyer && <span className="self-start"><Tag>Defence body</Tag></span>}
        <H className="m-0 text-[22px] font-bold leading-[30px] tracking-[-0.5px] sm:text-h2">
          <Link href={`/buyers/${buyer.slug}`} className={TITLE_LINK}>{buyer.name}</Link>
        </H>
        {buyer.country && <span className="text-small text-ink-muted"><CountryLabel code={buyer.country} /></span>}
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
