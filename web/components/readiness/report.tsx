'use client';

import { CircleAlert, CircleCheck, CircleX } from 'lucide-react';
import { cpvDictionaryTitle } from '@/lib/cpv';
import { now } from '@/lib/deadline';
import { formatStamp } from '@/lib/account-format';
import { CERTIFICATES, DE_QUESTIONS, DUAL_USE_QUESTION, ES_QUESTIONS, PROCESSES, REGISTRATIONS, answerLabel, holds, type Profile, type Tri } from '@/lib/profile';
import { VERDICT_WORD, isoDay, publicPassage, publicRef, verdictMeaning } from '@/lib/readiness';
import type { Assessment } from '@/lib/readiness-types';
import { RAG_WORD, supplierRoadmap, type Rag, type RoadmapItem } from '@/lib/supplier-roadmap';
import { countryName } from '@/lib/taxonomy';
import { safeHttpUrl } from '@/lib/safe-url';
import { cleanQuote } from '@/lib/quote';
import { cn } from '@/lib/utils';
import { Icon } from '@/components/dg/icon';
import { Button } from '@/components/dg/button';
import { PrintButton } from '@/components/dg/print-button';
import { ErrorState, Skeleton } from '@/components/dg/feedback';
import { ConsultantNote, VerdictBadge } from './rules';
import { NoProfile } from './results';
import { ES_REGIONS } from './supplier';
import { EXPORT_OPTIONS, SIZE_OPTIONS } from './wizard';
import { useAssessment, useCpvVocabulary, useProfile } from './use-readiness';
import { DemandMap } from './demand';

export const DISCLAIMER = 'Indicative, sources linked, not legal advice.';

/**
 * Print: A4, a page per section, no site chrome (the layout hides the header and the footer), and every outside link followed by its
 * address, since paper has no links. Only on this page: the rules are inside its own markup.
 */
const PRINT_CSS = `
@media print {
  @page { size: A4; margin: 16mm 14mm; }
  .report-section + .report-section { break-before: page; }
  .report-item, .report-row { break-inside: avoid; }
  .report a[href^="http"]::after { content: " (" attr(href) ")"; font-weight: 400; overflow-wrap: anywhere; }
  .report { font-size: 10.5pt; }
}`;

const RAG_ICON = { green: CircleCheck, amber: CircleAlert, red: CircleX } as const;
const RAG_CLASS: Record<Rag, string> = {
  green: 'border-open-fg bg-open-bg text-open-fg', amber: 'border-soon-fg bg-soon-bg text-soon-fg', red: 'border-alert bg-surface text-alert',
};

/** A word and an icon, never a colour alone; bordered so that it still reads on paper without backgrounds. */
export function RagBadge({ rag }: { rag: Rag }) {
  return (
    <span className={cn('inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-pill border-strong px-2.5 py-1 text-label font-bold', RAG_CLASS[rag])}>
      <Icon icon={RAG_ICON[rag]} size="inline" />{RAG_WORD[rag]}
    </span>
  );
}

function Section({ title, id, children }: { title: string; id: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} data-report-section={id} className="report-section flex flex-col gap-4 rounded-lg bg-surface p-5 sm:p-7 print:rounded-none print:bg-transparent print:p-0">
      <h2 id={id} className="m-0 text-h2 print:text-[18pt]">{title}</h2>
      {children}
    </section>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="report-row grid gap-1 border-b border-line py-2.5 last:border-b-0 sm:grid-cols-[220px_minmax(0,1fr)] sm:gap-4">
      <dt className="text-small font-semibold text-ink-muted">{label}</dt>
      <dd className="m-0 min-w-0 break-words text-body">{children}</dd>
    </div>
  );
}

const TRI: Record<Tri, string> = { yes: 'Yes', no: 'No', unsure: 'Not sure', '': 'Not answered' };

