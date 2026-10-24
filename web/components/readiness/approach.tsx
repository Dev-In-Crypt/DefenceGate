'use client';

import Link from 'next/link';
import { allWinnersLabel, approachGroups, approachOthersLine, openHref, supplierHref, winnersHref, type ApproachWinner, type Demand, type DemandRequest } from '@/lib/demand';
import { codeKind, type CodeKind } from '@/lib/cpv';
import { VALUE_RULES } from '@/lib/value-totals';
import { formatDateUtc } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { countryInText, countryName } from '@/lib/taxonomy';
import { Button } from '@/components/dg/button';
import { Tag } from '@/components/dg/tag';
import { ValueTotalsBlock } from '@/components/dg/value-totals';
import { ErrorState, Skeleton } from '@/components/dg/feedback';
import type { DemandState } from './use-readiness';
import { AboutData } from '@/components/dg/about-data';

type Result = DemandState & { retry: () => void };

export const INDRA_SOURCE = 'https://www.eldiario.es/motor/sector_y_mercado/fabricar-coches-componentes-vehiculos-militares-indra-busca-proveedores-automocion_1_13308288.html';

/**
 * WP-97: the one sentence before the list, chosen by the kind of codes (automotive, machining, ammunition, services, other goods). The Spanish
 * automotive evidence (Indra's 2026 supplier selection) is shown only to a Spanish company with automotive codes.
 */
export const INTRO: Record<CodeKind, string> = {
  automotive: 'Automotive suppliers usually enter defence as subcontractors: they sell to the prime contractors and their large suppliers, not to a ministry.',
  machining: 'Below are the companies that won defence-scope contracts for machined and aerospace parts under your codes, the prime contractors and large defence groups marked: those may buy parts as a subcontract.',
  ammunition: 'Below are the companies that won defence-scope contracts for ammunition and explosives under your codes, the large defence groups marked: those may buy components as a subcontract.',
  services: 'Services such as transport, fuel, facilities, catering, repair and training are bought by the defence bodies directly; below are the companies that won those contracts under your codes.',
  goods: 'Below are the companies that won defence-scope contracts under your codes: the defence buyers’ direct suppliers, and the prime contractors and large defence groups that may buy from you as a subcontractor.',
  none: 'Below are the companies that won defence-scope contracts under your codes, your own country first.',
};

/** WP-97: whether the Spanish automotive material (the Indra news, the automotive landing) is for this company. */
export const spanishAutomotive = (country: string, cpv: readonly string[]) => country === 'ES' && codeKind(cpv) === 'automotive';

/** Why this list comes first: the honest explainer of WP-80, in the words of the company's codes and country (WP-97). */
export function ApproachExplainer({ country = '', cpv = [] }: { country?: string; cpv?: readonly string[] }) {
  const kind = codeKind(cpv);
  return (
    <div className="flex max-w-prose flex-col gap-2 text-body" data-approach-explainer={kind}>
      <p className="m-0">{INTRO[kind]}</p>
      {/* WP-88: one sentence; the evidence and what the list cannot show are collapsed. */}
      <AboutData summary="Why this list comes first">
      {spanishAutomotive(country, cpv) && (
        <p className="m-0" data-approach-indra>
          In Spain, Indra opened a supplier selection for automotive firms in 2026 for its military vehicle programmes (
          <a href={INDRA_SOURCE} target="_blank" rel="noopener noreferrer">elDiario.es, 16 June 2026</a>).
        </p>
      )}
      <p className="m-0">
        Public notices miss most of that work: what a prime buys from its own suppliers is not published. The list below shows who won the published
        defence-scope contracts under your CPV codes; a company marked as a prime contractor or large defence group is one to offer your work to as a
        subcontractor; the others supply the buyers directly. A winner whose name says it deals in parts, tyres or hardware is listed apart, as a
        competitor or distributor rather than a customer.
      </p>
      </AboutData>
    </div>
  );
}

