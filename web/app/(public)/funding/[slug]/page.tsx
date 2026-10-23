import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, permanentRedirect } from 'next/navigation';
import { CalendarPlus, ExternalLink } from 'lucide-react';
import { getCall, getOpenCallsForRelated, relatedCallsFrom, REMOVED, whenRemoved } from '@/lib/api';
import { RemovedOnRequest } from '@/components/dg/removed';
import { callStatusKind, getCallDeadline } from '@/lib/deadline';
import { displayName } from '@/lib/display-name';
import { formatDateUtc, formatMoney, funderLine, openingPhrase, isoDatesToSite } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { sourceDisplay } from '@/lib/source-status';
import { buildMetadata, callJsonLd, meetsMinimumContent } from '@/lib/seo';
import { PROGRAMMES, REGIMES, isNonEnglish } from '@/lib/taxonomy';
import { JsonLd } from '@/components/dg/feedback';
import { AlertsLine } from '@/components/dg/alerts-line';
import { Tag, StatusPill } from '@/components/dg/tag';
import { DeadlineBadge } from '@/components/dg/deadline-badge';
import { BudgetDisplay, CountryLabel, FactCell, LangLabel } from '@/components/dg/data-display';
import { SourceBadge } from '@/components/dg/source-badge';
import { Button } from '@/components/dg/button';
import { Card } from '@/components/dg/card';
import { CallCard } from '@/components/dg/cards';
import { PageHeader } from '@/components/dg/page-header';
import { DetailLayout, SectionNav } from '@/components/dg/detail-layout';
import { Fact, FactsGrid } from '@/components/dg/facts-grid';
import { EligibilityCheck } from '@/components/funding/eligibility-check';
import { CallReadiness } from '@/components/funding/call-readiness';
import { PartnerSuggestions } from '@/components/funding/partner-suggestions';
import { RulesApplyBlock, UKRAINE_BASIS, ukraineSentence } from '@/components/funding/rules-apply';
import { Icon } from '@/components/dg/icon';
import { FollowButton, SaveButton } from '@/components/account/save-button';
import { LongText } from '@/components/funding/long-text';
import { mergeSameText } from '@/lib/long-text';
import { whatItFunds } from '@/lib/funding-path';
import { WHO_WORDS } from '@/lib/filters';
import { ApplySummary, UkraineOnly } from '@/components/funding/apply-summary';

export const revalidate = 300;
type Props = { params: Promise<{ slug: string }> };

/** The glossary entry that explains each programme chip. */
const PROGRAMME_GLOSSARY: Partial<Record<string, string>> = { EDF: 'edf', EDIP: 'edip', 'EDIP-USI': 'usi', HORIZON: 'horizon-europe', DIGITAL: 'digital-europe', CEF: 'cef' };

/** A value that reads as a sentence (not a figure or a name) takes the whole row of a facts grid. */
const isLong = (v: React.ReactNode) => typeof v === 'string' && v.length > 70;
/** The facts grid inside a titled card: the card's own header rule stands in for the first hairline. */
const IN_CARD = 'border-b-0 [&>div:first-child]:border-t-0';

/** Where the cascade flag was read from, in words. */
const CASCADE_BASIS: Record<string, string> = {
  call_document: 'From the call document',
  topic_text: 'From the topic’s own conditions',
  call_text: 'From the call’s conditions text',
};

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
    `Source: ${sourceDisplay(call.source.sourceName)}.`,
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

/** The id a part of the page has: its title in lower case with dashes. The index at the top links to these, and so do the tests. */
const panelId = (title: string) => title.toLowerCase().replace(/\W+/g, '-');

