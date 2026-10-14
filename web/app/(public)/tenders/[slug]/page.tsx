import type { Metadata } from 'next';
import Link from 'next/link';
import { Printer } from 'lucide-react';
import { notFound, permanentRedirect } from 'next/navigation';
import { getHealth, getTender, getTenders, getTenderVersions, isTenderSlug } from '@/lib/api';
import { getTenderDeadline } from '@/lib/deadline';
import { displayName } from '@/lib/display-name';
import { formatDateUtc, formatMoney, isPlaceholderAmount } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { buildMetadata, tenderMeetsMinimumContent } from '@/lib/seo';
import { TENDER_CHANGED_LABEL, sourceStatusWord, valueKindLabel } from '@/lib/tender-status';
import { cpvName } from '@/lib/cpv';
import { isNonEnglish, legalBasisLabel, procedureLabel, TENDER_SCOPES } from '@/lib/taxonomy';
import { clearanceView, subcontractingView } from '@/lib/tender-basis';
import { cn } from '@/lib/utils';
import { Breadcrumbs } from '@/components/dg/feedback';
import { Tag } from '@/components/dg/tag';
import { DeadlineBadge } from '@/components/dg/deadline-badge';
import { AmountDisplay, CountryLabel, FactCell, LangLabel } from '@/components/dg/data-display';
import { SourceBadge } from '@/components/dg/source-badge';
import { VersionTimeline } from '@/components/dg/version-timeline';
import { Button } from '@/components/dg/button';
import { AlertsLine } from '@/components/dg/alerts-line';
import { BasisChips } from '@/components/dg/basis-chips';
import { AnomalyNote, TenderCard, TenderStatusPills } from '@/components/dg/cards';
import { FollowButton, SaveButton } from '@/components/account/save-button';

export const revalidate = 300;
type Props = { params: Promise<{ slug: string }> };