/**
 * One named winner. `request` (WP-89): the profile's codes and countries, carried by the link to its supplier page; `rules={false}`: the
 * sums' scope and rules are stated once under the list, not under each company (the printed report repeated them 38 times).
 */
export function Winner({ w, scope, request = null, rules = true, full = false }: { w: ApproachWinner; scope: string; request?: DemandRequest | null; rules?: boolean; full?: boolean }) {
  const src = w.prime ? safeHttpUrl(w.prime.sourceUrl) : null;
  return (
    <li className="report-item flex flex-col gap-1.5 border-t border-line py-3 first:border-t-0" data-approach-winner={w.prime ? 'prime' : w.distributor ? 'dealer' : 'other'}
      {...(full ? { 'data-print-full': '' } : {})}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-body font-semibold">{w.slug ? <Link href={supplierHref(w.slug, request)}>{w.name}</Link> : w.name}</span>
        {w.country && <span className="text-small text-ink-muted">({countryName(w.country)})</span>}
        {w.prime && <Tag wrap>{w.prime.jointVenture ? `Joint venture with ${w.prime.group}` : `Prime or large defence group: ${w.prime.group}`}</Tag>}
        {w.distributor && <Tag>Distributor or dealer, by its name</Tag>}
        {w.edfProjects > 0 && <Tag>{`EDF projects: ${w.edfProjects}`}</Tag>}
        {w.defenceBuyer && <Tag>Also a defence buyer</Tag>}
      </div>
      <p className="m-0 text-small" data-approach-facts>
        {w.contracts} {w.contracts === 1 ? 'contract' : 'contracts'} won in {w.countries.map(countryName).join(', ')}
        {w.lastAward ? `; latest notice published ${formatDateUtc(w.lastAward)}` : ''}.
      </p>
      {w.buyers.length > 0 && (
        <p className="m-0 text-small text-ink-muted" data-short-hidden>
          Wins most from:{' '}
          {w.buyers.map((b, i) => (
            <span key={b.slug}>{i > 0 && '; '}<Link href={`/buyers/${b.slug}`}>{b.name}</Link> ({b.contracts})</span>
          ))}
        </p>
      )}
      {w.values && <ValueTotalsBlock values={w.values} noun="contract" scope={scope} rules={rules} />}
      {w.prime && <p className="m-0 text-small text-ink-muted" data-short-hidden>Listed by name from: {src ? <a href={src} target="_blank" rel="noopener noreferrer">{w.prime.source}</a> : w.prime.source}.</p>}
    </li>
  );
}

/**
 * WP-105 (p01: Indra, Santa Bárbara Sistemas and Iveco Defence were nowhere in an automotive maker's report): the primes and large defence
 * groups of our list that won none of the procurements under the codes, but other defence contracts from the same buyers.
 */