function Panel({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return <Card title={title} id={panelId(title)} className={className}>{children}</Card>;
}

export default async function CallDetailPage({ params }: Props) {
  const { slug } = await params;
  // The list the related calls come from does not depend on the call: read together, not after it (a cold page was two steps).
  const openCalls = getOpenCallsForRelated();
  openCalls.catch(() => undefined); // handled below if it is used; not an unhandled rejection if the page ends first
  const call = await getCall(slug).catch(whenRemoved);
  if (call === REMOVED) return <RemovedOnRequest what="call" />;
  if (!call) notFound();
  // The API looks up the leading id only; a changed title must not break a link.
  if (call.slug !== slug) permanentRedirect(`/funding/${call.slug}`);

  const related = relatedCallsFrom(call, (await openCalls).items);
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
  // Dates the source gave as 2026-12-15 read like every other date on the site (15 Dec 2026).
  const terms = call.eligibility.filter((r) => !whoLabels.has(r.label)).map((r) => ({ ...r, value: isoDatesToSite(r.value) }));
  // Two rows with the same sentence ("Described in section 6 of the call document.") are one row.
  const whoRows = mergeSameText(who);
  const ukraine = ukraineSentence(call.openToUkraine, call.ukraineBasis?.reason);
  const edip = call.rulesApply && (call.rulesApply.regime.code === 'EDIP' || call.rulesApply.regime.code === 'EDIP-USI') ? call.rulesApply.regime.name : null;
  // The parts of the page that are present, in order: the index links to them.
  // EDF and EDIP calls (the Ukraine Support Instrument's included: WP-91 labels them by their instrument) have readiness rules
  const defenceFund = call.programme === 'EDF' || call.programme === 'EDIP' || call.programme === 'EDIP-USI';
  const canApply = Boolean(call.documentEligibility) || call.eligibilityState === 'not_read' || (defenceFund && !closed);
  const part = (title: string, label = title) => ({ id: panelId(title), label });
  const toc = [
    hasScope && part('Scope'), part('Who can apply'), call.rulesApply && part('Rules that apply'), ukraine && part('Ukrainian participants'),
    canApply && part('Can you apply?'), call.partnerArea && part('Partners from earlier projects'),
    call.cascade !== null && call.cascade !== undefined && part('Cascade funding'),
    part('Terms'), documents.length > 0 && part('Official documents'), call.conditionsText && { id: 'conditions', label: 'Conditions as published' },
    part('Source and attribution', 'Source'), related.length > 0 && { id: 'related', label: 'Related calls' },
  ].filter((t): t is { id: string; label: string } => Boolean(t));

  return (
    <>
      <JsonLd data={callJsonLd(call)} />
      <PageHeader
        crumbs={[
          { label: 'Home', href: '/' }, { label: 'Funding', href: '/funding' },
          { label: displayName(call.title), href: `/funding/${call.slug}`, lang: nonEnglish ? call.titleLanguage : undefined },
        ]}
        eyebrow={(
          <div className="flex flex-wrap items-center gap-2">
            <Tag kind="programme">{programme.label}</Tag>
            {/* The portal files the EDIP calls under the EDF; the rules that apply, and the Ukraine flag, are those of the instrument (V2-C U3). */}
            {edip && <Tag>{edip}</Tag>}
            <Tag>{REGIMES[call.regime]}</Tag>
            {call.cascade === true && <Tag>Cascade funding</Tag>}
            {call.openToUkraine === true && <Tag>Open to Ukraine</Tag>}
            {call.whoMayApply && <Tag>{WHO_WORDS[call.whoMayApply]}</Tag>}
            {call.smeOnly === true && <Tag>SMEs only</Tag>}
            <StatusPill status={callStatusKind(call.status, d.state, call.openingDate)} />
          </div>
        )}
        title={displayName(call.title)}
        titleProps={{ lang: nonEnglish ? call.titleLanguage : undefined, className: closed ? 'text-ink-muted' : 'text-ink' }}
      >
        {nonEnglish && <LangLabel kind="language" code={call.titleLanguage} />}
        {call.originalTitle && (
          <p className="m-0 max-w-prose text-body text-ink-muted">
            <span lang={call.originalLanguage ?? undefined}>{displayName(call.originalTitle)}</span>
            {' · '}<LangLabel kind="title" code={call.originalLanguage} />
          </p>
        )}
        <p className="m-0 max-w-prose text-body text-ink-muted">{funderLine(call)}</p>
        {/* WP-91 (UX audit 6): what the call funds and whether one can apply, on the first screen (phone included) */}
        {/* WP-92: the topic description's own Objective / Expected outcome, commercial sentences only (backend topic_summary.py) */}
        {call.fundsSummary ? (
          <div className="m-0 max-w-prose text-body" data-what-it-funds data-funds-summary>
            <p className="m-0"><strong>What it funds:</strong> {call.fundsSummary}</p>
            <p className="m-0 text-small text-ink-muted">
              From the topic description{sourceUrl
                ? <>; <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="font-semibold">see the full text<span className="sr-only"> at {sourceDisplay(call.source.sourceName)} (opens in new tab)</span></a>.</>
                : '.'}
            </p>
          </div>
        ) : (
          <p className="m-0 max-w-prose text-body" data-what-it-funds>
            <strong>What it funds:</strong> <span lang={nonEnglish ? call.titleLanguage : undefined}>{whatItFunds({ ...call, title: displayName(call.title) })}</span>
            {sourceUrl && <> <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="font-semibold">Read the topic description at {sourceDisplay(call.source.sourceName)}<span className="sr-only"> (opens in new tab)</span></a>.</>}
          </p>
        )}
        {!closed && <ApplySummary call={call} />}
        {call.status === 'open' && call.sourceStatus === 'forthcoming' && (
          <p className="m-0 max-w-prose text-body text-ink-muted">
            The source still lists this call as forthcoming. Its opening date has passed and its deadline is ahead, so we show it as open.
          </p>
        )}
      </PageHeader>

      <DetailLayout
        // Deadline (or opening date) first on mobile: the hero element.
        top={<DeadlineBadge info={d} opening={opens} size="lg" className="w-full" />}
        // A call page runs to some twenty screens at 375 px: the way to its parts is one tap from the top (U14); from lg it is a sticky list.
        nav={toc.length >= 5 ? <SectionNav items={toc} /> : undefined}
        facts={(
          <Card title="Key facts">
            <FactsGrid className={IN_CARD}>
              <FactCell label="Budget">
                <BudgetDisplay money={call.budget} note={call.budgetNote} size="lg" long />
                {call.budget && call.budgetScope === 'call' && (
                  <div className="mt-1 font-sans text-small font-normal text-ink-muted">Shared across several topics of the same call</div>
                )}
                {call.budget && call.budgetScope === 'topic' && (
                  <div className="mt-1 font-sans text-small font-normal text-ink-muted">Budget of this topic</div>
                )}
              </FactCell>
              {call.callId && <FactCell label="Call ID">{call.callId}</FactCell>}
              <FactCell label={call.callId ? 'Topic ID' : 'Source ID'}>{call.topicId}</FactCell>
              {/* WP-90: the deadline in the facts too, the way the badge states it (date only, or a time in UTC; a cut-off of a rolling call) */}
              <FactCell label={call.rolling ? 'Cut-off' : 'Deadline'}>
                {call.deadline && d.iso
                  ? <span className="font-sans" data-key-deadline>{d.utc}</span>
                  : <span className="font-sans" data-key-deadline>Not stated</span>}
              </FactCell>
              <FactCell label="Opening date">
                {call.openingDate
                  ? <time dateTime={call.openingDate}>{formatDateUtc(call.openingDate)} UTC</time>
                  : <span className="font-sans">Not stated</span>}
              </FactCell>
              {call.issuer && <FactCell label="Issued by"><span className="font-sans">{call.issuer}</span></FactCell>}
              <FactCell label="Funder"><span className="font-sans">{call.funder}</span></FactCell>
              <FactCell label="Programme">
                <span className="font-sans">
                  {call.programmeName}
                  {edip && ` (filed here by the portal; the call is under ${edip})`}
                </span>
              </FactCell>
              <FactCell label="Funder country"><CountryLabel code={call.funderCountry} className="font-sans" /></FactCell>
              {call.fundingRate && <FactCell label="Funding rate"><span className="font-sans">{call.fundingRate}</span></FactCell>}
              {call.publishedAt && (
                <FactCell label="Dated by the source"><time dateTime={call.publishedAt}>{formatDateUtc(call.publishedAt)} UTC</time></FactCell>
              )}
            </FactsGrid>
            <p className="m-0 text-small text-ink-muted">
              What do these terms mean? In the <Link href="/glossary" className="font-semibold">glossary</Link>:
              {PROGRAMME_GLOSSARY[call.programme] && <> <Link href={`/glossary#${PROGRAMME_GLOSSARY[call.programme]}`} className="font-semibold">{programme.label}</Link>,</>}
              {call.regime === 'dual-use' && <> <Link href="/glossary#dual-use" className="font-semibold">dual-use (our label)</Link>,</>}
              {' '}<Link href="/glossary#call-and-topic" className="font-semibold">call and topic budget</Link>,
              {' '}<Link href="/glossary#date-only-deadline" className="font-semibold">date-only deadline</Link>.
            </p>
          </Card>
        )}
        side={(
          <div className="flex flex-col gap-4 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
            <DeadlineBadge info={d} opening={opens} size="lg" className="hidden w-full lg:flex" />
            <SaveButton kind="call" refId={call.id} />
            <FollowButton kind="programme" refId={call.programme} label={`Follow ${programme.label}`} />
            {/* WP-91: the call's deadline (and its opening day, before it opens) as a calendar file */}
            {!closed && (call.deadline || (upcoming && call.openingDate)) && (
              <a href={`/funding.ics?call=${call.slug}`} download className="inline-flex min-h-11 items-center gap-2 self-start text-small font-bold" data-call-ics>
                <Icon icon={CalendarPlus} size="inline" />Add to my calendar (.ics)
              </a>
            )}
            {sourceUrl ? (
              <Button href={sourceUrl} external variant="text" className="self-start">View original at {sourceDisplay(call.source.sourceName)}</Button>
            ) : (
              <p className="m-0 text-small text-ink-muted">The source gives no link to this call.</p>
            )}
            <AlertsLine />
          </div>
        )}
      >
        {hasScope && (
          <Panel title="Scope">
            <FactsGrid className={IN_CARD}>
              {call.actionType && <Fact label={<Link href="/glossary#action-type">Action type</Link>}>{call.actionType}</Fact>}
              {call.scope.length > 0 && (
                <Fact label="Topics" wide>
                  <span className="flex min-w-0 flex-wrap gap-2">{call.scope.map((s) => <Tag key={s} wrap>{s}</Tag>)}</span>
                </Fact>
              )}
            </FactsGrid>
          </Panel>
        )}

        <Panel title="Who can apply">
          {who.length > 0 ? (
            <>
              <FactsGrid className={IN_CARD} items={whoRows.map((e) => ({ label: e.label, value: <LongText text={e.value} />, wide: isLong(e.value) }))} />
              <p className="m-0 text-small text-ink-muted">In the source’s own words. The official call text is authoritative.</p>
            </>
          ) : (
            <p className="m-0 text-body text-ink-muted">The source does not say who may apply.</p>
          )}
          {sourceUrl ? (
            <Button href={sourceUrl} external variant="secondary" className="self-start whitespace-normal text-left">See the official call text at {sourceDisplay(call.source.sourceName)}</Button>
          ) : (
            <p className="m-0 text-body text-ink-muted">The source gives no link to this call. Search for “{call.topicId}” at {sourceDisplay(call.source.sourceName)}.</p>
          )}
        </Panel>

        {call.rulesApply && (
          <Panel title="Rules that apply">
            <RulesApplyBlock block={call.rulesApply} canApplyPanel={canApply} />
          </Panel>
        )}

        {ukraine && (
          <Panel title="Ukrainian participants">
            <p className="m-0 text-body">
              {ukraine}{' '}
              {/* WP-91: the territory note concerns a Ukrainian company only (the saved profile's country) */}
              {call.openToUkraine === true && call.rulesApply?.regime.code === 'EDIP-USI' && <UkraineOnly>Entities established in the non-government controlled areas of Ukraine are not eligible. </UkraineOnly>}
              See the <Link href="/glossary#open-to-ukraine" className="font-semibold">glossary</Link>.
            </p>
            {call.ukraineBasis?.evidence && (
              <p className="m-0 text-small text-ink-muted">
                {UKRAINE_BASIS[call.ukraineBasis.reason] ?? 'Source'}: <q className="italic">{call.ukraineBasis.evidence}</q>
              </p>
            )}
          </Panel>
        )}

        {call.documentEligibility ? (
          <Panel title="Can you apply?">
            <EligibilityCheck facts={call.documentEligibility.facts} documentUrl={call.documentEligibility.documentUrl} readAt={formatDateUtc(call.documentEligibility.extractedAt)}
              basis={call.documentEligibility.basis} sources={call.documentEligibility.sources} callId={call.id} closed={closed}
              ctx={{ programme: call.programme, topic: call.topicId }} />
          </Panel>
        ) : call.eligibilityState === 'not_read' ? (
          <Panel title="Can you apply?">
            <p className="m-0 text-body">
              The rules for this call have not been read yet, so there is no verdict here. They are written
              {(call.eligibilitySources ?? []).some((s) => s.scope === 'general') ? ' in the work programme’s general annexes' : ' in the source’s documents'}
              {(call.eligibilitySources ?? []).some((s) => s.scope === 'topic') ? ' and in this topic’s own conditions (under “Conditions as published by the source”)' : ''}.
              Read them at the source before you apply.
            </p>
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {(call.eligibilitySources ?? []).filter((s) => s.url && safeHttpUrl(s.url)).map((s) => (
                <li key={s.url}>
                  <a href={safeHttpUrl(s.url!) ?? '#'} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-2 break-words text-body font-semibold">
                    {s.label}<Icon icon={ExternalLink} size="inline" /><span className="sr-only">(opens in new tab)</span>
                  </a>
                </li>
              ))}
            </ul>
            {!closed && <div className="border-t border-line pt-5"><CallReadiness callId={call.id} /></div>}
          </Panel>
        ) : defenceFund && !closed ? (
          // EDF and EDIP calls have readiness rules even when no document was read (WP-29).
          <Panel title="Can you apply?">
            <CallReadiness callId={call.id} />
          </Panel>
        ) : null}

        {call.partnerArea && (
          <Panel title="Partners from earlier projects">
            <PartnerSuggestions callSlug={call.slug} />
          </Panel>
        )}

        {call.cascade !== null && call.cascade !== undefined && (
          <Panel title="Cascade funding">
            {call.cascade ? (
              <p className="m-0 text-body">
                This call has cascade funding: the projects it funds may pass part of the money to third parties, usually small firms, by calls of their own.
                See the <Link href="/glossary#cascade-funding" className="font-semibold">glossary</Link>.
              </p>
            ) : (
              <p className="m-0 text-body">The call’s document says the projects may not pass money on to third parties (no cascade funding).</p>
            )}
            {call.cascadeBasis?.evidence && (
              <p className="m-0 text-small text-ink-muted">
                {CASCADE_BASIS[call.cascadeBasis.reason] ?? 'Source'}: <q className="italic">{call.cascadeBasis.evidence}</q>
              </p>
            )}
          </Panel>
        )}

        <Panel title="Terms">
          {terms.length > 0 ? (
            <FactsGrid className={IN_CARD} items={terms.map((e) => ({ label: e.label, value: e.value, wide: isLong(e.value) }))} />
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
            <p className="m-0 text-small text-ink-muted">Linked from the call at {sourceDisplay(call.source.sourceName)}. They are the source’s documents, not ours.</p>
          </Panel>
        )}

        {call.conditionsText && (
          // The source's own text, unedited. Not prose of ours. The first ~600 characters are on the page, the whole text is one tap away.
          <Card title="Conditions as published by the source" anchor="conditions" id="conditions-heading" className="scroll-mt-4">
            <LongText text={call.conditionsText} pre />
          </Card>
        )}

        <Panel title="Source and attribution">
          <SourceBadge source={call.source} />
        </Panel>
      </DetailLayout>

      {related.length > 0 && (
        <section aria-labelledby="related" className="flex flex-col gap-4">
          <h2 id="related" className="m-0 scroll-mt-4 text-h2">Related calls</h2>
          <ul className="m-0 flex list-none flex-col gap-4 p-0">
            {related.map((c) => <li key={c.id} className="min-w-0"><CallCard call={c} headingLevel="h3" /></li>)}
          </ul>
        </section>
      )}
    </>
  );
}