const RELATED_LIMIT = 3;
const ROW = 'grid gap-1 break-words py-3 sm:grid-cols-[200px_minmax(0,1fr)] sm:gap-4';

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const tender = await getTender((await params).slug);
  if (!tender) return { title: 'Tender not found', robots: { index: false } };
  const d = getTenderDeadline(tender);
  // Structured fields only: buyer, deadline, value, source.
  const description = [
    `${displayName(tender.buyerName, 'title')}.`,
    d.iso ? `Deadline ${d.utc}.` : 'No deadline stated.',
    `Estimated value ${tender.estimatedValue ? formatMoney(tender.estimatedValue) : 'not stated'}.`,
    `Source: ${tender.source.sourceName}.`,
  ].join(' ');
  return buildMetadata({
    title: `${displayName(tender.title)} (${tender.noticeId})`,
    description,
    path: `/tenders/${tender.slug}`,
    // The sitemap lists core-scope notices only; a notice that only supplies a defence buyer is not promoted.
    noindex: !tenderMeetsMinimumContent(tender) || tender.scope !== 'core',
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

const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export default async function TenderDetailPage({ params }: Props) {
  const { slug } = await params;
  // A slug that cannot be a tender never reaches the API.
  if (!isTenderSlug(slug)) notFound();
  const tender = await getTender(slug);
  if (!tender) notFound();
  // The API looks up the leading id only; a changed title must not break a link.
  if (tender.slug !== slug && isTenderSlug(tender.slug)) permanentRedirect(`/tenders/${tender.slug}`);

  const [versions, health, sameBuyer] = await Promise.all([
    getTenderVersions(tender.slug),
    getHealth(),
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
  const closed = d.state === 'closed';
  const nonEnglish = isNonEnglish(tender.titleLanguage);
  const sourceUrl = safeHttpUrl(tender.source.url);
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

  return (
    <>
      <Breadcrumbs items={[
        { label: 'Home', href: '/' }, { label: 'Tenders', href: '/tenders' },
        { label: title, href: `/tenders/${tender.slug}` },
      ]} />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-6">
          <header className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2">
              {tender.cpv && <Tag kind="programme">CPV {tender.cpv}</Tag>}
              <TenderStatusPills tender={tender} />
            </div>
            <div className="flex flex-col gap-2">
              <h1 lang={nonEnglish ? (tender.titleLanguage ?? undefined) : undefined}
                className={cn('m-0 break-words text-[32px] font-extrabold leading-10 tracking-[-1px] md:text-h1', closed ? 'text-ink-muted' : 'text-ink')}>{title}</h1>
              {nonEnglish && <LangLabel kind="language" code={tender.titleLanguage} />}
            </div>
            {tender.originalTitle && (
              <p className="m-0 text-body text-ink-muted">
                <span lang={tender.originalLanguage ?? undefined}>{displayName(tender.originalTitle)}</span>
                {' · '}<LangLabel kind="title" code={tender.originalLanguage} />
              </p>
            )}
            <p className="m-0 text-body">
              <span className="text-ink-muted">Buyer: </span>
              {tender.buyerSlug
                ? <Link href={`/buyers/${tender.buyerSlug}`} className="font-semibold">{buyer}</Link>
                : <span className="font-semibold">{buyer}</span>}
            </p>
            <BasisChips tender={tender} />
            {tender.scope === 'supply' && (
              <p className="m-0 text-small text-ink-muted">{TENDER_SCOPES.supply.hint}</p>
            )}
          </header>

          {/* Deadline first on mobile: the hero element */}
          <DeadlineBadge info={d} size="lg" className="w-full lg:hidden" />

          <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
            <FactCell label="Estimated value">
              <AmountDisplay money={tender.estimatedValue} size="lg" />
              {tender.estimatedValue && !isPlaceholderAmount(tender.estimatedValue.amount) && valueKindLabel(tender.valueKind) && (
                <div className="mt-1 font-sans text-small font-normal text-ink-muted">{sentence(valueKindLabel(tender.valueKind) ?? '')}</div>
              )}
            </FactCell>
            <FactCell label="Notice ID">{tender.noticeId}</FactCell>
            <FactCell label="Published">
              {tender.publishedAt
                ? <time dateTime={tender.publishedAt}>{formatDateUtc(tender.publishedAt)} UTC</time>
                : <span className="font-sans">Publication date not stated by the source</span>}
            </FactCell>
            <FactCell label="Procedure">
              <span className="font-sans">{procedureEn ?? tender.procedure ?? 'Not available'}</span>
              {tender.procedureFrom === 'ted_twin' && <div className="mt-1 font-sans text-small font-normal text-ink-muted">Not stated in this notice; as given in the TED notice of the same procurement</div>}
              {procedureEn && <div className="mt-1 font-sans text-small font-normal text-ink-muted">As stated: {tender.procedure}</div>}
            </FactCell>
            <FactCell label="Legal basis">
              {tender.legalBasis ? (
                legal ? (
                  <>
                    <span className="font-sans">{legal}</span>
                    {tender.legalBasis.trim().toLowerCase() !== 'other' && (
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
          </dl>
          <AnomalyNote tender={tender} />

          {cpvCodes.length > 0 && (
            <Panel title="CPV codes">
              <ul className="m-0 flex list-none flex-col p-0">
                {cpvCodes.map((code, i) => {
                  const label = cpvName(code);
                  return (
                    <li key={code} className={cn(ROW, i < cpvCodes.length - 1 && 'border-b border-line')}>
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
                  const name = sourceNames.get(n.source) ?? n.source;
                  return (
                    <li key={`${n.source}-${i}`} className={cn('flex flex-wrap items-center justify-between gap-2 py-3', i < tender.sameNotice.length - 1 && 'border-b border-line')}>
                      <span className="text-body font-semibold">{name}</span>
                      {url && <Button href={url} external variant="text">View at {name}<span className="sr-only"> (opens in new tab)</span></Button>}
                    </li>
                  );
                })}
              </ul>
            </Panel>
          )}

          <Panel title="Version history">
            <p className="m-0 text-small text-ink-muted">
              We keep a new version when the title, buyer, country, procedure, legal basis, value, currency, publication date, deadline, product codes, source link or status changes. Earlier versions are never overwritten or deleted. History starts when we first saw the notice; our archive began in September 2026.
              {' '}{versions.length > 1 ? `${versions.length} versions observed.` : 'One version observed so far.'}
            </p>
            {versions.length > 0
              ? <VersionTimeline versions={versions} />
              : <p className="m-0 text-body text-ink-muted">The version history could not be read for this notice.</p>}
          </Panel>

          <Panel title="Source and attribution">
            <SourceBadge source={tender.source} retrievedLabel={TENDER_CHANGED_LABEL} version={tender.versionCount > 1 ? `v${tender.versionCount}` : undefined} />
          </Panel>
        </div>

        <aside aria-label="Deadline and actions" className="flex flex-col gap-4 lg:sticky lg:top-4">
          <div className="flex flex-col gap-4 rounded-lg bg-surface p-6">
            <DeadlineBadge info={d} size="lg" className="hidden w-full lg:flex" />
            <SaveButton kind="tender" refId={tender.id} />
            {tender.buyerId && <FollowButton kind="buyer" refId={tender.buyerId} label="Follow this buyer" />}
            {sourceUrl && (
              <Button href={sourceUrl} external variant="text" className="self-start">View original at {tender.source.sourceName}</Button>
            )}
            <Button href={`/tenders/${tender.slug}/evidence`} variant="text" icon={Printer} className="self-start">Print evidence</Button>
            <AlertsLine />
          </div>
        </aside>
      </div>

      {related.length > 0 && tender.buyerSlug && (
        <section aria-labelledby="related" className="flex flex-col gap-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="related" className="m-0 text-h2">More from this buyer</h2>
            <Link href={`/buyers/${tender.buyerSlug}`} className="inline-flex min-h-11 items-center text-small font-bold">All tenders from {buyer}</Link>
          </div>
          <ul className="m-0 grid list-none gap-4 p-0 lg:grid-cols-3">
            {related.map((t) => <li key={t.id} className="min-w-0"><TenderCard tender={t} headingLevel="h3" /></li>)}
          </ul>
        </section>
      )}
    </>
  );
}
