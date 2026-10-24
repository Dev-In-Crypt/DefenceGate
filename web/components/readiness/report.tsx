'use client';

import { useEffect, useState } from 'react';
import { CircleAlert, CircleCheck, CircleX, Printer } from 'lucide-react';
import { cpvDictionaryTitle } from '@/lib/cpv';
import { now } from '@/lib/deadline';
import { formatStamp } from '@/lib/account-format';
import { HEADCOUNT_BANDS, SUPPLY_ROUTES, CERTIFICATES, DE_QUESTIONS, DUAL_USE_QUESTION, ES_QUESTIONS, PROCESSES, REGISTRATIONS, SERVICE_PROCESSES, answerLabel, holds, notSure, providesServices, roadmapProgrammes, type Profile, type Tri } from '@/lib/profile';
import { countryRoute } from '@/lib/country-routes';
import { VERDICT_WORD, isoDay, publicPassage, publicRef, verdictMeaning } from '@/lib/readiness';
import type { Assessment } from '@/lib/readiness-types';
import { RAG_WORD, supplierRoadmap, type Rag, type RoadmapItem } from '@/lib/supplier-roadmap';
import { countryName } from '@/lib/taxonomy';
import { safeHttpUrl } from '@/lib/safe-url';
import { cleanQuote } from '@/lib/quote';
import { cn } from '@/lib/utils';
import { Icon } from '@/components/dg/icon';
import { Button } from '@/components/dg/button';
import { AboutData } from '@/components/dg/about-data';
import { ErrorState, Skeleton } from '@/components/dg/feedback';
import { ConsultantNote, VerdictBadge } from './rules';
import { NoProfile } from './results';
import { ES_REGIONS } from './supplier';
import { EXPORT_OPTIONS, SIZE_OPTIONS } from './wizard';
import { useAssessment, useCpvVocabulary, useDemand, useProfile } from './use-readiness';
import { DemandMap } from './demand';
import { ApproachMap, OpenNowBlock } from './approach';
import { demandRequest } from '@/lib/demand';
import { CHECK_THE_CALL, COURSES, guidesFor, isClosed, noRegionalGrant, regionalGrants, type Grant } from '@/lib/es-support';
import { Tag } from '@/components/dg/tag';

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
  /* WP-89: a company's contract values print as their summary line (the total, and how many state none); the details stay on the page */
  .report [data-value-totals] { display: none; }
  /* WP-89: on paper, each winner of the demand map with its newest notice (all of them are named under "Who to approach"), and tighter rows */
  .report [data-demand-winner] [data-demand-notice]:not(:first-child) { display: none; }
  .report .report-item { padding-top: 0.35rem; padding-bottom: 0.35rem; }
  /* WP-97: the short version (5 to 10 pages): the first ten of each list, the own country's notices, the step plan; no appendix */
  .report[data-print="short"] [data-print-full], .report[data-print="short"] [data-short-hidden] { display: none !important; }
  /* the explainers ("How we count") and the per-country winners, which "Who to approach" already names, are in the full print only */
  .report[data-print="short"] [data-about], .report[data-print="short"] [data-demand-who-won] { display: none !important; }
  .report[data-print="short"] .report-section + .report-section { break-before: auto; margin-top: 8mm; }
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