/** The company as entered on the supplier page and in the readiness check: nothing added, nothing inferred. */
function ProfileRows({ p }: { p: Profile }) {
  const vocab = useCpvVocabulary();
  const s = p.supplier;
  const region = ES_REGIONS.find((r) => r.value === s.region)?.label ?? s.region;
  const held = [...CERTIFICATES, ...REGISTRATIONS].filter((h) => (!h.esOnly || p.country === 'ES') && holds(p, h));
  const answered = [...(p.country === 'ES' ? ES_QUESTIONS : []), ...(p.country === 'DE' ? DE_QUESTIONS : []), DUAL_USE_QUESTION].filter((q) => s.answers[q.field]);
  return (
    <dl className="m-0 flex flex-col">
      {p.name && <Row label="Company">{p.name}</Row>}
      <Row label="Established in">{countryName(p.country)}{region ? `, ${region}` : ''}</Row>
      <Row label="Size">{SIZE_OPTIONS.find((o) => o.value === p.sizeClass)?.label ?? 'Not answered'}</Row>
      <Row label="NACE code">{s.nace ? <span className="font-mono">{s.nace}</span> : 'Not answered'}</Row>
      <Row label="Foreign investor owns or controls part">
        {TRI[s.foreignOwner]}{s.foreignOwner === 'yes' && s.foreignCountry ? ` (${countryName(s.foreignCountry)})` : ''}
      </Row>
      <Row label="What you make (CPV)">
        {s.cpv.length === 0 ? 'None chosen' : (
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {s.cpv.map((c) => <li key={c}><span className="font-mono">{c}</span> {vocab?.get(c) ?? cpvDictionaryTitle(c) ?? ''}</li>)}
          </ul>
        )}
      </Row>
      <Row label="Processes">{s.processes.length === 0 ? 'None chosen' : s.processes.map((v) => PROCESSES.find((x) => x.value === v)?.label ?? v).join(', ')}</Row>
      <Row label="Certificates and registrations held">
        {held.length === 0 ? 'None' : held.map((h) => `${h.label}${s.expiry[h.key] ? ` (expires ${s.expiry[h.key]})` : ''}`).join('; ')}
      </Row>
      <Row label="US-origin components">{TRI[s.usComponents]}</Row>
      <Row label="Access to classified information">{TRI[p.classified]}</Row>
      <Row label="Exports">{EXPORT_OPTIONS.find((o) => o.value === p.exportIntent)?.label ?? 'Not answered'}</Row>
      {answered.map((q) => <Row key={q.field} label={q.label}>{answerLabel(q, s.answers[q.field])}</Row>)}
    </dl>
  );
}

function Results({ data }: { data: Assessment }) {
  return (
    <ul className="m-0 flex list-none flex-col p-0">
      {data.assessments.map((a) => {
        const titles = (codes: string[]) => a.rules.filter((r) => codes.includes(r.rule)).map((r) => r.title);
        const lists: [string, string[]][] = [['Not met', titles(a.blocking)], ['To obtain first', titles(a.toObtain)], ['A condition applies', titles(a.conditions)]];
        return (
          <li key={a.programme} className="report-row flex flex-col gap-2 border-b border-line py-4 last:border-b-0" data-report-programme={a.programme}>
            <div className="flex flex-wrap items-center gap-3">
              <h3 className="m-0 min-w-0 flex-1 text-h4">{a.name}</h3>
              <VerdictBadge verdict={a.verdict} />
            </div>
            <p className="m-0 max-w-prose text-small">{verdictMeaning(a)}</p>
            {lists.filter(([, xs]) => xs.length > 0).map(([label, xs]) => <p key={label} className="m-0 text-small"><strong>{label}:</strong> {xs.join('; ')}.</p>)}
            {a.missing.length > 0 && <p className="m-0 text-small text-ink-muted">{a.missing.length === 1 ? '1 answer is missing.' : `${a.missing.length} answers are missing.`}</p>}
          </li>
        );
      })}
    </ul>
  );
}

function Item({ i, n }: { i: RoadmapItem; n: number }) {
  const url = i.source ? safeHttpUrl(i.source.url) : null;
  const quote = i.source?.text ? cleanQuote(publicPassage(i.source.text.split('\n\n')[0])) : null;
  return (
    <li className="report-item flex flex-col gap-2 border-t border-line py-4 first:border-t-0" data-item={i.key} data-rag={i.rag}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-mono-strong text-ink-muted" aria-hidden="true">{n}.</span>
        <h3 className="m-0 min-w-0 flex-1 text-h4">{i.name}</h3>
        <RagBadge rag={i.rag} />
      </div>
      <p className="m-0 text-body font-semibold">{i.status}</p>
      {i.reason && <p className="m-0 max-w-prose text-body">{i.reason}</p>}
      {i.after.length > 0 && <p className="m-0 text-small">Comes after: {i.after.join('; ')}.</p>}
      {i.neededFor.length > 0 && <p className="m-0 text-small text-ink-muted">Named by: {i.neededFor.join('; ')}.</p>}
      {i.cost !== null && (
        <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-small">
          <dt className="text-ink-muted">Cost</dt><dd className="m-0">{i.cost}</dd>
          <dt className="text-ink-muted">Time</dt><dd className="m-0">{i.time}</dd>
        </dl>
      )}
      {i.issuers.length > 0 && <p className="m-0 text-small">Issued by: {i.issuers.join('; ')}.</p>}
      {i.note && <p className="m-0 max-w-prose text-small" data-item-note>{i.note}</p>}
      {i.consultant.map((c) => <ConsultantNote key={c} text={c} />)}
      {i.asks.map((q) => <p key={q} className="m-0 text-small">To answer: {q}</p>)}
      {i.source && i.rag !== 'green' && (
        <div className="flex flex-col gap-1 text-small text-ink-muted">
          <p className="m-0">
            Source: {publicRef(i.source.ref) ?? 'see the link'}
            {url && <> · <a href={url} target="_blank" rel="noopener noreferrer" className="font-semibold">Open the source</a></>}
            {' '}· Last reviewed {isoDay(i.source.lastReviewed)}
          </p>
          {quote && <blockquote className="m-0 break-words border-l-2 border-line pl-3 text-ink">{quote}</blockquote>}
        </div>
      )}
    </li>
  );
}

