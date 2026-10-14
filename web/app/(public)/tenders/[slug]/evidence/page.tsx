import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, permanentRedirect } from 'next/navigation';
import { getHealth, getTender, getTenderVersions, isTenderSlug } from '@/lib/api';
import { formatStamp } from '@/lib/account-format';
import { getTenderDeadline } from '@/lib/deadline';
import { formatDateUtc, formatMoney, isPlaceholderAmount } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { absoluteUrl, buildMetadata } from '@/lib/seo';
import { anomalyNotes, tenderStatusView, valueKindLabel } from '@/lib/tender-status';
import { cpvName } from '@/lib/cpv';
import { TENDER_SCOPES, countryName, isNonEnglish, languageName, legalBasisLabel, procedureLabel } from '@/lib/taxonomy';
import { basisChips, clearanceView, subcontractingView } from '@/lib/tender-basis';
import { cn } from '@/lib/utils';
import { Breadcrumbs } from '@/components/dg/feedback';
import { Button } from '@/components/dg/button';
import { PrintButton } from '@/components/dg/print-button';
import { VersionTimeline } from '@/components/dg/version-timeline';

/** The page states when it was generated, so it is rendered per request. Data still comes through the cached helpers. */
export const dynamic = 'force-dynamic';
type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const tender = await getTender((await params).slug);
  if (!tender) return { title: 'Tender not found', robots: { index: false } };
  return buildMetadata({
    title: `Evidence record: ${tender.title} (${tender.noticeId})`,
    description: 'A printable record of what DefenceGate holds for this notice, its source and its version history.',
    path: `/tenders/${tender.slug}/evidence`,
    noindex: true,
  });
}

const ROW = 'grid gap-1 py-2.5 sm:grid-cols-[200px_minmax(0,1fr)] sm:gap-4 print:py-1.5';
const PANEL = 'flex flex-col gap-3 rounded-lg bg-surface p-5 sm:p-6 print:break-inside-avoid print:rounded-none print:border-t print:border-line print:bg-transparent print:p-0 print:pt-4';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={cn(ROW, 'border-b border-line last:border-b-0')}>
      <dt className="text-small font-semibold text-ink-muted">{label}</dt>
      <dd className="m-0 min-w-0 break-words text-body text-ink">{children}</dd>
    </div>
  );
}
const Mono = ({ children }: { children: React.ReactNode }) => <span className="font-mono text-mono-strong tabular-nums">{children}</span>;
const NotStated = () => <span className="text-ink-muted">Not available</span>;

