import { TriangleAlert } from 'lucide-react';
import { cn } from '@/lib/utils';
import { callStatusKind, getCallDeadline, getTenderDeadline, localDeadline, now } from '@/lib/deadline';
import { formatDateUtc, formatNumber, funderLine, isPlaceholderAmount, openingPhrase, variantsLine } from '@/lib/format';
import { AWARD_VALUE_LABEL, anomalyNotes, isLongRunning, noticeValueLabel, subjectAddsTo, tenderChangedLabel, tenderStatusView, winnersLine } from '@/lib/tender-status';
import { PROGRAMMES, REGIMES, isNonEnglish } from '@/lib/taxonomy';
import { WHO_BADGE } from '@/lib/filters';
import { displayName } from '@/lib/display-name';
import { cpvOwnName } from '@/lib/cpv';
import { matchedCpv } from '@/lib/tender-basis';
import type { Buyer, Call, Tender } from '@/lib/types';
import { Tag, StatusPill } from './tag';
import { CardLink } from './card-link';
import { AmountDisplay, BudgetDisplay, CountryLabel, LIST_FACTS, LangLabel, ListFact } from './data-display';
import { Icon } from './icon';
import { SourceBadge } from './source-badge';
import { BasisChips } from './basis-chips';
import { FitBadge } from '../funding/fit-badge';

/**
 * A list card: the book's surface with no outline, radius 20, a 1.5px --ink-muted edge and an underlined title on hover (the transparent
 * border keeps the box the same size on hover and draws the card in forced colours). Compact by the owner's decision of 21 Oct 2026 (the
 * book's 28 px padding, 20 px gaps and 28/36 title made a call card 331-371 px tall): padding 20, 12 px between the parts.
 */
const CARD = '[container-type:inline-size] group relative flex flex-col gap-3 [&_p]:max-w-prose rounded-lg border-strong border-transparent bg-surface p-5 transition-colors duration-dg hover:border-ink-muted has-[[data-link-pending]]:opacity-70';
/**
 * Card title: the card-title step, 20/28 bold (the book's 28/36 h2 is for page-level titles). Two lines at most in a wide card, three in a
 * narrow one (the card is a size container); the whole title is also in the link's `title` (a tooltip) and always in the link text itself,
 * which the clamp only hides.
 */
export const CARD_TITLE = 'm-0 line-clamp-3 text-h3 font-bold cq:line-clamp-2';
const TITLE_LINK = 'break-words text-inherit no-underline decoration-2 underline-offset-4 group-hover:underline after:absolute after:inset-0 after:rounded-lg after:content-[""]';
/**
 * One column in a narrow card (text, facts, provenance). From a 664 px card the facts are a 22rem column at the right of the text, and the
 * provenance runs under both on one line.
 */
export const CARD_BODY = 'grid gap-x-6 gap-y-3 cq:grid-cols-[minmax(0,1fr)_22rem]';
export const CARD_TEXT = 'flex min-w-0 flex-col gap-2 cq:col-start-1 cq:row-start-1';
const CARD_PROVENANCE = 'cq:col-span-2 cq:row-start-2';
const CARD_FACTS = 'cq:col-start-2 cq:row-start-1';

