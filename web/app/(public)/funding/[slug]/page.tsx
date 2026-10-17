import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, permanentRedirect } from 'next/navigation';
import { ExternalLink, Plus } from 'lucide-react';
import { getCall, getRelatedCalls, REMOVED, whenRemoved } from '@/lib/api';
import { RemovedOnRequest } from '@/components/dg/removed';
import { callStatusKind, getCallDeadline } from '@/lib/deadline';
import { displayName } from '@/lib/display-name';
import { formatDateUtc, formatMoney, funderLine, openingPhrase } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { buildMetadata, callJsonLd, meetsMinimumContent } from '@/lib/seo';
import { PROGRAMMES, REGIMES, isNonEnglish } from '@/lib/taxonomy';
import { cn } from '@/lib/utils';
import { Breadcrumbs, JsonLd } from '@/components/dg/feedback';
import { AlertsLine } from '@/components/dg/alerts-line';
import { Tag, StatusPill } from '@/components/dg/tag';
import { DeadlineBadge } from '@/components/dg/deadline-badge';
import { AmountDisplay, CountryLabel, FactCell, LangLabel } from '@/components/dg/data-display';
import { SourceBadge } from '@/components/dg/source-badge';
import { Button } from '@/components/dg/button';
import { CallCard } from '@/components/dg/cards';
import { EligibilityCheck } from '@/components/funding/eligibility-check';
import { Icon } from '@/components/dg/icon';
import { FollowButton, SaveButton } from '@/components/account/save-button';

export const revalidate = 300;
type Props = { params: Promise<{ slug: string }> };

/** The glossary entry that explains each programme chip. */
const PROGRAMME_GLOSSARY: Partial<Record<string, string>> = { EDF: 'edf', EDIP: 'edip', HORIZON: 'horizon-europe', DIGITAL: 'digital-europe', CEF: 'cef' };

const ROW = 'grid gap-1 break-words py-3 sm:grid-cols-[200px_minmax(0,1fr)] sm:gap-4';

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const call = await getCall((await params).slug).catch(whenRemoved);
  if (call === REMOVED) return { title: 'Removed on request', robots: { index: false } };
  if (!call) return { title: 'Call not found', robots: { index: false } };
  const d = getCallDeadline(call);
  // Structured fields only: programme, opening, deadline, budget, source.
  const description = [
    `${funderLine(call)}.`,
    call.status === 'forthcoming' && call.openingDate ? `${openingPhrase(call.openingDate).lead} ${openingPhrase(call.openingDate).date}.` : null,
    d.rolling ? `Open: rolling submission, last cut-off ${d.utc}.` : d.iso ? `Deadline ${d.utc}.` : 'No fixed deadline.',
    `Budget ${call.budget ? formatMoney(call.budget) : 'not stated'}.`,
    `Source: ${call.source.sourceName}.`,
  ].filter(Boolean).join(' ');
  return buildMetadata({
    // The topic id is a Horizon-style identifier only where the call has a call id; elsewhere it falls back to the
    // source's own key ("[aid] 12345"), which is not a title (site-qa2:N12: 27 calls).
    title: call.callId ? `${displayName(call.title)} (${call.topicId})` : displayName(call.title),
    description,
    path: `/funding/${call.slug}`,
    noindex: !meetsMinimumContent(call),
  });
}