export default async function TenderEvidencePage({ params }: Props) {
  const { slug } = await params;
  if (!isTenderSlug(slug)) notFound();
  const tender = await getTender(slug);
  if (!tender) notFound();
  if (tender.slug !== slug && isTenderSlug(tender.slug)) permanentRedirect(`/tenders/${tender.slug}/evidence`);

  const [versions, health] = await Promise.all([getTenderVersions(tender.slug), getHealth()]);
  const sourceNames = new Map(health.sources.map((s) => [s.id, s.name]));
  const status = tenderStatusView(tender);
  const d = getTenderDeadline(tender);
  const notes = anomalyNotes(tender);
  const sourceUrl = safeHttpUrl(tender.source.url);
  const legal = tender.legalBasis ? legalBasisLabel(tender.legalBasis) : null;
  const cpvCodes = [...new Set([...(tender.cpv ? [tender.cpv] : []), ...(tender.cpvCodes ?? [])])];
  const shown = versions[0] ?? null;
  // The number a reader counts by (1 = first seen), not the archive's own row number, which has gaps.
  const versionNo = shown ? (shown.sequence ?? versions.length) : tender.versionCount;
  const pagePath = `/tenders/${tender.slug}`;
  const valueKind = valueKindLabel(tender.valueKind);
  const lang = (code: string | null) => (code ? languageName(code) : null);
  const generated = new Date().toISOString();
  const procedureEn = tender.procedure ? procedureLabel(tender.procedure) : null;
  const clearance = clearanceView(tender);
  const subcontracting = subcontractingView(tender);

  return (
    <>
      <div className="print:hidden">
        <Breadcrumbs items={[
          { label: 'Home', href: '/' }, { label: 'Tenders', href: '/tenders' },
          { label: tender.title, href: pagePath }, { label: 'Evidence record', href: `${pagePath}/evidence` },
        ]} />
      </div>

      <header className="flex flex-col gap-3">
        <p className="m-0 font-mono text-mono text-ink-muted">DefenceGate evidence record · generated {formatStamp(generated)}</p>
        <h1 lang={isNonEnglish(tender.titleLanguage) ? (tender.titleLanguage ?? undefined) : undefined}
          className="m-0 break-words text-[28px] font-extrabold leading-9 tracking-[-1px] md:text-h1 print:text-[22px] print:leading-7">{tender.title}</h1>
        <p className="m-0 text-body text-ink-muted">Notice {tender.noticeId} · {tender.buyerName} · {tender.source.sourceName}</p>
        <div className="flex flex-wrap items-center gap-3 print:hidden">
          <PrintButton>Print this record</PrintButton>
          <Button href={pagePath} variant="secondary">Back to the notice</Button>
        </div>
      </header>

      <section aria-labelledby="held" className={PANEL}>
        <h2 id="held" className="m-0 text-h3">What we hold</h2>
        <p className="m-0 text-small text-ink-muted">The fields below are as DefenceGate holds them. Normalised fields and the defence label are ours; they are not part of the original notice.</p>
        <dl className="m-0 flex flex-col">
          <Row label="Record">
            <Mono>{absoluteUrl(pagePath)}</Mono>
          </Row>
          <Row label="Notice number"><Mono>{tender.noticeId}</Mono></Row>
          <Row label="Title">
            <span lang={tender.titleLanguage ?? undefined}>{tender.title}</span>
            {tender.titleLanguage && <span className="text-ink-muted"> ({lang(tender.titleLanguage)})</span>}
          </Row>
          {tender.originalTitle && (
            <Row label="Other-language title">
              <span lang={tender.originalLanguage ?? undefined}>{tender.originalTitle}</span>
              {tender.originalLanguage && <span className="text-ink-muted"> ({lang(tender.originalLanguage)})</span>}
            </Row>
          )}
          <Row label="Buyer, as published">{tender.buyerName}</Row>
          {tender.buyerCanonicalName && tender.buyerCanonicalName !== tender.buyerName && (
            <Row label="Buyer record name">{tender.buyerCanonicalName}</Row>
          )}
          <Row label="Buyer country">
            {tender.country ? <><Mono>{tender.country}</Mono> {countryName(tender.country)}</> : <NotStated />}
          </Row>
          <Row label="Classification">
            {basisChips(tender).join('; ') || (TENDER_SCOPES[tender.scope]?.label ?? tender.scope)}
            <span className="text-ink-muted"> · classified automatically, not by the publisher</span>
          </Row>
          <Row label="CPV codes">
            {cpvCodes.length === 0 ? <NotStated /> : (
              <ul className="m-0 flex list-none flex-col gap-1 p-0">
                {cpvCodes.map((code, i) => {
                  const label = cpvName(code);
                  return (
                    <li key={code}>
                      <Mono>{code}</Mono>{i === 0 && tender.cpv ? <span className="text-ink-muted"> (main)</span> : null}
                      {label?.exact ? <span className="text-ink-muted"> · {label.label}</span> : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </Row>
          <Row label="Procedure">
            {tender.procedure ?? <NotStated />}
            {procedureEn && <span className="text-ink-muted"> · {procedureEn}</span>}
          </Row>
          <Row label="Legal basis">
            {tender.legalBasis ? <><Mono>{tender.legalBasis}</Mono>{legal && <span className="text-ink-muted"> · {legal}</span>}</> : <NotStated />}
          </Row>
          <Row label="Published">
            {tender.publishedAt ? <Mono>{formatDateUtc(tender.publishedAt)} UTC</Mono> : <span className="text-ink-muted">Publication date not stated by the source</span>}
          </Row>
          <Row label="Deadline">
            {d.iso ? (
              <>
                <Mono>{d.utc}</Mono>
                {d.dateOnly && <span className="text-ink-muted"> · the source gives a date, not a time of day</span>}
              </>
            ) : <span>No deadline stated</span>}
            {notes.map((n) => <span key={n} className="mt-1 block text-small text-ink-muted">{n}</span>)}
          </Row>
          <Row label="Estimated value">
            {tender.estimatedValue && !isPlaceholderAmount(tender.estimatedValue.amount)
              ? <><Mono>{formatMoney(tender.estimatedValue)}</Mono>{valueKind && <span className="text-ink-muted"> · {valueKind}</span>}</>
              : tender.estimatedValue
                ? <><NotStated /><span className="text-ink-muted"> · the notice gives {formatMoney(tender.estimatedValue)}, a placeholder</span></>
                : <NotStated />}
          </Row>
          {typeof (tender.lots ?? tender.lotCount) === 'number' && (tender.lots ?? tender.lotCount ?? 0) > 0 && <Row label="Lots"><Mono>{tender.lots ?? tender.lotCount}</Mono></Row>}
          <Row label="Status shown">{status.label}{tender.statusNative ? <span className="text-ink-muted"> · status word: {tender.statusNative}</span> : null}</Row>
          <Row label="Security clearance">{clearance.text}{clearance.hint && <span className="text-ink-muted"> · {clearance.hint}</span>}</Row>
          <Row label="Subcontracting">{subcontracting.text}</Row>
        </dl>
      </section>

      <section aria-labelledby="source" className={PANEL}>
        <h2 id="source" className="m-0 text-h3">Source and licence</h2>
        <dl className="m-0 flex flex-col">
          <Row label="Source">{tender.source.sourceName}</Row>
          <Row label="Original notice">
            {sourceUrl ? <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="break-all font-mono text-mono">{sourceUrl}</a> : <NotStated />}
          </Row>
          <Row label="Last changed in our archive"><Mono>{formatStamp(tender.source.retrievedAt)}</Mono></Row>
          <Row label="Licence">{tender.source.licence}</Row>
          <Row label="Attribution">{tender.source.attribution}</Row>
          {tender.sameNotice.length > 0 && (
            <Row label="Same notice elsewhere">
              <ul className="m-0 flex list-none flex-col gap-1 p-0">
                {tender.sameNotice.map((n, i) => {
                  const url = safeHttpUrl(n.url);
                  return (
                    <li key={`${n.source}-${i}`}>
                      {sourceNames.get(n.source) ?? n.source}
                      {url && <> · <a href={url} target="_blank" rel="noopener noreferrer" className="break-all font-mono text-mono">{url}</a></>}
                    </li>
                  );
                })}
              </ul>
            </Row>
          )}
        </dl>
      </section>

      <section aria-labelledby="versions" className={PANEL}>
        <h2 id="versions" className="m-0 text-h3">Version shown and history</h2>
        <p className="m-0 text-body">
          This record shows <strong>version {versionNo}</strong>
          {shown ? <>, first observed by DefenceGate on <Mono>{formatStamp(shown.detectedAt)}</Mono></> : null}.
          {' '}{versions.length > 1 ? `${versions.length} versions have been observed.` : versions.length === 1 ? 'One version has been observed.' : 'The version history could not be read when this page was generated.'}
        </p>
        <p className="m-0 text-small text-ink-muted">
          We keep a new version when the title, buyer, country, procedure, legal basis, value, currency, publication date, deadline, product codes, source link or status changes; earlier versions are not overwritten. History starts when we first saw the notice (our archive began in September 2026). A version is dated by when we observed it, which is not necessarily when the source made the change.
        </p>
        {versions.length > 0 && <VersionTimeline versions={versions} />}
      </section>

      <section aria-labelledby="authority" className={cn(PANEL, 'print:border-ink')}>
        <h2 id="authority" className="m-0 text-h3">The original is authoritative</h2>
        <p className="m-0 text-body">
          The original notice at {tender.source.sourceName} is the authoritative record. This page documents what DefenceGate held and when; it is not the notice, not an official publication and not legal advice. Confirm every fact at the source before you rely on it.
        </p>
        <p className="m-0 text-small text-ink-muted print:hidden">
          Back to the <Link href={pagePath} className="font-semibold">notice</Link> or read how we <Link href="/methodology" className="font-semibold">collect and classify</Link>.
        </p>
      </section>
    </>
  );
}
