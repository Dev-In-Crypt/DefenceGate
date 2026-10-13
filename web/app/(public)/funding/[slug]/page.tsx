import type { Metadata } from 'next';
import { notFound, permanentRedirect } from 'next/navigation';
import { Plus } from 'lucide-react';
import { getCall, getRelatedCalls } from '@/lib/api';
import { callStatusKind, getCallDeadline } from '@/lib/deadline';
import { displayName } from '@/lib/display-name';
import { formatDateUtc, formatMoney, openingPhrase } from '@/lib/format';
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
import { Icon } from '@/components/dg/icon';
import { FollowButton, SaveButton } from '@/components/account/save-button';

export const revalidate = 3600;
type Props = { params: Promise<{ slug: string }> };

const ROW = 'grid gap-1 break-words py-3 sm:grid-cols-[200px_minmax(0,1fr)] sm:gap-4';

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const call = await getCall((await params).slug);
  if (!call) return { title: 'Call not found', robots: { index: false } };
  const d = getCallDeadline(call);
  // Structured fields only: programme, opening, deadline, budget, source.
  const description = [
    `${call.programmeName}.`,
    call.status === 'forthcoming' && call.openingDate ? `${openingPhrase(call.openingDate).lead} ${openingPhrase(call.openingDate).date}.` : null,
    d.rolling ? `Open: rolling submission, last cut-off ${d.utc}.` : d.iso ? `Deadline ${d.utc}.` : 'No fixed deadline.',
    `Budget ${call.budget ? formatMoney(call.budget) : 'not stated'}.`,
    `Source: ${call.source.sourceName}.`,
  ].filter(Boolean).join(' ');
  return buildMetadata({
    title: `${displayName(call.title)} (${call.topicId})`,
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
  const call = await getCall(slug);
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
              <StatusPill status={callStatusKind(call.status, d.state)} />
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
          </header>

          {/* Deadline (or opening date) first on mobile: the hero element */}
          <DeadlineBadge info={d} opening={opens} size="lg" className="w-full lg:hidden" />

          <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
            <FactCell label="Budget">
              <AmountDisplay money={call.budget} size="lg" />
              {call.budget && call.budgetScope === 'call' && (
                <div className="mt-1 font-sans text-small font-normal text-ink-muted">Shared across several topics of the same call</div>
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
            <FactCell label="Funder country"><CountryLabel code={call.funderCountry} className="font-sans" /></FactCell>
            {call.fundingRate && <FactCell label="Funding rate"><span className="font-sans">{call.fundingRate}</span></FactCell>}
            {call.publishedAt && (
              <FactCell label="Dated by the source"><time dateTime={call.publishedAt}>{formatDateUtc(call.publishedAt)} UTC</time></FactCell>
            )}
          </dl>

          {hasScope && (
            <Panel title="Scope">
              <dl className="m-0 flex flex-col">
                {call.actionType && (
                  <div className={cn(ROW, call.scope.length > 0 && 'border-b border-line')}>
                    <dt className="text-body font-semibold">Action type</dt><dd className="m-0 text-body">{call.actionType}</dd>
                  </div>
                )}
                {call.scope.length > 0 && (
                  <div className={ROW}>
                    <dt className="text-body font-semibold">Topics</dt>
                    <dd className="m-0 flex flex-wrap gap-2">{call.scope.map((s) => <Tag key={s}>{s}</Tag>)}</dd>
                  </div>
                )}
              </dl>
            </Panel>
          )}

          <Panel title="Eligibility">
            {call.eligibility.length > 0 ? (
              <dl className="m-0 flex flex-col">
                {call.eligibility.map((e, i) => (
                  <div key={e.label} className={cn(ROW, i < call.eligibility.length - 1 && 'border-b border-line')}>
                    <dt className="text-body font-semibold">{e.label}</dt><dd className="m-0 text-body">{e.value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="m-0 text-body text-ink-muted">The source does not publish structured eligibility for this call.</p>
            )}
          </Panel>

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
            {sourceUrl && (
              <Button href={sourceUrl} external variant="text" className="self-start">View original at {call.source.sourceName}</Button>
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