export function PrimesAtBuyers({ a }: { a: Demand['approach'] }) {
  const xs = a.primesAtBuyers ?? [];
  if (xs.length === 0) return null;
  return (
    <div className="flex flex-col gap-1 pt-2" data-approach-primes-at-buyers>
      <h4 className="m-0 text-body font-bold">Primes that win other contracts from the same buyers</h4>
      <p className="m-0 max-w-prose text-small text-ink-muted">
        On our list of prime contractors and large defence groups, these won no published contract under your codes, but other defence-scope
        contracts from the buyers that buy what you make (any code, the same three years): the programmes they build for those buyers may need your parts.
      </p>
      <ul className="m-0 flex list-none flex-col p-0">
        {xs.map((p) => {
          const src = safeHttpUrl(p.prime.sourceUrl);
          return (
            // one wrapped line per prime (it was three stacked lines): the full report's print stays within its page budget
            <li key={p.slug} className="report-item flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-t border-line py-1.5 first:border-t-0" data-prime-at-buyers={p.prime.group}>
              <span className="text-body">
                <Link href={`/suppliers/${p.slug}`} className="font-semibold">{p.name}</Link>
                {p.country && <span className="text-small text-ink-muted"> ({countryName(p.country)})</span>}
                {' '}<Tag wrap>{`Prime or large defence group: ${p.prime.group}`}</Tag>
              </span>
              <span className="text-small">{p.contracts} {p.contracts === 1 ? 'contract' : 'contracts'} from these buyers under other codes.</span>
              <span className="text-small text-ink-muted" data-short-hidden>Listed by name from: {src ? <a href={src} target="_blank" rel="noopener noreferrer">{p.prime.source}</a> : p.prime.source}.</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** WP-81: what the sums under each winner cover, the list's own period, countries and sources. */
export function winnersScope(d: Pick<Demand, 'since' | 'until' | 'countries' | 'sources'>): string {
  return `The contracts of this list: ${formatDateUtc(d.since)} to ${formatDateUtc(d.until)}, in ${d.countries.map(countryName).join(', ')}, from ${d.sources.some((s) => s.code.startsWith('es_placsp')) ? 'TED and PLACSP' : 'TED'}.`;
}

/** WP-89: "Direct suppliers in Spain", the heading of the winners of the company's own country. */
const homeTitle = (country: string) => `Direct suppliers in ${countryInText(country)}`;

/** The full "who to approach" section of the report. `country`: the company's; its own winners come first (WP-89). */
export function ApproachMap({ result, hasCodes, country, request }: { result: Result; hasCodes: boolean; country: string; request: DemandRequest | null }) {
  const cpv = request?.cpv ?? [];
  if (!hasCodes) {
    return (
      <div className="flex flex-col gap-3">
        <ApproachExplainer country={country} />
        <p className="m-0 text-body">Choose the CPV codes of what you make on your supplier profile, and this section lists the companies that win those contracts.</p>
        <div><Button href="/readiness/supplier" variant="secondary">Add CPV codes to my supplier profile</Button></div>
      </div>
    );
  }
  if (result.state === 'idle' || result.state === 'loading') return <div role="status" aria-label="Finding who wins these contracts"><Skeleton className="h-40" /></div>;
  if (result.state === 'error') return <ErrorState title="The list could not be computed" onRetry={result.retry}>{result.message}</ErrorState>;
  const d = result.data;
  const a = d.approach;
  const { home, primes, others: abroad, dealers } = approachGroups(a, country);
  const others = approachOthersLine(a, d.kMin);
  const scope = winnersScope(d);
  // WP-97: the short print keeps the first ten of each list (`data-print-full` items are left out of it)
  const list = (ws: ApproachWinner[], key: string, keep = SHORT_PRINT) => (
    <ul className="m-0 flex list-none flex-col p-0">{ws.map((w, i) => (
      <Winner key={`${key}-${i}-${w.name}`} w={w} scope={scope} request={request} rules={false} full={i >= keep} />
    ))}</ul>
  );
  return (
    <div className="flex flex-col gap-4" data-approach>
      <ApproachExplainer country={country} cpv={cpv} />
      <p className="m-0 max-w-prose text-body" data-approach-summary>
        From {formatDateUtc(d.since)} to {formatDateUtc(d.until)}, in {d.countries.map(countryName).join(', ')}: {d.total.winners}{' '}
        {d.total.winners === 1 ? 'company' : 'companies'} won defence-scope procurements under your codes. {a.winners.length === 0
          ? (d.kMin > 1 ? `None won ${d.kMin} or more, so none is named.` : 'None is named.')
          : d.kMin > 1
            ? `${a.winners.length} won ${d.kMin} or more and ${a.winners.length === 1 ? 'is' : 'are'} named below, most contracts first.`
            : `${a.winners.length} ${a.winners.length === 1 ? 'is' : 'are'} named below, most contracts first. A winner who is a natural person is never named.`}
      </p>
      {home.length > 0 && (
        <div className="flex flex-col gap-1" data-approach-home>
          <h3 className="m-0 text-h4">{homeTitle(country)}</h3>
          <p className="m-0 max-w-prose text-small text-ink-muted">Companies of your country that sell these products to the defence buyers directly: competitors, partners or customers for your parts.</p>
          {list(home, 'h')}
        </div>
      )}
      <div className="flex flex-col gap-1" data-approach-primes>
        <h3 className="m-0 text-h4">Prime contractors and large defence groups among them</h3>
        {primes.length === 0 ? (
          <p className="m-0 max-w-prose text-body">
            None of the named winners is on our list of prime contractors and large defence groups (the European companies of the SIPRI Top 100 of
            2024, and the Spanish and other EU vehicle and defence makers we list, each with its source). Primes may still buy what you make from their own suppliers; that is not published.
          </p>
        ) : list(primes, 'p', SHORT_PRIMES)}
        <PrimesAtBuyers a={a} />
      </div>
      {abroad.length > 0 && (
        <div className="flex flex-col gap-1" data-approach-abroad data-print-full>
          <h3 className="m-0 text-h4">{home.length > 0 || primes.length > 0 ? 'Direct suppliers in other countries' : 'The named winners'}</h3>
          {list(abroad, 'o')}
        </div>
      )}
      {dealers.length > 0 && (
        <div className="flex flex-col gap-1" data-approach-dealers data-print-full>
          <h3 className="m-0 text-h4">Competitors and distributors</h3>
          <p className="m-0 max-w-prose text-small text-ink-muted">Winners whose names say they deal in parts, tyres or hardware: they resell what others make, so they compete with a maker for these contracts or distribute its products; they are not customers for your parts.</p>
          {list(dealers, 'd')}
        </div>
      )}
      {others && <p className="m-0 max-w-prose text-small text-ink-muted" data-approach-others>{others}</p>}
      {d.total.winners > a.winners.length && (
        <p className="m-0" data-approach-all><a href={winnersHref()} className="font-semibold">{allWinnersLabel(d.total.winners)}</a></p>
      )}
      <AboutData summary="How we count">
      <p className="m-0">
        A contract here is a procurement with a published winner, counted once however many notices publish it. Under each company, Contract values sums the values of its contracts per currency. The
        latest notice is the newest publication among them: for Spain’s national portal (PLACSP) the date the procurement was published, since its
        award date is not stored. Marked by name: a group member that carries the group’s name; a subsidiary under another name is not marked.
      </p>
      {/* WP-89: the sums' scope and rules once, for every company above (they were printed under each of them) */}
      <p className="m-0" data-value-rules>Contract values: {scope} {VALUE_RULES}</p>
      <p className="m-0">{d.winnersFrom} {d.coverage}</p>
      </AboutData>
    </div>
  );
}

/** The short version, first on the results page: the company's own country's direct suppliers and the primes, and the way to the report. */
export function ApproachSummary({ result, country, cpv }: { result: Result; country: string; cpv: string[] }) {
  if (result.state === 'idle') return null;
  return (
    <section aria-labelledby="approach" className="flex flex-col gap-3" data-approach-summary-section>
      <h2 id="approach" className="m-0 text-h2">Who to approach</h2>
      <ApproachExplainer country={country} cpv={cpv} />
      {result.state === 'loading' && <div role="status" aria-label="Finding who wins these contracts"><Skeleton className="h-40" /></div>}
      {result.state === 'error' && <ErrorState title="The list could not be computed" onRetry={result.retry}>{result.message}</ErrorState>}
      {result.state === 'done' && <ShortList d={result.data} country={country} cpv={cpv} />}
    </section>
  );
}

/** How many of each group the results page shows (WP-89: two columns of five; before, the first eight, primes first). */
export const SHORT_LIST = 5;
/** WP-97: how many of each list the short print of the report keeps. */
export const SHORT_PRINT = 10;
/** WP-97: and how many primes (the top ten winners are the own country's direct suppliers and these). */
export const SHORT_PRIMES = 5;

/**
 * WP-97 (persona round of 23 October 2026): "Open now in <country> under your codes (N)", first on the results page and in the report: the
 * open tenders of the company's own country under its codes, counted as /tenders counts them, with the link to that list. Another country of
 * the answer follows when its count is known. A country outside the five of the map gets the link without a count.
 */
export function OpenNowBlock({ result, country }: { result: Result; country: string }) {
  if (result.state !== 'done' || !country || country === 'XX') return null;
  const d = result.data;
  // a count the API could not finish in time comes as "at least 0": the link alone then
  const found = d.byCountry.find((c) => c.country === country)?.openNow;
  const open = found && !(found.atLeast && found.count === 0) ? found : null;
  const count = (n: { count: number; atLeast: boolean }) => `${n.atLeast ? 'at least ' : ''}${n.count}`;
  const others = d.byCountry.filter((c) => c.country !== country && c.openNow && c.openNow.count > 0);
  return (
    <section aria-labelledby="open-now" className="flex flex-col gap-2 rounded-lg bg-surface p-5" data-open-now={country}>
      <h2 id="open-now" className="m-0 text-h3">
        {open ? `Open now in ${countryInText(country)} under your codes (${count(open)})` : `Open now in ${countryInText(country)} under your codes`}
      </h2>
      <p className="m-0 max-w-prose text-body">
        <a href={openHref(d, country)} className="font-semibold" data-open-now-link>
          {open ? (open.count === 0 ? 'None is open today: see the tender list for these codes' : `See the ${count(open)} open ${open.count === 1 ? 'tender' : 'tenders'}`) : 'See the open tenders for these codes'}
        </a>
        {!open && <span className="text-ink-muted"> (the list itself counts them)</span>}
      </p>
      {others.length > 0 && (
        <p className="m-0 max-w-prose text-small text-ink-muted" data-open-now-others>
          Elsewhere: {others.map((c, i) => <span key={c.country}>{i > 0 && '; '}<a href={openHref(d, c.country)}>{countryName(c.country)} ({count(c.openNow!)})</a></span>)}.
        </p>
      )}
    </section>
  );
}

function ShortList({ d, country, cpv }: { d: Demand; country: string; cpv: string[] }) {
  const { home, primes, others } = approachGroups(d.approach, country);
  // without winners of its own country, the direct suppliers of every country (dealers are never in this short list: WP-97)
  const direct = (home.length > 0 ? home : others).slice(0, SHORT_LIST);
  const big = primes.slice(0, SHORT_LIST);
  const request = cpv.length ? { cpv, countries: d.countries } : null;
  const column = (title: string, ws: ApproachWinner[], key: string, attr: string) => (
    <div className="flex min-w-0 flex-col gap-1" {...{ [attr]: '' }}>
      <h3 className="m-0 text-h4">{title}</h3>
      {ws.length === 0
        ? <p className="m-0 text-small text-ink-muted">None among the winners under your codes.</p>
        : <ul className="m-0 flex list-none flex-col p-0">{ws.map((w, i) => <Winner key={`${key}-${i}-${w.name}`} w={w} scope={winnersScope(d)} request={request} />)}</ul>}
    </div>
  );
  return (
    <>
      {direct.length + big.length === 0 ? (
        <p className="m-0 max-w-prose text-body">{d.kMin > 1
          ? `No company won ${d.kMin} or more defence-scope procurements under your codes in the last three years, so none is named.`
          : 'No company won a defence-scope procurement under your codes in the last three years.'}</p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {column(home.length > 0 ? homeTitle(country) : 'Direct suppliers', direct, 'h', 'data-approach-home')}
          {column('Large primes', big, 'p', 'data-approach-primes')}
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        <Button href="/readiness/supplier/report#r-approach" variant="secondary">Who to approach in your supplier report</Button>
        {d.total.winners > direct.length + big.length && <Button href={winnersHref()} variant="secondary">{allWinnersLabel(d.total.winners)}</Button>}
      </div>
    </>
  );
}