function Section({ title, id, children, short = true }: { title: string; id: string; children: React.ReactNode; short?: boolean }) {
  return (
    <section aria-labelledby={id} data-report-section={id} {...(short ? {} : { 'data-print-full': '' })}
      className="report-section flex flex-col gap-4 rounded-lg bg-surface p-5 sm:p-7 print:rounded-none print:bg-transparent print:p-0">
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
      <Row label="Size">{HEADCOUNT_BANDS.find((o) => o.value === p.headcount)?.label ? `${HEADCOUNT_BANDS.find((o) => o.value === p.headcount)!.label} staff${p.inGroup === 'yes' ? `, part of a group${p.groupHeadcount ? ` of ${HEADCOUNT_BANDS.find((o) => o.value === p.groupHeadcount)!.label.toLowerCase()}` : ''}` : ''}` : SIZE_OPTIONS.find((o) => o.value === p.sizeClass)?.label ?? 'Not answered'}</Row>
      <Row label="NACE code">{s.nace ? <span className="font-mono">{s.nace}</span> : 'Not answered'}</Row>
      <Row label="Foreign investor owns or controls part">
        {TRI[s.foreignOwner]}{s.foreignOwner === 'yes' && s.foreignCountry ? ` (${countryName(s.foreignCountry)})` : ''}
      </Row>
      <Row label={providesServices(p) ? 'What you provide (CPV)' : 'What you make (CPV)'}>
        {s.cpv.length === 0 ? 'None chosen' : (
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {s.cpv.map((c) => <li key={c}><span className="font-mono">{c}</span> {vocab?.get(c) ?? cpvDictionaryTitle(c) ?? ''}</li>)}
          </ul>
        )}
      </Row>
      <Row label={providesServices(p) ? 'Services' : 'Processes'}>{s.processes.length === 0 ? 'None chosen' : s.processes.map((v) => [...PROCESSES, ...SERVICE_PROCESSES].find((x) => x.value === v)?.label ?? v).join(', ')}</Row>
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

function Results({ data, profile }: { data: Assessment; profile: Profile }) {
  // WP-89: the supply routes first (the Spanish Ministry of Defence, then NATO and NSPA), then the EU funding programmes
  const rank = (a: Assessment['assessments'][number]) => (a.kind === 'route' ? (SUPPLY_ROUTES as readonly string[]).indexOf(a.programme) + 1 || 50 : 100);
  return (
    <ul className="m-0 flex list-none flex-col p-0">
      {[...data.assessments].sort((x, y) => rank(x) - rank(y)).map((a) => {
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
            {(() => {
              // WP-97: "I am not sure" is an answer, said apart; only what was not answered is missing
              const unsure = a.missing.filter((m) => notSure(profile, m.field)).length;
              const missing = a.missing.length - unsure;
              return (
                <>
                  {missing > 0 && <p className="m-0 text-small text-ink-muted">{missing === 1 ? '1 answer is missing.' : `${missing} answers are missing.`}</p>}
                  {unsure > 0 && <p className="m-0 text-small text-ink-muted">{unsure === 1 ? 'One rule stays open on an answer “I am not sure”.' : `${unsure} rules stay open on answers “I am not sure”.`}</p>}
                </>
              );
            })()}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * WP-80: the free official guide and the Spanish regional grants that have covered this step (lib/es-support.ts). WP-89: with the region
 * chosen, its own programmes only, or one plain sentence when it has none; a closed call is marked so.
 */
const grantKey = (g: Grant) => `${g.programme}|${g.covers}`;

/** WP-97: the first step of the plan that each grant covers: the grant is printed in full there, and named with a pointer on the others. */
function firstGrants(items: RoadmapItem[], region: string | null): Map<string, string> {
  const out = new Map<string, string>();
  if (region === null) return out;
  for (const i of items) {
    if (i.rag === 'green') continue;
    for (const g of regionalGrants(i.requirement ?? i.key, region).grants) if (!out.has(grantKey(g))) out.set(grantKey(g), i.key);
  }
  return out;
}

function Support({ requirement, region, country, itemKey, first, names }: {
  requirement: string; region: string | null; country: string; itemKey: string; first: Map<string, string>; names: Map<string, string>;
}) {
  // the free guides of Murcia's CAETRA programme are about the Spanish route: for a Spanish company only (WP-97)
  const guides = country === 'ES' ? guidesFor(requirement) : [];
  // Spanish regions: for a company established in Spain
  const { grants, none } = region === null ? { grants: [], none: false } : regionalGrants(requirement, region);
  const regionName = ES_REGIONS.find((r) => r.value === region)?.label ?? region ?? '';
  if (guides.length === 0 && grants.length === 0 && !none) return null;
  const link = (url: string, text: string) => {
    const safe = safeHttpUrl(url);
    return safe ? <a href={safe} target="_blank" rel="noopener noreferrer">{text}</a> : text;
  };
  return (
    <div className="flex flex-col gap-1 text-small" data-item-support>
      {guides.map((g) => <p key={g.url} className="m-0" data-item-guide><strong>Free guide:</strong> {link(g.url, g.title)} ({g.by}, {g.date}).</p>)}
      {none && <p className="m-0" data-item-no-grant><strong>Regional grants:</strong> {noRegionalGrant(regionName)}</p>}
      {grants.length > 0 && (
        <div className="flex flex-col gap-0.5" data-item-grants>
          <p className="m-0"><strong>Regional grants that have paid for this step:</strong></p>
          <ul className="m-0 flex list-disc flex-col gap-0.5 pl-5">
            {grants.map((g) => {
              const at = first.get(grantKey(g));
              const again = at !== undefined && at !== itemKey;
              return (
                <li key={`${g.programme}-${g.covers}`} data-grant-region={g.region} data-grant-closed={isClosed(g) || undefined} data-grant-repeat={again || undefined}>
                  {isClosed(g) && <><Tag>Closed</Tag>{' '}</>}
                  {again
                    ? <>{g.regionName}: {g.programme} (described under “{names.get(at) ?? at}” above).</>
                    : <>{g.regionName}{g.region === region ? ' (your region)' : ''}: {link(g.url, g.programme)}, for {g.covers}{g.amounts ? `; ${g.amounts}` : ''} ({g.read}).</>}
                </li>
              );
            })}
          </ul>
          {grants.some((g) => first.get(grantKey(g)) === itemKey) && <p className="m-0 text-ink-muted">{CHECK_THE_CALL}</p>}
        </div>
      )}
    </div>
  );
}

function Item({ i, n, region, country, first, names }: { i: RoadmapItem; n: number; region: string | null; country: string; first: Map<string, string>; names: Map<string, string> }) {
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
      {i.neededFor.length > 0 && <p className="m-0 text-small text-ink-muted" data-short-hidden>Named by: {i.neededFor.join('; ')}.</p>}
      {i.cost !== null && (
        <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-small">
          <dt className="text-ink-muted">Cost</dt><dd className="m-0" data-item-cost>{i.cost}{i.costLabel ? ` (${i.costLabel})` : ''}</dd>
          <dt className="text-ink-muted">Time</dt><dd className="m-0" data-item-time>{i.time}</dd>
        </dl>
      )}
      {i.issuers.length > 0 && <p className="m-0 text-small">Issued by: {i.issuers.join('; ')}.</p>}
      {i.note && <p className="m-0 max-w-prose text-small" data-item-note>{i.note}</p>}
      {i.consultant.map((c) => <ConsultantNote key={c} text={c} />)}
      {i.asks.map((q) => <p key={q} className="m-0 text-small">To answer: {q}</p>)}
      {i.source && i.rag !== 'green' && (
        <div className="flex flex-col gap-1 text-small text-ink-muted" data-short-hidden>
          <p className="m-0">
            Source: {publicRef(i.source.ref) ?? 'see the link'}
            {url && <> · <a href={url} target="_blank" rel="noopener noreferrer" className="font-semibold">Open the source</a></>}
            {' '}· Last reviewed {isoDay(i.source.lastReviewed)}
          </p>
          {quote && <blockquote className="m-0 break-words border-l-2 border-line pl-3 text-ink">{quote}</blockquote>}
        </div>
      )}
      {i.rag !== 'green' && <Support requirement={i.requirement ?? i.key} region={region} country={country} itemKey={i.key} first={first} names={names} />}
    </li>
  );
}

/**
 * WP-97: the national route of the company's own country (lib/country-routes.ts): what our primary sources state, and "Not covered yet"
 * with the body to ask where they state nothing. Spain's route is in the rules, so it has none.
 */
export function CountryRoute({ country }: { country: string }) {
  const lines = countryRoute(country);
  if (lines.length === 0) return null;
  return (
    <div className="flex max-w-prose flex-col gap-2" data-country-route={country}>
      <h3 className="m-0 text-h4">{`Your national route: ${countryName(country)}`}</h3>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {lines.map((l) => {
          const url = l.link ? (l.link.url.startsWith('/') ? l.link.url : safeHttpUrl(l.link.url)) : null;
          return (
            <li key={l.key} className="report-item flex flex-col gap-0.5 text-small" data-route-line={l.key} data-route-open={l.open || undefined}>
              <strong>{l.title}</strong>
              <span>{l.text}</span>
              {l.link && url && (url.startsWith('/')
                ? <a href={url} className="font-semibold">{l.link.label}</a>
                : <a href={url} target="_blank" rel="noopener noreferrer" className="font-semibold">{l.link.label}</a>)}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * The printable supplier report (WP-67), built in the browser from the stored profile and the one assess call the results page makes too.
 * `names`: requirement names from the public catalogue. The section "Who buys what you make" (WP-66) is shown when the supplier page holds CPV codes.
 */
export function SupplierReport({ names }: { names: Record<string, string> }) {
  const { profile, ready } = useProfile();
  // WP-97: the programmes the roadmap asks (the supply routes only, unless the company wants EU funding), so the report has no PIC then
  const result = useAssessment(profile, profile ? roadmapProgrammes(profile) : null);
  // WP-97: the short or the full print; the attribute is set for the print dialog and taken off after it
  const [print, setPrint] = useState<'short' | 'full' | null>(null);
  useEffect(() => {
    if (!print) return;
    const done = () => setPrint(null);
    window.addEventListener('afterprint', done);
    window.print();
    return () => window.removeEventListener('afterprint', done);
  }, [print]);
  const demand = useDemand(profile);          // one request, read by "who to approach" and "who buys what you make"
  const title = <h1 className="m-0 text-h1-sm md:text-h1 print:text-[22pt] print:leading-tight">Supplier readiness report{profile?.name ? `: ${profile.name}` : ''}</h1>;
  if (!ready || profile === null) return <div className="flex flex-col gap-6">{title}<Skeleton className="h-56" /></div>;
  if (!profile.country) return <div className="flex flex-col gap-6">{title}<NoProfile /></div>;
  const plan = result.state === 'done' ? supplierRoadmap(result.data, profile, names) : null;
  const firstGrant = plan ? firstGrants(plan.items, profile.country === 'ES' ? profile.supplier.region : null) : new Map<string, string>();
  const itemNames = new Map((plan?.items ?? []).map((i) => [i.key, i.name]));

  return (
    <div className="report flex flex-col gap-6 print:gap-0" data-print={print ?? undefined}>
      <style>{PRINT_CSS}</style>
      <header className="flex flex-col gap-3 print:mb-4">
        <p className="m-0 font-mono text-mono text-ink-muted">DefenceGate supplier readiness report · generated {formatStamp(now().toISOString())}</p>
        {title}
        <p className="m-0 max-w-prose text-body font-semibold" data-disclaimer>{DISCLAIMER}</p>
        <div className="flex flex-col gap-2 print:hidden">
          <div className="flex flex-wrap items-center gap-3">
            <Button icon={Printer} onClick={() => setPrint('short')} data-print-short>Print the short version (5 to 10 pages)</Button>
            <Button icon={Printer} variant="secondary" onClick={() => setPrint('full')} data-print-all>Print the full report</Button>
            <Button href="/readiness/supplier" variant="secondary">Change my supplier profile</Button>
            <Button href="/readiness/results" variant="secondary">My results</Button>
          </div>
          <AboutData summary="How to keep a PDF">
          <p className="m-0">
            To keep a PDF, choose “Save as PDF” as the printer in your browser’s print dialog; turning off its “Headers and footers” option leaves out the
            address and date the browser adds. The report is made in this browser; no file is made on our server.
          </p>
          </AboutData>
        </div>
      </header>

      {/* WP-97: what is open now in the company's own country under its codes, first */}
      {profile.supplier.cpv.length > 0 && demand.state === 'done' && (
        <section data-report-section="r-open" className="report-section flex flex-col"><OpenNowBlock result={demand} country={profile.country} /></section>
      )}

      <Section title="Who to approach" id="r-approach">
        <ApproachMap result={demand} hasCodes={profile.supplier.cpv.length > 0} country={profile.country} request={demandRequest(profile)} />
      </Section>

      {profile.supplier.cpv.length > 0 && <Section title={providesServices(profile) ? 'Who buys what you provide' : 'Who buys what you make'} id="r-demand"><DemandMap result={demand} country={profile.country} /></Section>}

      {(result.state === 'loading' || result.state === 'idle') && <div role="status" aria-label="Computing your report"><Skeleton className="h-56" /></div>}
      {result.state === 'error' && <ErrorState title="The readiness appendix could not be computed" onRetry={result.retry}>{result.message}</ErrorState>}
      {result.state === 'done' && plan && (
        <>
          <Section title="Appendix A: readiness results" id="r-results" short={false}>
            <p className="m-0 max-w-prose text-small text-ink-muted">The verdict of each programme and route on your answers. Every rule, its reason and its source are on your results page.</p>
            <Results data={result.data} profile={profile} />
          </Section>

          <Section title="Appendix B: supplier roadmap, with the free guides and grants" id="r-roadmap">
            <p className="m-0 max-w-prose text-body" data-report-summary>{plan.summary}</p>
            <p className="m-0 max-w-prose text-small text-ink-muted">
              In place first, then what is needed now, then what depends on a contract, a condition or an answer; a step that must come first is
              always listed first. Cost and time are in the words of the requirement's source, as on your roadmap page; where no source
              states one, the line says so.
            </p>
            <CountryRoute country={profile.country} />
            {profile.country === 'ES' && (
              <div className="flex max-w-prose flex-col gap-1 text-small" data-report-support>
                <p className="m-0">
                  In Spain these steps are covered by free public material: the guides to the RID and to PECAL/AQAP of Murcia’s CAETRA programme,
                  and regional programmes that have paid for the steps themselves (on each step below, with the call or list they come from). A
                  free course:
                </p>
                <ul className="m-0 flex list-disc flex-col gap-0.5 pl-5">
                  {COURSES.map((c) => {
                    const url = safeHttpUrl(c.url);
                    return (
                      <li key={c.url}>
                        {url ? <a href={url} target="_blank" rel="noopener noreferrer">{c.title}</a> : c.title} ({c.by}, {c.date}
                        {profile.supplier.region === c.region ? ', your region' : ''}): {c.covers}.
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            <ol className="m-0 flex list-none flex-col p-0">
              {plan.items.map((i, k) => <Item key={i.key} i={i} n={k + 1} region={profile.country === 'ES' ? profile.supplier.region : null}
                country={profile.country} first={firstGrant} names={itemNames} />)}
            </ol>
          </Section>
        </>
      )}

      <Section title="Appendix C: company profile" id="r-profile" short={false}>
        <p className="m-0 text-small text-ink-muted">As entered in this browser. Nothing is added or inferred.</p>
        <ProfileRows p={profile} />
      </Section>

      {result.state === 'done' && (
        <>
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