/** The title in the original language, one line, with its label; nothing when there is none. */
function OriginalTitle({ title, lang }: { title: string | null | undefined; lang: string | null | undefined }) {
  if (!title) return null;
  return (
    <p className="m-0 flex min-w-0 items-baseline gap-2 text-small text-ink-muted">
      <span lang={lang ?? undefined} className="min-w-0 truncate">{displayName(title)}</span>
      <LangLabel kind="title" code={lang} className="shrink-0" />
    </p>
  );
}

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
      <div className={CARD_BODY}>
        <div className={CARD_TEXT}>
          <div className="flex flex-wrap items-center gap-2">
            <Tag kind="programme">{PROGRAMMES[call.programme].label}</Tag>
            <Tag>{REGIMES[call.regime]}</Tag>
            <Tag>{call.funderCountry}</Tag>
            {/* WP-91: who may apply, where the rules or the source say (a few EDIP calls are for public bodies only) */}
            {call.whoMayApply && <span data-who={call.whoMayApply} className="contents"><Tag>{WHO_BADGE[call.whoMayApply]}</Tag></span>}
            {/* WP-92: the call document reserves it for SMEs */}
            {call.smeOnly === true && <span data-sme-only className="contents"><Tag>SMEs only</Tag></span>}
            {call.cascade === true && <Tag>Cascade funding</Tag>}
            {!closed && <FitBadge id={call.id} />}
            {call.openToUkraine === true && <Tag>Open to Ukraine</Tag>}
            <span className="ml-auto"><StatusPill status={callStatusKind(call.status, d.state, call.openingDate)} /></span>
          </div>
          <H lang={nonEnglish ? call.titleLanguage : undefined} className={CARD_TITLE}>
            <CardLink href={`/funding/${call.slug}`} className={TITLE_LINK} title={displayName(call.title)}>{displayName(call.title)}</CardLink>
          </H>
          <p className="m-0 flex flex-wrap items-baseline gap-x-2 text-small text-ink-muted">
            <span>{funderLine(call)}</span>
            {nonEnglish && <LangLabel kind="language" code={call.titleLanguage} />}
          </p>
          <OriginalTitle title={call.originalTitle} lang={call.originalLanguage} />
          {call.status === 'open' && call.sourceStatus === 'forthcoming' && (
            <p className="m-0 text-small text-ink-muted">The source still lists this call as forthcoming; its opening date has passed and its deadline is ahead.</p>
          )}
          {upcoming && call.openingDate && (
            <p className="m-0 text-body font-bold text-ink">
              {openingPhrase(call.openingDate, now()).lead}{' '}
              <time dateTime={call.openingDate}>{openingPhrase(call.openingDate, now()).date}</time>
            </p>
          )}
        </div>
        <dl className={cn(LIST_FACTS, CARD_FACTS)}>
          <ListFact label={d.rolling ? 'Submission' : soon ? 'Closing soon' : 'Deadline'} tone={soon ? 'soon' : closed ? 'closed' : 'default'}>
            {d.rolling && d.iso ? (
              <>
                <span className="font-sans">Open: rolling submission</span>
                <div className="font-sans text-small font-normal text-ink-muted">Last cut-off <time dateTime={d.iso}>{d.utc}</time> (passed; no next one published)</div>
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
          </ListFact>
          <ListFact label={call.budgetScope === 'call' ? 'Call budget, all topics' : call.budgetScope === 'topic' ? 'Topic budget' : 'Budget'} tone={closed ? 'closed' : 'default'}>
            {budgetRepeated ? (
              <span className="font-sans text-body text-ink-muted">Shared with the other topics of this call</span>
            ) : (
              <>
                {/* WP-88: the label says whose budget it is ("Call budget": shared by its topics, see the glossary); no second line. */}
                <BudgetDisplay money={call.budget} note={call.budgetNote} />
              </>
            )}
          </ListFact>
          {/* WP-109 (p08): the topic, not the call, tells two topics of one call apart (EDF-EDIP-USI-2027 holds several) */}
          <ListFact label={call.callId ? 'Topic ID' : 'Source ID'} tone={closed ? 'closed' : 'default'}>{call.topicId}</ListFact>
        </dl>
        <SourceBadge source={call.source} variant="inline" className={CARD_PROVENANCE} subject={displayName(call.title)} subjectLang={nonEnglish ? call.titleLanguage : undefined} />
      </div>
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
export function TenderCard({ tender, headingLevel = 'h2', cpvFilter, valueNote, classifiedNote = true }: {
  tender: Tender; headingLevel?: 'h2' | 'h3';
  /** The "Classified automatically; see how" line on the card. A list that says it once (ClassifiedNote) passes false. */
  classifiedNote?: boolean;
  /** The CPV prefixes the list is filtered by: a notice found through an additional code says so. */
  cpvFilter?: string[];
  /** Why the value is missing for this source ("Not collected from this source" or "No usable estimated value in 82 % of notices from this source."). */
  valueNote?: string | null;
}) {
  const d = getTenderDeadline(tender);
  const local = d.state === 'closed' ? null : localDeadline(d.iso, tender.country, d.dateOnly);
  const matched = matchedCpv(tender, cpvFilter);
  // WP-106: the API's title from the full vocabulary first (34330000 had none), then the selection's
  const mainName = tender.cpv ? (tender.cpvTitles?.[tender.cpv] ?? cpvOwnName(tender.cpv)) : null;
  const award = tender.awardValue && !isPlaceholderAmount(tender.awardValue.amount) ? tender.awardValue : null;
  const winners = winnersLine(tender, 2, (n) => displayName(n, 'title'));
  const subject = subjectAddsTo(tender.subject, tender.title);
  const closed = d.state === 'closed';
  const soon = d.state === 'soon' || d.state === 'urgent';
  const longRunning = isLongRunning(tender) && !closed;
  const nonEnglish = isNonEnglish(tender.titleLanguage);
  const H = headingLevel;
  return (
    <article className={cn(CARD, closed ? 'text-ink-muted' : 'text-ink')}>
      <div className={CARD_BODY}>
        <div className={CARD_TEXT}>
          <div className="flex flex-wrap items-center gap-2">
            {tender.cpv && <Tag kind="programme">CPV {tender.cpv}</Tag>}
            {mainName && <span title={mainName} className="min-w-0 flex-1 truncate text-small text-ink-muted">{mainName}</span>}
            {tender.country && <Tag>{tender.country}</Tag>}
            <span className="ml-auto flex min-w-0 max-w-full flex-wrap gap-2"><TenderStatusPills tender={tender} /></span>
          </div>
          {matched.length > 0 && (
            <p className="m-0 text-small text-ink-muted">
              Matches your code filter through {matched.length === 1 ? 'an additional code' : 'additional codes'}:{' '}
              {matched.map((c, i) => <span key={c}>{i > 0 && ', '}<span className="font-mono text-mono-strong">{c}</span>{cpvOwnName(c) ? ` (${cpvOwnName(c)})` : ''}</span>)}
            </p>
          )}
          <H lang={nonEnglish ? (tender.titleLanguage ?? undefined) : undefined} className={CARD_TITLE}>
            <CardLink href={`/tenders/${tender.slug}`} className={TITLE_LINK} title={displayName(tender.title)}>{displayName(tender.title)}</CardLink>
          </H>
          <p className="m-0 flex flex-wrap items-baseline gap-x-2 text-small">
            {tender.buyerSlug ? (
              <CardLink href={`/buyers/${tender.buyerSlug}`} className="relative z-10 inline-flex min-h-8 items-center font-semibold">{displayName(tender.buyerName, 'title')}</CardLink>
            ) : (
              <span className="font-semibold">{displayName(tender.buyerName, 'title')}</span>
            )}
            {nonEnglish && <LangLabel kind="language" code={tender.titleLanguage} />}
          </p>
          <OriginalTitle title={tender.originalTitle} lang={tender.originalLanguage} />
          {/* WP-106 (p03, p06): what is bought, in the notice's own words, where the title is an internal number or a place */}
          {subject && <p className="m-0 line-clamp-2 text-small" data-subject><span className="text-ink-muted">Subject: </span>{subject}</p>}
          {/* WP-106 (p06): an award says whom it names in the list too */}
          {winners && <p className="m-0 text-small" data-awarded-to><span className="text-ink-muted">Awarded to: </span><span className="font-semibold">{winners}</span></p>}
          <BasisChips tender={tender} lifted note={classifiedNote} />
        </div>
        <dl className={cn(LIST_FACTS, CARD_FACTS)}>
          <ListFact label={soon ? 'Closing soon' : longRunning ? 'Open until (long-running)' : 'Deadline'} tone={soon ? 'soon' : closed ? 'closed' : 'default'}>
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
          </ListFact>
          {award ? (
            // WP-106 (p06, p07): an award's value under the words of its kind, never "Estimated value" over a contract or a ceiling
            <ListFact label={AWARD_VALUE_LABEL[award.kind]} tone={closed ? 'closed' : 'default'}>
              <AmountDisplay money={{ amount: award.amount, currency: award.currency }} />
              {award.kind === 'framework' && <div className="font-sans text-small font-normal text-ink-muted">The most that may be bought, not a contract value</div>}
            </ListFact>
          ) : (
          <ListFact label={noticeValueLabel(tender)} tone={closed ? 'closed' : 'default'}>
            <AmountDisplay money={tender.estimatedValue} />
            {valueNote && (!tender.estimatedValue || isPlaceholderAmount(tender.estimatedValue.amount)) && (
              <div className="font-sans text-small font-normal text-ink-muted">{valueNote}</div>
            )}
            {tender.estimatedValue && !isPlaceholderAmount(tender.estimatedValue.amount) && tender.valueKind === 'lot_sum' && (
              <div className="font-sans text-small font-normal text-ink-muted">Sum of the values the notice states for its lots</div>
            )}
          </ListFact>
          )}
          <ListFact label="Notice ID" tone={closed ? 'closed' : 'default'}>{tender.noticeId}</ListFact>
        </dl>
        <div className={cn('flex min-w-0 flex-col gap-2', CARD_PROVENANCE)}>
          <AnomalyNote tender={tender} />
          <SourceBadge source={tender.source} variant="inline" retrievedLabel={tenderChangedLabel(tender.source)} subject={displayName(tender.title)} subjectLang={nonEnglish ? (tender.titleLanguage ?? undefined) : undefined} />
        </div>
      </div>
    </article>
  );
}

/** A procurement body. Counts are core-scope notices only (API_CONTRACT.md). Name at the left, three facts at the right (from xl). */
export function BuyerCard({ buyer, headingLevel = 'h2' }: { buyer: Buyer; headingLevel?: 'h2' | 'h3' }) {
  const H = headingLevel;
  const variants = variantsLine(buyer.nameVariants);
  return (
    <article className={cn(CARD, 'text-ink')}>
      <div className={CARD_BODY}>
        <div className={CARD_TEXT}>
          {buyer.isDefenceBuyer && <span className="self-start"><Tag>Defence body</Tag></span>}
          <H className={CARD_TITLE}>
            <CardLink href={`/buyers/${buyer.slug}`} className={TITLE_LINK} title={displayName(buyer.name, 'title')}>{displayName(buyer.name, 'title')}</CardLink>
          </H>
          {buyer.country && <span className="text-small text-ink-muted"><CountryLabel code={buyer.country} /></span>}
          {variants && <p className="m-0 text-small text-ink-muted">{variants}</p>}
        </div>
        <dl className={cn(LIST_FACTS, 'cq:col-start-2 cq:row-start-1')}>
          {/* WP-98b: with a CPV filter, its tenders under the codes (the list's order), before all of its tenders */}
          {typeof buyer.cpvCount === 'number' && <ListFact label="Under these codes"><span className="tabular-nums" data-cpv-count>{formatNumber(buyer.cpvCount)}</span></ListFact>}
          <ListFact label="Tenders in archive"><span className="tabular-nums" data-buyer-tenders>{formatNumber(buyer.tenderCount)}</span></ListFact>
          <ListFact label="Open now" tone={buyer.openCount === 0 ? 'closed' : 'default'}><span className="tabular-nums">{formatNumber(buyer.openCount)}</span></ListFact>
          <ListFact label="Last published">
            {buyer.lastPublishedAt
              ? <time dateTime={buyer.lastPublishedAt}>{formatDateUtc(buyer.lastPublishedAt)} UTC</time>
              : <span className="font-sans">Not stated</span>}
          </ListFact>
        </dl>
      </div>
    </article>
  );
}