/**
 * The printable supplier report (WP-67), built in the browser from the stored profile and the one assess call the results page makes too.
 * `names`: requirement names from the public catalogue. The section "Who buys what you make" (WP-66) is shown when the supplier page holds CPV codes.
 */
export function SupplierReport({ names }: { names: Record<string, string> }) {
  const { profile, ready } = useProfile();
  const result = useAssessment(profile);
  const title = <h1 className="m-0 text-h1-sm md:text-h1 print:text-[22pt] print:leading-tight">Supplier readiness report{profile?.name ? `: ${profile.name}` : ''}</h1>;
  if (!ready || profile === null) return <div className="flex flex-col gap-6">{title}<Skeleton className="h-56" /></div>;
  if (!profile.country) return <div className="flex flex-col gap-6">{title}<NoProfile /></div>;
  const plan = result.state === 'done' ? supplierRoadmap(result.data, profile, names) : null;

  return (
    <div className="report flex flex-col gap-6 print:gap-0">
      <style>{PRINT_CSS}</style>
      <header className="flex flex-col gap-3 print:mb-4">
        <p className="m-0 font-mono text-mono text-ink-muted">DefenceGate supplier readiness report · generated {formatStamp(now().toISOString())}</p>
        {title}
        <p className="m-0 max-w-prose text-body font-semibold" data-disclaimer>{DISCLAIMER}</p>
        <div className="flex flex-col gap-2 print:hidden">
          <div className="flex flex-wrap items-center gap-3">
            <PrintButton>Print or save as PDF</PrintButton>
            <Button href="/readiness/supplier" variant="secondary">Change my supplier profile</Button>
            <Button href="/readiness/results" variant="secondary">My results</Button>
          </div>
          <p className="m-0 max-w-prose text-small text-ink-muted">
            To keep a PDF, choose “Save as PDF” as the printer in your browser’s print dialog; turning off its “Headers and footers” option leaves out the
            address and date the browser adds. The report is made in this browser; no file is made on our server.
          </p>
        </div>
      </header>

      <Section title="Company profile" id="r-profile">
        <p className="m-0 text-small text-ink-muted">As entered in this browser. Nothing is added or inferred.</p>
        <ProfileRows p={profile} />
      </Section>

      {(result.state === 'loading' || result.state === 'idle') && <div role="status" aria-label="Computing your report"><Skeleton className="h-56" /></div>}
      {result.state === 'error' && <ErrorState title="The report could not be computed" onRetry={result.retry}>{result.message}</ErrorState>}
      {result.state === 'done' && plan && (
        <>
          <Section title="Readiness results" id="r-results">
            <p className="m-0 max-w-prose text-small text-ink-muted">The verdict of each programme and route on your answers. Every rule, its reason and its source are on your results page.</p>
            <Results data={result.data} />
          </Section>

          <Section title="Supplier roadmap" id="r-roadmap">
            <p className="m-0 max-w-prose text-body" data-report-summary>{plan.summary}</p>
            <p className="m-0 max-w-prose text-small text-ink-muted">
              In place first, then what is needed now, then what depends on a contract, a condition or an answer; a step that must come first is
              always listed first. A cost or a time is given only where a primary source states it; the vendor ranges and the figures of our
              research notes on your roadmap page are left out here.
            </p>
            <ol className="m-0 flex list-none flex-col p-0">
              {plan.items.map((i, k) => <Item key={i.key} i={i} n={k + 1} />)}
            </ol>
          </Section>

          {profile.supplier.cpv.length > 0 && <Section title="Who buys what you make" id="r-demand"><DemandMap profile={profile} /></Section>}

          <Section title="About this report" id="r-about">
            <p className="m-0 max-w-prose text-body font-semibold">{DISCLAIMER}</p>
            <p className="m-0 max-w-prose text-body">
              It applies the rules of the sources linked above to the answers given in this browser. It is not legal advice, and it does not say that
              you will be awarded a contract. Where it says a specialist is needed, it gives no answer of its own.
            </p>
            <p className="m-0 max-w-prose text-small text-ink-muted">
              {result.data.notice} Rules last reviewed on {isoDay(result.data.rulesReviewed)}. Generated on {formatStamp(now().toISOString())}.
              {profile.supplier.cpv.length > 0
                ? 'Two requests left this browser to make it: the one that computes the verdict, with the answers the rules read, and the one for the demand map, with your CPV codes and nothing else; the server does not store or log either.'
                : 'The only thing that left this browser to make it is the request that computes the verdict, with the answers the rules read; the server does not store or log it.'}
            </p>
          </Section>
        </>
      )}
    </div>
  );
}
