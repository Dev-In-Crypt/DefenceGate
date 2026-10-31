import type { Metadata } from 'next';
import Link from 'next/link';
import { Printer } from 'lucide-react';
import { notFound, permanentRedirect } from 'next/navigation';
import { getHealth, getTender, getTenderMoved, getTenders, getTenderVersions, isTenderSlug, REMOVED, whenRemoved, type TenderMoved } from '@/lib/api';
import { EmptyState } from '@/components/dg/feedback';
import { RemovedOnRequest } from '@/components/dg/removed';
import { getTenderDeadline, localDeadline } from '@/lib/deadline';
import { VALUE_MISSING_MEANS, sourceDisplay, valueMissingNote, valueMissingNotes } from '@/lib/source-status';
import { displayName } from '@/lib/display-name';
import { formatDateUtc, formatMoney, isPlaceholderAmount, noticeDateLabel } from '@/lib/format';
import { correctionLines, setAsideNote, versionCountLine, winnersNotReadLine } from '@/lib/award-lines';
import { safeHttpUrl } from '@/lib/safe-url';
import { buildMetadata, tenderCanonicalPath, tenderMeetsMinimumContent, tenderTitle } from '@/lib/seo';
import { AWARD_VALUE_LABEL, AWARD_NOTICE_VALUE_LABEL, noticeValueLabel, sourceStatusWord, tenderChangedLabel, valueKindLabel } from '@/lib/tender-status';
import { WHO_MAY_BID_NOTE, WHO_MAY_BID_UNKNOWN, whoMayBid, winnersHref } from '@/lib/who-may-bid';
import { cpvName } from '@/lib/cpv';
import { countryName, isNonEnglish, legalBasisLabel, procedureLabel, TENDER_SCOPES } from '@/lib/taxonomy';
import { clearanceView, scopeGroupNote, subcontractingView } from '@/lib/tender-basis';
import { cn } from '@/lib/utils';
import { Tag } from '@/components/dg/tag';
import { DeadlineBadge } from '@/components/dg/deadline-badge';
import { AmountDisplay, CountryLabel, FactCell, LangLabel } from '@/components/dg/data-display';
import { SourceBadge } from '@/components/dg/source-badge';
import { VersionTimeline } from '@/components/dg/version-timeline';
import { Button } from '@/components/dg/button';
import { AboutData } from '@/components/dg/about-data';
import { Details } from '@/components/dg/details';
import { Card, slugId } from '@/components/dg/card';
import { AlertsLine } from '@/components/dg/alerts-line';
import { BasisChips, ClassifiedNote } from '@/components/dg/basis-chips';
import { PageHeader } from '@/components/dg/page-header';
import { DetailLayout } from '@/components/dg/detail-layout';
import { FactsGrid } from '@/components/dg/facts-grid';
import { AnomalyNote, TenderCard, TenderStatusPills } from '@/components/dg/cards';
import { FollowButton, SaveButton } from '@/components/account/save-button';
import { ContractPeriodText } from '@/components/tenders/contract-period';

export const revalidate = 300;
type Props = { params: Promise<{ slug: string }> };

const RELATED_LIMIT = 3;
/** WP-100: a title longer than this is cut to four lines on a phone (about 18 characters a line at the phone's title size). */
const LONG_TITLE = 80;
/** WP-106: what another notice of the procedure is, by its stored status. */
const STAGE_WORD: Record<string, string> = { awarded: 'Award notice', cancelled: 'Cancellation', forthcoming: 'Prior information notice' };
const ROW = 'grid gap-1 break-words py-2.5 sm:grid-cols-[160px_minmax(0,1fr)] sm:gap-4';
/** The facts grid inside a titled card: the card's own header rule stands in for the first hairline. */
const IN_CARD = 'border-b-0 [&>div:first-child]:border-t-0';

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const tender = await getTender((await params).slug).catch(whenRemoved);
  if (tender === REMOVED) return { title: 'Removed on request', robots: { index: false } };
  if (!tender) {
    const moved = await getTenderMoved((await params).slug).catch(() => null);
    return { title: moved?.left ? LEFT_SCOPE : 'Tender not found', robots: { index: false } };
  }
  const d = getTenderDeadline(tender);
  // Structured fields only: buyer, deadline, value, source.
  const description = [
    `${displayName(tender.buyerName, 'title')}.`,
    d.iso ? `Deadline ${d.utc}.` : 'No deadline stated.',
    `${noticeValueLabel(tender)} ${tender.estimatedValue ? formatMoney(tender.estimatedValue) : 'not stated'}.`,
    `Source: ${tender.source.sourceName}.`,
  ].join(' ');
  return buildMetadata({
    title: tenderTitle(tender),
    description,
    path: tenderCanonicalPath(tender),
    // The sitemap lists core-scope notices only; a notice that only supplies a defence buyer is not promoted.
    noindex: !tenderMeetsMinimumContent(tender) || tender.scope !== 'core',
  });
}