function Panel({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  const id = title.toLowerCase().replace(/\W+/g, '-');
  return (
    <section aria-labelledby={id} className={cn('flex flex-col gap-4 rounded-lg bg-surface p-5 sm:p-6', className)}>
      <h2 id={id} className="m-0 text-h3">{title}</h2>
      {children}
    </section>
  );
}

export default async function CallDetailPage({ params }: Props) {
  const { slug } = await params;
  const call = await getCall(slug).catch(whenRemoved);
  if (call === REMOVED) return <RemovedOnRequest what="call" />;
  if (!call) notFound();
  // The API looks up the leading id only; a changed title must not break a link.
  if (call.slug !== slug) permanentRedirect(`/funding/${call.slug}`);

  const related = await getRelatedCalls(call);
  const d = getCallDeadline(call);
  const closed = d.state === 'closed';
  const upcoming = call.status === 'forthcoming';
  const opens = upcoming ? call.openingDate : null;
  const nonEnglish = isNonEnglish(call.titleLanguage);
  const programme = PROGRAMMES[call.programme];
  const sourceUrl = safeHttpUrl(call.source.url);
  const hasScope = Boolean(call.actionType) || call.scope.length > 0;
  const who = call.whoCanApply ?? [];
  const documents = call.documents ?? [];
  // The structured rows that already answer "who can apply" are not repeated under Terms.
  const whoLabels = new Set(who.map((r) => r.label));
  const terms = call.eligibility.filter((r) => !whoLabels.has(r.label));

  return (
    <>
      <JsonLd data={callJsonLd(call)} />
      <Breadcrumbs items={[
        { label: 'Home', href: '/' }, { label: 'Funding', href: '/funding' },
        { label: displayName(call.title), href: `/funding/${call.slug}` },
      ]} />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-6">
          <header className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <Tag kind="programme">{programme.label}</Tag>
              <Tag>{REGIMES[call.regime]}</Tag>
              <StatusPill status={callStatusKind(call.status, d.state, call.openingDate)} />
            </div>
            <div className="flex flex-col gap-2">
              <h1 lang={nonEnglish ? call.titleLanguage : undefined}
                className={cn('m-0 break-words text-[32px] font-extrabold leading-10 tracking-[-1px] md:text-h1', closed ? 'text-ink-muted' : 'text-ink')}>{displayName(call.title)}</h1>
              {nonEnglish && <LangLabel kind="language" code={call.titleLanguage} />}
            </div>
            {call.originalTitle && (
              <p className="m-0 text-body text-ink-muted">
                <span lang={call.originalLanguage ?? undefined}>{displayName(call.originalTitle)}</span>
                {' · '}<LangLabel kind="title" code={call.originalLanguage} />
              </p>
            )}
            <p className="m-0 text-body text-ink-muted">{funderLine(call)}</p>
            {call.status === 'open' && call.sourceStatus === 'forthcoming' && (
              <p className="m-0 text-body text-ink-muted">
                The source still lists this call as forthcoming. Its opening date has passed and its deadline is ahead, so we show it as open.
              </p>
            )}
          </header>

          {/* Deadline (or opening date) first on mobile: the hero element */}
          <DeadlineBadge info={d} opening={opens} size="lg" className="w-full lg:hidden" />

          <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
            <FactCell label="Budget">
              <AmountDisplay money={call.budget} size="lg" />
              {call.budget && call.budgetScope === 'call' && (
                <div className="mt-1 font-sans text-small font-normal text-ink-muted">Shared across several topics of the same call</div>
              )}
              {call.budget && call.budgetScope === 'topic' && (
                <div className="mt-1 font-sans text-small font-normal text-ink-muted">Budget of this topic</div>
              )}
            </FactCell>
            {call.callId && <FactCell label="Call ID">{call.callId}</FactCell>}
            <FactCell label={call.callId ? 'Topic ID' : 'Source ID'}>{call.topicId}</FactCell>
            <FactCell label="Opening date">
              {call.openingDate
                ? <time dateTime={call.openingDate}>{formatDateUtc(call.openingDate)} UTC</time>
                : <span className="font-sans">Not stated</span>}
            </FactCell>
            {call.issuer && <FactCell label="Issued by"><span className="font-sans">{call.issuer}</span></FactCell>}
            <FactCell label="Funder"><span className="font-sans">{call.funder}</span></FactCell>
            <FactCell label="Programme"><span className="font-sans">{call.programmeName}</span></FactCell>
            <FactCell label="Funder country"><CountryLabel code={call.funderCountry} className="font-sans" /></FactCell>
            {call.fundingRate && <FactCell label="Funding rate"><span className="font-sans">{call.fundingRate}</span></FactCell>}
            {call.publishedAt && (
              <FactCell label="Dated by the source"><time dateTime={call.publishedAt}>{formatDateUtc(call.publishedAt)} UTC</time></FactCell>
            )}
          </dl>

          <p className="m-0 text-small text-ink-muted">
            What do these terms mean? In the <Link href="/glossary" className="font-semibold">glossary</Link>:
            {PROGRAMME_GLOSSARY[call.programme] && <> <Link href={`/glossary#${PROGRAMME_GLOSSARY[call.programme]}`} className="font-semibold">{programme.label}</Link>,</>}
            {call.regime === 'dual-use' && <> <Link href="/glossary#dual-use" className="font-semibold">dual-use (our label)</Link>,</>}
            {' '}<Link href="/glossary#call-and-topic" className="font-semibold">call and topic budget</Link>,
            {' '}<Link href="/glossary#date-only-deadline" className="font-semibold">date-only deadline</Link>.
          </p>

          {hasScope && (
            <Panel title="Scope">
              <dl className="m-0 flex flex-col">
                {call.actionType && (
                  <div className={cn(ROW, call.scope.length > 0 && 'border-b border-line')}>
                    <dt className="text-body font-semibold"><Link href="/glossary#action-type">Action type</Link></dt><dd className="m-0 text-body">{call.actionType}</dd>
                  </div>
                )}
                {call.scope.length > 0 && (
                  <div className={ROW}>
                    <dt className="text-body font-semibold">Topics</dt>
                    <dd className="m-0 flex min-w-0 flex-wrap gap-2">{call.scope.map((s) => <Tag key={s} wrap>{s}</Tag>)}</dd>
                  </div>
                )}
              </dl>
            </Panel>
          )}

          <Panel title="Who can apply">
            {who.length > 0 ? (
              <>
                <dl className="m-0 flex flex-col">
                  {who.map((e, i) => (
                    <div key={e.label} className={cn(ROW, i < who.length - 1 && 'border-b border-line')}>
                      <dt className="text-body font-semibold">{e.label}</dt><dd className="m-0 text-body">{e.value}</dd>
                    </div>
                  ))}
                </dl>
                <p className="m-0 text-small text-ink-muted">In the source’s own words. The official call text is authoritative.</p>
              </>
            ) : (
              <p className="m-0 text-body text-ink-muted">The source does not say who may apply.</p>
            )}
            {sourceUrl ? (
              <Button href={sourceUrl} external variant="secondary" className="self-start whitespace-normal text-left">See the official call text at {call.source.sourceName}</Button>
            ) : (
              <p className="m-0 text-body text-ink-muted">The source gives no link to this call. Search for “{call.topicId}” at {call.source.sourceName}.</p>
            )}
          </Panel>

          {call.documentEligibility && (
            <Panel title="Can you apply?">
              <EligibilityCheck facts={call.documentEligibility.facts} documentUrl={call.documentEligibility.documentUrl} readAt={formatDateUtc(call.documentEligibility.extractedAt)} />
            </Panel>
          )}

          <Panel title="Terms">
            {terms.length > 0 ? (
              <dl className="m-0 flex flex-col">
                {terms.map((e, i) => (
                  <div key={e.label} className={cn(ROW, i < terms.length - 1 && 'border-b border-line')}>
                    <dt className="text-body font-semibold">{e.label}</dt><dd className="m-0 text-body">{e.value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="m-0 text-body text-ink-muted">The source does not publish structured terms for this call.</p>
            )}
          </Panel>

          {documents.length > 0 && (
            <Panel title="Official documents">
              <ul className="m-0 flex list-none flex-col gap-1 p-0">
                {documents.map((d) => (
                  <li key={d.url}>
                    <a href={d.url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-2 break-words text-body font-semibold">
                      {d.label}<Icon icon={ExternalLink} size="inline" /><span className="sr-only">(opens in new tab)</span>
                    </a>
                  </li>
                ))}
              </ul>
              <p className="m-0 text-small text-ink-muted">Linked from the call at {call.source.sourceName}. They are the source’s documents, not ours.</p>
            </Panel>
          )}

          {call.conditionsText && (
            <details className="group rounded-lg bg-surface px-5 sm:px-6">
              <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 py-4 text-body font-semibold [&::-webkit-details-marker]:hidden">
                Conditions as published by the source
                <Icon icon={Plus} className="shrink-0 text-ink-muted transition-transform duration-dg group-open:rotate-45" />
              </summary>
              {/* The source's own text, unedited. Not prose of ours. */}
              <p className="m-0 whitespace-pre-wrap pb-5 text-body">{call.conditionsText}</p>
            </details>
          )}

          <Panel title="Source and attribution">
            <SourceBadge source={call.source} />
          </Panel>
        </div>

        <aside aria-label="Deadline and actions" className="flex flex-col gap-4 lg:sticky lg:top-4">
          <div className="flex flex-col gap-4 rounded-lg bg-surface p-6">
            <DeadlineBadge info={d} opening={opens} size="lg" className="hidden w-full lg:flex" />
            <SaveButton kind="call" refId={call.id} />
            <FollowButton kind="programme" refId={call.programme} label={`Follow ${programme.label}`} />
            {sourceUrl ? (
              <Button href={sourceUrl} external variant="text" className="self-start">View original at {call.source.sourceName}</Button>
            ) : (
              <p className="m-0 text-small text-ink-muted">The source gives no link to this call.</p>
            )}
            <AlertsLine />
          </div>
        </aside>
      </div>

      {related.length > 0 && (
        <section aria-labelledby="related" className="flex flex-col gap-4">
          <h2 id="related" className="m-0 text-h2">Related calls</h2>
          <ul className="m-0 grid list-none gap-4 p-0 lg:grid-cols-3">
            {related.map((c) => <li key={c.id} className="min-w-0"><CallCard call={c} headingLevel="h3" /></li>)}
          </ul>
        </section>
      )}
    </>
  );
}