const LEFT_SCOPE = 'No longer in our defence scope';

/** WP-121: the page of a notice we held that left the defence scope: what it was and where the original is, nothing more. */
function LeftScope({ left }: { left: NonNullable<TenderMoved['left']> }) {
  const url = safeHttpUrl(left.url);
  return (
    <EmptyState level="h1" title={LEFT_SCOPE} action={<Button href="/tenders">Browse tenders</Button>}>
      This address was the page of a notice we no longer list: on a later reading it is not a defence purchase.{' '}
      {url
        ? <>The original: <a href={url} rel="noopener noreferrer" className="font-semibold">{left.title || left.noticeId}</a> ({left.sourceName}, notice {left.noticeId}).</>
        : <>It was {left.title ? `“${left.title}”, ` : ''}notice {left.noticeId} of {left.sourceName}.</>}
    </EmptyState>
  );
}

function Panel({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return <Card title={title} id={slugId(title)} className={className}>{children}</Card>;
}

const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export default async function TenderDetailPage({ params }: Props) {
  const { slug } = await params;
  // A slug that cannot be a tender never reaches the API.
  if (!isTenderSlug(slug)) notFound();
  // The archive and the source list need only the slug: read together with the notice, not after it.
  const versionsRead = getTenderVersions(slug);
  const healthRead = getHealth();
  versionsRead.catch(() => undefined); // handled below if they are used; not an unhandled rejection if the page ends first
  healthRead.catch(() => undefined);
  const tender = await getTender(slug).catch(whenRemoved);
  if (tender === REMOVED) return <RemovedOnRequest what="notice" />;
  if (!tender) {
    // WP-121 (p10): an old address of a notice that left the scope leads to its publication in scope, or says what it was
    const moved = await getTenderMoved(slug).catch(() => null);
    if (moved?.slug && isTenderSlug(moved.slug)) permanentRedirect(`/tenders/${moved.slug}`);
    if (moved?.left) return <LeftScope left={moved.left} />;
    notFound();
  }
  // The API looks up the leading id only; a changed title must not break a link.
  if (tender.slug !== slug && isTenderSlug(tender.slug)) permanentRedirect(`/tenders/${tender.slug}`);

  const [versions, health, sameBuyer] = await Promise.all([
    versionsRead,
    healthRead,
    tender.buyerId
      ? getTenders({ buyer: tender.buyerId, status: 'open', pageSize: RELATED_LIMIT + 1 }, { cacheable: true }).then((r) => r.items).catch(() => [])
      : Promise.resolve([]),
  ]);
  // Not this notice, and not its twin in another source (the API collapses twins within a list; a list
  // fetched before the link was made, or kept by the cache, may still carry both).
  const twinIds = new Set((tender.sameNotice ?? []).map((s) => s.id).filter(Boolean));
  const related = sameBuyer.filter((t) => t.id !== tender.id && !twinIds.has(t.id)).slice(0, RELATED_LIMIT);
  const sourceNames = new Map(health.sources.map((s) => [s.id, s.name]));

  const d = getTenderDeadline(tender);
  const local = d.state === 'closed' ? null : localDeadline(d.iso, tender.country, d.dateOnly);
  const missingNote = valueMissingNote(valueMissingNotes(health.sources), tender.source.sourceId);
  const closed = d.state === 'closed';
  const nonEnglish = isNonEnglish(tender.titleLanguage);
  const sourceUrl = safeHttpUrl(tender.source.url);
  const documentsUrl = safeHttpUrl(tender.documentsUrl ?? null);
  // WP-90: our own re-readings fold away under the publisher's changes
  const ownVersions = versions.filter((v) => !v.correction);
  const corrections = versions.filter((v) => v.correction);
  const legal = tender.legalBasis ? legalBasisLabel(tender.legalBasis) : null;
  // The main code first, then the rest, each once.
  const cpvCodes = [...new Set([...(tender.cpv ? [tender.cpv] : []), ...tender.cpvCodes])];
  // Capitals are shown in sentence or title case; the stored title and buyer are untouched.
  const title = displayName(tender.title);
  const buyer = displayName(tender.buyerName, 'title');
  const sourceStatus = sourceStatusWord(tender);
  const lots = tender.lots ?? tender.lotCount;
  const procedureEn = tender.procedure ? procedureLabel(tender.procedure) : null;
  const clearance = clearanceView(tender);
  const subcontracting = subcontractingView(tender);
  const otherBuyers = tender.otherBuyers ?? [];
  const awardedTo = tender.awardedTo ?? [];
  const awardedPersons = tender.awardedPersons ?? 0;
  const award = tender.awardValue && !isPlaceholderAmount(tender.awardValue.amount) ? tender.awardValue : null;
  const notRead = winnersNotReadLine(tender);       // WP-103
  const setAside = setAsideNote(award);
  // WP-100: four lines of the phone's title size hold about this much
  const longTitle = title.length > LONG_TITLE;
  // WP-106: who may bid by the legal basis, who wins under the notice's code, the procedure's other notices
  const bid = whoMayBid(tender.legalBasis);
  const winners = winnersHref(tender.cpv, tender.country);
  const stages = tender.stages ?? [];

  return (
    <>
      <PageHeader
        crumbs={[
          { label: 'Home', href: '/' }, { label: 'Tenders', href: '/tenders' },
          { label: title, href: `/tenders/${tender.slug}`, lang: nonEnglish ? (tender.titleLanguage ?? undefined) : undefined },
        ]}
        eyebrow={(
          <div className="flex flex-wrap items-center gap-2">
            {tender.cpv && <Tag kind="programme">CPV {tender.cpv}</Tag>}
            <TenderStatusPills tender={tender} />
          </div>
        )}
        title={title}
        // WP-100: on a phone a long title is cut to four lines (the whole of it is under "Full title"), so the deadline and the
        // link to the original are on the first screen: a notice whose description is its title put them 2,000 and 4,200 px down
        titleProps={{ lang: nonEnglish ? (tender.titleLanguage ?? undefined) : undefined, className: cn(closed ? 'text-ink-muted' : 'text-ink', longTitle && 'max-lg:line-clamp-4') }}
      >
        {longTitle && (
          <details className="text-small lg:hidden" data-full-title>
            <summary className="min-h-11 cursor-pointer py-2 font-bold">Full title</summary>
            <p className="m-0 max-w-prose text-body" lang={nonEnglish ? (tender.titleLanguage ?? undefined) : undefined}>{title}</p>
          </details>
        )}
        {/* WP-100: the deadline and the original first on a phone (from lg they head the side column) */}
        <div className="d-top flex flex-col gap-3 rounded-lg border border-transparent bg-surface p-4 sm:p-5 lg:hidden" data-phone-first>
          <DeadlineBadge info={d} size="lg" className="w-full" local={local} />
          {sourceUrl && (
            <Button href={sourceUrl} external variant="text" className="self-start">View original at {sourceDisplay(tender.source.sourceName)}</Button>
          )}
        </div>
        {/* WP-150: the facts a reader decides on, on the first screen at 1440 and 375 px: the value, the deadline and the buyer (the
            status is in the tags above; on a phone the deadline is the box above). The full facts stay in Key facts. */}
        <div data-head-facts>
        <FactsGrid className="facts-grid--4">
          <FactCell label={award ? AWARD_VALUE_LABEL[award.kind] : noticeValueLabel(tender)}>
            <AmountDisplay money={award ? { amount: award.amount, currency: award.currency } : tender.estimatedValue} />
          </FactCell>
          {/* from lg; on a phone the deadline box above says it */}
          <FactCell label="Deadline" tone={closed ? 'closed' : 'default'} className="max-lg:hidden">
            {d.iso
              ? <><time dateTime={d.iso}>{d.utc}</time>{d.countdown && <span className="block font-sans text-small font-normal text-ink-muted">{d.countdown}</span>}</>
              : <span className="font-sans">{d.label}</span>}
          </FactCell>
          <FactCell label={otherBuyers.length > 0 ? 'Buyers' : 'Buyer'} className="min-[360px]:col-span-2">
            <span className="font-sans text-body">
              {tender.buyerSlug
                ? <Link href={`/buyers/${tender.buyerSlug}`} className="py-2 font-semibold">{buyer}</Link>
                : <span className="font-semibold">{buyer}</span>}
              {/* WP-95: every buyer of a joint procurement, as the notice names them */}
              {otherBuyers.length > 0 && <span data-other-buyers>{otherBuyers.map((b) => `; ${displayName(b, 'title')}`).join('')} (joint procurement)</span>}
            </span>
          </FactCell>
        </FactsGrid>
        </div>
        {/* the source's own words and the method lines under the facts */}
        {nonEnglish && <LangLabel kind="language" code={tender.titleLanguage} />}
        {tender.originalTitle && (
          <p className="m-0 max-w-prose text-body text-ink-muted">
            <span lang={tender.originalLanguage ?? undefined}>{displayName(tender.originalTitle)}</span>
            {' · '}<LangLabel kind="title" code={tender.originalLanguage} />
          </p>
        )}
        {/* WP-95: who the award names; natural persons are counted, never named */}
        {(awardedTo.length > 0 || awardedPersons > 0) && (
          <p className="m-0 max-w-prose text-body" data-awarded-to>
            <span className="text-ink-muted">Awarded to: </span>
            {awardedTo.map((w, i) => (
              <span key={`${w.name}-${i}`}>
                {i > 0 && '; '}
                {w.slug ? <Link href={`/suppliers/${w.slug}`} className="py-2 font-semibold">{displayName(w.name, 'title')}</Link> : <span className="font-semibold">{displayName(w.name, 'title')}</span>}
                {w.country ? ` (${w.country})` : ''}
              </span>
            ))}
            {awardedPersons > 0 && `${awardedTo.length > 0 ? '; and ' : ''}${awardedPersons === 1 ? 'a natural person' : `${awardedPersons} natural persons`}, not named`}
          </p>
        )}
        {/* WP-103: an award whose winners have not been read is said to be so, not left to look like an award to nobody */}
        {notRead && (
          <p className="m-0 max-w-prose text-body" data-winners-not-read>
            <span className="text-ink-muted">Awarded to: </span>{notRead}
          </p>
        )}
        {/* WP-90: the subject in the notice's own words (its first sentence, commercial only: the API leaves out a specification or a contact) */}
        {tender.subject && (
          <p className="m-0 max-w-prose text-body" data-subject>
            <span className="text-ink-muted">Subject, as the notice states it: </span>{tender.subject}
          </p>
        )}
        <BasisChips tender={tender} />
        {tender.scope === 'supply' && (
          <p className="m-0 max-w-prose text-small text-ink-muted">{scopeGroupNote(tender.qualifiedBy) ?? TENDER_SCOPES.supply.hint}</p>
        )}
      </PageHeader>

      <DetailLayout
        // Deadline first on mobile: the hero element, in the page header now (WP-100)
        facts={(
          <Card title="Key facts">
            <FactsGrid className={IN_CARD}>
              {/* WP-95: an award's value says what it is: the contract awarded, a framework ceiling, or the estimate */}
              {award ? (
                <FactCell label={AWARD_VALUE_LABEL[award.kind]}>
                  <AmountDisplay money={{ amount: award.amount, currency: award.currency }} size="lg" />
                  {award.kind === 'framework' && <div className="mt-1 font-sans text-small font-normal text-ink-muted">The most that may be bought under the framework agreement, not a contract value</div>}
                  {award.kind === 'estimate' && !award.setAside && <div className="mt-1 font-sans text-small font-normal text-ink-muted">The award states no value; this is the buyer’s estimate</div>}
                  {/* WP-103: a published figure the notice's own estimate contradicts is said, and not used */}
                  {setAside && <div className="mt-1 font-sans text-small font-normal text-ink-muted" data-set-aside>{setAside}</div>}
                </FactCell>
              ) : (
              <FactCell label={noticeValueLabel(tender)}>
                <AmountDisplay money={tender.estimatedValue} size="lg" />
                {/* WP-113: a figure the notice does not state, taken from its TED twin, says where it is from */}
                {tender.estimatedValue && tender.valueFrom === 'ted_twin' && <div className="mt-1 font-sans text-small font-normal text-ink-muted" data-value-from-twin>Not stated in this notice; as given in the TED notice of the same procurement</div>}
                {(!tender.estimatedValue || isPlaceholderAmount(tender.estimatedValue.amount)) && missingNote && (
                  <div className="mt-1 font-sans text-small font-normal text-ink-muted">{missingNote}{missingNote.startsWith('No usable') && <> {VALUE_MISSING_MEANS}</>}</div>
                )}
                {/* WP-108 (p07, V7000 375694-2026): an award notice's total is what the award states, not the buyer's estimate */}
                {tender.estimatedValue && !isPlaceholderAmount(tender.estimatedValue.amount) && (noticeValueLabel(tender) === AWARD_NOTICE_VALUE_LABEL
                  ? <div className="mt-1 font-sans text-small font-normal text-ink-muted" data-award-notice-value>The total the award notice states; not told apart as a contract value or a framework ceiling</div>
                  : valueKindLabel(tender.valueKind) && <div className="mt-1 font-sans text-small font-normal text-ink-muted">{sentence(valueKindLabel(tender.valueKind) ?? '')}</div>)}
              </FactCell>
              )}
              <FactCell label="Notice ID">{tender.noticeId}</FactCell>
              <FactCell label={tender.publishedAt || !tender.noticeDate ? 'Published' : 'Notice date'}>
                {tender.publishedAt
                  ? <time dateTime={tender.publishedAt}>{formatDateUtc(tender.publishedAt)} UTC</time>
                  : <span className="font-sans">{noticeDateLabel(tender) ?? 'Publication date not stated by the source'}</span>}
              </FactCell>
              <FactCell label="Procedure">
                <span className="font-sans">{procedureEn ?? tender.procedure ?? 'Not available'}</span>
                {tender.procedureFrom === 'ted_twin' && <div className="mt-1 font-sans text-small font-normal text-ink-muted">Not stated in this notice; as given in the TED notice of the same procurement</div>}
                {procedureEn && <div className="mt-1 font-sans text-small font-normal text-ink-muted">As stated: {tender.procedure}</div>}
              </FactCell>
              {/* WP-160: the contract period the notice states, with where its end comes from; free for everyone */}
              {tender.contractPeriod && (
                <FactCell label="Contract period">
                  <ContractPeriodText p={tender.contractPeriod} className="font-normal" />
                  {tender.contractPeriod.end && <Link href="/tenders/ending" className="mt-1 inline-flex min-h-8 items-center font-sans text-small font-bold">Contracts ending soon</Link>}
                </FactCell>
              )}
              <FactCell label="Legal basis">
                {tender.legalBasis ? (
                  legal ? (
                    <>
                      <span className="font-sans">{legal}</span>
                      {tender.legalBasis.trim().toLowerCase() !== 'other' && /^3\d{4}L\d{4}$/i.test(tender.legalBasis.trim()) && (
                        <div className="mt-1 font-mono text-small font-normal text-ink-muted">Code {tender.legalBasis}</div>
                      )}
                    </>
                  ) : <span className="font-sans">{tender.legalBasis}</span>
                ) : <span className="font-sans">Not available</span>}
              </FactCell>
              <FactCell label="Buyer country">
                {tender.country ? <CountryLabel code={tender.country} className="font-sans" /> : <span className="font-sans">Not available</span>}
              </FactCell>
              <FactCell label="Security clearance">
                <span className="font-sans">{clearance.text}</span>
                {clearance.hint && <div className="mt-1 font-sans text-small font-normal text-ink-muted">{clearance.hint}</div>}
              </FactCell>
              <FactCell label="Subcontracting"><span className="font-sans">{subcontracting.text}</span></FactCell>
              {/* Awarded, cancelled and planned are read from the type of notice (TED) or the source's own status; "Closing soon" is ours and is not shown here. */}
              {sourceStatus && <FactCell label="Status read from the notice"><span className="font-sans">{sourceStatus}</span></FactCell>}
              {typeof lots === 'number' && lots > 0 && <FactCell label="Lots">{lots}</FactCell>}
            </FactsGrid>
            <AnomalyNote tender={tender} />
          </Card>
        )}
        side={(
          <div className="flex flex-col gap-4 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
            <DeadlineBadge info={d} size="lg" className="hidden w-full lg:flex" local={local} />
            <SaveButton kind="tender" refId={tender.id} />
            {tender.buyerId && <FollowButton kind="buyer" refId={tender.buyerId} label="Follow this buyer" />}
            {sourceUrl && (
              <Button href={sourceUrl} external variant="text" className="self-start">View original at {sourceDisplay(tender.source.sourceName)}</Button>
            )}
            {documentsUrl && documentsUrl !== sourceUrl && (
              <Button href={documentsUrl} external variant="text" className="self-start" data-documents>Procurement documents</Button>
            )}
            {documentsUrl && documentsUrl === sourceUrl && <p className="m-0 text-small text-ink-muted">The original is where the procurement documents are.</p>}
            <Button href={`/tenders/${tender.slug}/evidence`} variant="text" icon={Printer} className="self-start">Print evidence</Button>
            <AlertsLine />
          </div>
        )}
      >
        {/* WP-106 (p02, p08): who may bid, as the legal basis says it, and who has won contracts under the same code */}
        <Panel title="Who may bid">
          <div className="flex flex-col gap-2" data-who-may-bid>
            {bid ? (
              <>
                <p className="m-0 max-w-prose text-small font-semibold">{bid.act}</p>
                <p className="m-0 max-w-prose text-body">{bid.text}</p>
              </>
            ) : <p className="m-0 max-w-prose text-body">{WHO_MAY_BID_UNKNOWN}</p>}
            <p className="m-0 max-w-prose text-small text-ink-muted">{WHO_MAY_BID_NOTE}</p>
            {winners && (
              <Link href={winners} className="inline-flex min-h-11 items-center self-start text-small font-bold" data-who-wins>
                Who wins such contracts{tender.country ? ` in ${countryName(tender.country)}` : ''}
              </Link>
            )}
          </div>
        </Panel>

        {/* WP-106 (p06): the call of an award and the award of a call, by the procedure they share */}
        {stages.length > 0 && (
          <Panel title="Other notices of this procedure">
            <ul className="m-0 flex list-none flex-col p-0" data-stages>
              {stages.map((s, i) => (
                <li key={s.id} className={cn('flex flex-wrap items-baseline justify-between gap-2 py-2', i > 0 && 'border-t border-line')}>
                  <Link href={`/tenders/${s.slug}`} className="inline-flex min-h-11 items-center font-semibold">{STAGE_WORD[s.status ?? ''] ?? 'Call for competition'}</Link>
                  <span className="font-mono text-small text-ink-muted">{s.noticeId}{s.publishedAt ? ` · ${formatDateUtc(s.publishedAt)}` : ''}</span>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        {cpvCodes.length > 0 && (
          <Panel title="CPV codes">
            <ul className="m-0 flex list-none flex-col p-0">
              {cpvCodes.map((code, i) => {
                // WP-106: the official title the API reads from the full vocabulary, else the selection's or its group's
                const own = tender.cpvTitles?.[code];
                const label = own ? { label: own, exact: true } : cpvName(code);
                return (
                  <li key={code} className={cn(ROW, i > 0 && 'border-t border-line')}>
                    <span className="font-mono text-mono-strong tabular-nums">{code}{i === 0 && tender.cpv ? <span className="ml-2 font-sans text-label text-ink-muted">Main</span> : null}</span>
                    <span className="text-body">
                      {label ? (
                        label.exact ? label.label : <><span className="text-ink-muted">Within: </span>{label.label}</>
                      ) : <span className="text-ink-muted">Name not in our table</span>}
                    </span>
                  </li>
                );
              })}
            </ul>
          </Panel>
        )}

        {tender.sameNotice.length > 0 && (
          <Panel title="Same notice in other sources">
            <ul className="m-0 flex list-none flex-col p-0">
              {tender.sameNotice.map((n, i) => {
                const url = safeHttpUrl(n.url);
                const name = sourceDisplay(sourceNames.get(n.source) ?? n.source);
                return (
                  <li key={`${n.source}-${i}`} className={cn('flex flex-wrap items-center justify-between gap-2 py-2', i > 0 && 'border-t border-line')}>
                    <span className="text-body font-semibold">{name}{n.noticeId && <span className="ml-2 font-mono text-small font-normal text-ink-muted">{n.noticeId}</span>}</span>
                    {/* WP-90: a working link always: the notice at its source when it gives an address, and its own page here */}
                    <span className="flex flex-wrap gap-x-4">
                      {n.id && <Link href={`/tenders/${n.id}`} className="inline-flex min-h-11 items-center text-small font-bold" data-same-notice-page>Open this copy here</Link>}
                      {url && <Button href={url} external variant="text">View at {name}<span className="sr-only"> (opens in new tab)</span></Button>}
                    </span>
                  </li>
                );
              })}
            </ul>
          </Panel>
        )}

        <Panel title="Version history">
          {/* WP-103: the count is of the versions listed; DefenceGate's own corrections are counted apart, under it (persona p10: "3 versions observed" over one) */}
          <p className="m-0 text-small text-ink-muted" data-version-count>{versionCountLine(ownVersions.length, corrections.length)}</p>
          <AboutData summary="What counts as a new version">
            <p className="m-0">
              We keep a new version when the title, buyer, country, procedure, legal basis, value, currency, publication date, deadline, product codes, source link or status changes. Earlier versions are never overwritten or deleted. History starts when we first saw the notice; our archive began in September 2026.
            </p>
          </AboutData>
          {versions.length > 0
            ? <VersionTimeline versions={ownVersions} />
            : <p className="m-0 text-body text-ink-muted">The version history could not be read for this notice.</p>}
          {corrections.length > 0 && (
            <div data-corrections className="flex flex-col gap-2">
              {/* WP-108 (p10: "2 corrections (below)" with nothing below while the fold was closed): each correction in one line, open, with its date, fields, before and after; the fold keeps the full entries */}
              <ul className="m-0 flex list-none flex-col gap-1 p-0 text-small" data-correction-lines>
                {correctionLines(corrections).map((line, i) => <li key={i} className="min-w-0 break-words">{line}</li>)}
              </ul>
              <Details summary={`${corrections.length} ${corrections.length === 1 ? 'correction' : 'corrections'} by DefenceGate, not changes by the publisher`}>
                <VersionTimeline versions={corrections} />
              </Details>
            </div>
          )}
        </Panel>

        <Panel title="Source and attribution">
          <SourceBadge source={tender.source} retrievedLabel={tenderChangedLabel(tender.source)} version={tender.versionCount > 1 ? `v${tender.versionCount}` : undefined} />
        </Panel>
      </DetailLayout>

      {related.length > 0 && tender.buyerSlug && (
        <section aria-labelledby="related" className="flex flex-col gap-4 print:hidden">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="related" className="m-0 text-h2">More from this buyer</h2>
            <Link href={`/buyers/${tender.buyerSlug}`} className="inline-flex min-h-11 items-center text-small font-bold">All tenders from {buyer}</Link>
          </div>
          <ClassifiedNote tenders={related} />
          <ul className="m-0 flex list-none flex-col gap-4 p-0">
            {related.map((t) => <li key={t.id} className="min-w-0"><TenderCard tender={t} headingLevel="h3" classifiedNote={false} /></li>)}
          </ul>
        </section>
      )}
    </>
  );
}
