import Link from 'next/link';
import { CircleAlert, CircleCheck, CircleHelp } from 'lucide-react';
import { L, valueLine, type BuyerCountry, type ItemStatus, type NoticeLink, type SellReport } from '@/lib/sell-report';
import { CERTIFICATES, REGISTRATIONS } from '@/lib/profile';
import { formatDateUtc, formatNumber } from '@/lib/format';
import { countryName } from '@/lib/taxonomy';
import { safeHttpUrl } from '@/lib/safe-url';
import { cleanQuote } from '@/lib/quote';
import { cn } from '@/lib/utils';
import { Logo } from '@/components/dg/logo';
import { Icon } from '@/components/dg/icon';

/**
 * WP-162: the "Who to sell to" supplier report, one page for the screen and for paper (A4, the browser's print dialog saves it as PDF).
 * Pure: it renders the API's answer (backend/dgate/sell_report.py) and adds nothing; every label is in lib/sell-report.ts `L`. Every
 * number and row links to its page here and to its source notice (the source's own identifier, in mono; the links stay live in the PDF).
 * On paper (3 to 5 A4 pages): a smaller type scale, one quote per requirement, no screen padding.
 */
const PRINT_CSS = `
@media print {
  @page { size: A4; margin: 12mm 12mm; }
  .sr { font-size: 8.5pt; line-height: 1.3; }
  .sr .text-body { font-size: 8.5pt; line-height: 1.3; }
  .sr .text-small, .sr td, .sr th, .sr .text-label { font-size: 7.5pt; line-height: 1.25; }
  .sr .text-mono { font-size: 6.5pt; }
  .sr .text-h4 { font-size: 9pt; }
  .sr h2 { font-size: 12pt !important; break-after: avoid; }
  .sr h1 { font-size: 18pt !important; }
  .sr td, .sr th { padding: 2px 4px !important; }
  .sr .sr-row { padding-top: 2px; padding-bottom: 2px; }
  .sr .sr-item { padding-top: 4px; padding-bottom: 4px; gap: 2px; }
  .sr-section { break-inside: auto; gap: 4px; }
  .sr-row, .sr-item, .sr tr { break-inside: avoid; }
  .sr-section + .sr-section { margin-top: 4mm; }
  .sr [data-sr-quote] + [data-sr-quote] { display: none; }
  .sr [data-scroll] { overflow: visible !important; }
  .sr table { min-width: 0 !important; }
}`;

/** A quote, cut at a word near `max` characters (marked with an ellipsis): the full text is at the link. */
function excerpt(text: string, max = 280): string {
  const t = cleanQuote(text);
  if (t.length <= max) return t;
  const cut = t.slice(0, max);
  return `${cut.slice(0, Math.max(cut.lastIndexOf(' '), max - 40)).replace(/[\s,;:]+$/, '')} […]`;
}

const STATUS_ICON = { have: CircleCheck, missing: CircleAlert, consultant: CircleHelp } as const;
const STATUS_CLASS: Record<ItemStatus, string> = {
  have: 'border-open-fg bg-open-bg text-open-fg', missing: 'border-alert bg-surface text-alert', consultant: 'border-soon-fg bg-soon-bg text-soon-fg',
};

function StatusBadge({ s }: { s: ItemStatus }) {
  return (
    <span className={cn('inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-pill border-strong px-2.5 py-0.5 text-label font-bold', STATUS_CLASS[s])} data-status={s}>
      <Icon icon={STATUS_ICON[s]} size="inline" />{L.statusWord[s]}
    </span>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} data-sr-section={id} className="sr-section flex min-w-0 flex-col gap-3 rounded-lg bg-surface p-5 sm:p-7 print:rounded-none print:bg-transparent print:p-0">
      <h2 id={id} className="m-0 text-h2 print:text-[15pt]">{title}</h2>
      {children}
    </section>
  );
}

/** A source link: the address in mono, opened in a new tab; on paper followed by the address. */
function Src({ url, children }: { url: string | null; children: React.ReactNode }) {
  const safe = url ? safeHttpUrl(url) : null;
  if (!safe) return <span className="font-mono text-mono text-ink-muted">{children}</span>;
  return <a href={safe} target="_blank" rel="noopener noreferrer" data-src className="font-mono text-mono">{children}</a>;
}

function Notice({ n }: { n: NoticeLink | null }) {
  if (!n) return <span className="text-ink-muted">{L.notStated}</span>;
  return (
    <span className="flex flex-col gap-0.5">
      <Link href={n.href} prefetch={false} className="whitespace-nowrap">{n.publishedAt ? formatDateUtc(n.publishedAt) : n.noticeId}</Link>
      <Src url={n.sourceUrl}>{`${n.source.toUpperCase()} ${n.noticeId}`}</Src>
    </span>
  );
}

function Table({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 overflow-x-auto" data-scroll role="region" aria-label={label} tabIndex={0}>
      <table className="w-full min-w-[560px] border-collapse text-left text-small [&_td]:px-2.5 [&_td]:py-2 [&_td]:align-top [&_th]:px-2.5 [&_th]:py-2 [&_th]:font-semibold [&_thead_th]:bg-surface-inset [&_tbody_tr]:border-b [&_tbody_tr]:border-line">
        <caption className="sr-only">{label}</caption>
        {children}
      </table>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="sr-row grid gap-1 border-b border-line py-2 last:border-b-0 sm:grid-cols-[220px_minmax(0,1fr)] sm:gap-4">
      <dt className="text-small font-semibold text-ink-muted">{label}</dt>
      <dd className="m-0 min-w-0 break-words text-body">{children}</dd>
    </div>
  );
}

const HELD_LABELS: Record<string, string> = Object.fromEntries([...CERTIFICATES, ...REGISTRATIONS].map((h) => [h.key, h.label]));
const TRI: Record<string, string> = { yes: 'Yes', no: 'No', unsure: 'Not sure' };
const EXPORTS: Record<string, string> = { none: 'No', within_eu: 'Yes, to other EU countries', outside_eu: 'Yes, outside the EU', unsure: 'Not sure yet' };

function Profile({ r }: { r: SellReport }) {
  const p = r.profile;
  return (
    <dl className="m-0 flex flex-col">
      <Row label={L.company}>{p.name ?? L.notStated}{p.href && <> · <Link href={p.href} prefetch={false}>its page here</Link></>}</Row>
      <Row label={L.country}>{p.country ? countryName(p.country) : L.notStated}</Row>
      <Row label={L.codes}>
        {p.cpv.length === 0 ? L.notStated : (
          <>
            <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
              {p.cpv.map((c) => <li key={c}><span className="font-mono">{c}</span> {p.cpvTitles?.[c] ?? ''}</li>)}
            </ul>
            <span className="text-small text-ink-muted">{p.cpvFrom === 'awards' ? L.codesFromAwards : L.codesFromRequest}</span>
          </>
        )}
      </Row>
      {p.nace && <Row label={L.nace}><span className="font-mono">{p.nace}</span></Row>}
      {p.size && <Row label={L.size}>{p.size === 'sme' ? L.sizeSme : L.sizeLarge}</Row>}
      <Row label={L.held}>{p.held.length ? p.held.map((k) => HELD_LABELS[k] ?? k).join('; ') : L.none}</Row>
      {p.exports && <Row label="Exports">{EXPORTS[p.exports] ?? p.exports}</Row>}
      {p.classified && <Row label="Access to classified information">{TRI[p.classified] ?? p.classified}</Row>}
      {p.usComponents && <Row label="US-origin parts, software or technology">{TRI[p.usComponents] ?? p.usComponents}</Row>}
      {p.mode === 'A' && <Row label={L.awards}>{p.awards === null ? L.notStated : formatNumber(p.awards ?? 0)}</Row>}
      {p.mode === 'A' && (
        <Row label={L.projects}>{p.projects.length ? p.projects.map((x) => `${x.programme}: ${formatNumber(x.projects)}`).join('; ') : 'None in CORDIS or the EDF factsheets'}</Row>
      )}
    </dl>
  );
}

function Unavailable({ r }: { r: SellReport }) {
  const m = r.market;
  return (
    <p className="m-0 text-body" data-sr-empty>
      {m.reason === 'too_broad' ? m.message : 'No CPV codes: this section needs the codes of what the company makes.'}
    </p>
  );
}

function Buyers({ b }: { b: BuyerCountry }) {
  return (
    <div className="flex min-w-0 flex-col gap-2" data-sr-country={b.country}>
      <h3 className="m-0 text-h4">{countryName(b.country)} <span className="text-small font-normal text-ink-muted">· <Link href={b.href} prefetch={false}>{L.countryLine(b.procurements, b.buyers, b.coreBuyers)}</Link></span></h3>
      <Table label={`${L.s2}: ${countryName(b.country)}`}>
        <thead><tr><th scope="col">{L.buyer}</th><th scope="col" className="text-right">{L.procurements}</th><th scope="col">{L.value}</th><th scope="col">{L.newest}</th></tr></thead>
        <tbody>
          {b.rows.map((x) => (
            <tr key={x.href} data-sr-buyer>
              <td><Link href={x.href} prefetch={false} className="break-words">{x.name}</Link></td>
              <td className="text-right font-mono tabular-nums">{formatNumber(x.procurements)}</td>
              <td>{valueLine(x.awardedValue) ?? <span className="text-ink-muted">{L.noValue}</span>}</td>
              <td><Notice n={x.notice} /></td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}

function Winners({ r }: { r: SellReport }) {
  const w = r.market.winners!;
  return (
    <>
      <p className="m-0 max-w-prose text-body">{L.winnersLead}</p>
      <p className="m-0 max-w-prose text-small text-ink-muted" data-sr-mosaic>{L.mosaic(w.mosaicMin)}</p>
      {!w.names && <p className="m-0 text-small font-semibold" data-sr-signin>{L.signInForNames}</p>}
      {w.ownContracts != null && <p className="m-0 text-small" data-sr-own>{L.ownContracts(w.ownContracts)}</p>}
      {w.rows.length > 0 && (
        <Table label={L.s3}>
          <thead><tr><th scope="col">{L.winner}</th><th scope="col">{L.country}</th><th scope="col" className="text-right">{L.contracts}</th><th scope="col">{L.value}</th><th scope="col">{L.newest}</th></tr></thead>
          <tbody>
            {w.rows.map((x) => (
              <tr key={x.href} data-sr-winner>
                <td>
                  <Link href={x.href} prefetch={false} className="break-words">{x.name}</Link>
                  {x.prime && <span className="block text-small text-ink-muted">{L.prime}: {x.prime.group} (<Src url={x.prime.sourceUrl}>source</Src>)</span>}
                </td>
                <td className="whitespace-nowrap">{x.country ?? L.notStated}</td>
                <td className="text-right font-mono tabular-nums">{formatNumber(x.contracts)}</td>
                <td>{valueLine(x.values.byCurrency) ?? <span className="text-ink-muted">{L.noValue}</span>}</td>
                <td><Notice n={x.notice} /></td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {w.notNamed.length > 0 && (
        <ul className="m-0 flex list-disc flex-col gap-0.5 pl-5 text-small" data-sr-not-named>
          {w.notNamed.map((n) => <li key={n.country ?? '-'}>{L.notNamed(n)}</li>)}
        </ul>
      )}
      {w.total > 0 && <p className="m-0 text-small"><Link href={w.href} prefetch={false}>{L.allWinners(w.total)}</Link></p>}
    </>
  );
}

function OpenNow({ r }: { r: SellReport }) {
  const { tenders, calls } = r.open;
  const day = (d: string | null) => (d ? formatDateUtc(d) : L.notStated);
  return (
    <>
      <h3 className="m-0 text-h4">{L.tenders}</h3>
      {tenders.rows.length === 0 ? <p className="m-0 text-body" data-sr-empty>{L.noTenders}</p> : (
        <Table label={L.tenders}>
          <thead><tr><th scope="col">Tender</th><th scope="col">{L.country}</th><th scope="col">{L.deadline}</th><th scope="col">{L.flag}</th></tr></thead>
          <tbody>
            {tenders.rows.map((t) => (
              <tr key={t.href} data-sr-tender>
                <td><Link href={t.href} prefetch={false} className="break-words">{t.title}</Link><span className="block text-small text-ink-muted">{t.buyer}</span><Src url={t.sourceUrl}>source notice</Src></td>
                <td className="whitespace-nowrap">{t.country ?? L.notStated}</td>
                <td className="whitespace-nowrap">{t.deadlineKnown ? day(t.deadline) : L.notStated}</td>
                <td className="text-small">{L.tenderFlag[t.flag]}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {tenders.href && tenders.total > tenders.rows.length && <p className="m-0 text-small"><Link href={tenders.href} prefetch={false}>{L.moreTenders(tenders.total, !!tenders.totalCapped)}</Link></p>}
      <h3 className="m-0 mt-2 text-h4">{L.calls}</h3>
      {calls.rows.length === 0 ? <p className="m-0 text-body" data-sr-empty>{L.noCalls}</p> : (
        <Table label={L.calls}>
          <thead><tr><th scope="col">Call</th><th scope="col">Programme</th><th scope="col">{L.deadline}</th><th scope="col">{L.flag}</th></tr></thead>
          <tbody>
            {calls.rows.map((c) => (
              <tr key={c.href} data-sr-call>
                <td><Link href={c.href} prefetch={false} className="break-words">{c.title}</Link>{" · "}<Src url={c.sourceUrl}>source</Src></td>
                <td>{c.programme}</td>
                <td className="whitespace-nowrap">{c.rolling ? `${L.rolling}, ${day(c.deadline)}` : day(c.deadline)}</td>
                <td className="text-small">{L.callFlag[c.flag]}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <p className="m-0 text-small text-ink-muted">{L.callWords(calls.words)}</p>
    </>
  );
}

function Ending({ r }: { r: SellReport }) {
  const rows = r.ending?.rows ?? [];
  return (
    <>
      <p className="m-0 max-w-prose text-body">{L.endingLead}</p>
      {rows.length === 0 ? <p className="m-0 text-body" data-sr-empty>{L.noEnding}</p> : (
        <Table label={L.s5}>
          <thead><tr><th scope="col">Contract</th><th scope="col">{L.buyer}</th><th scope="col">{L.end}</th><th scope="col">{L.winner}</th></tr></thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.href} data-sr-ending>
                <td><Link href={e.href} prefetch={false}>{e.title}</Link>{" · "}<Src url={e.sourceUrl}>source</Src></td>
                <td>{e.buyer ?? L.notStated}{e.country ? ` (${e.country})` : ''}</td>
                <td className="whitespace-nowrap">{formatDateUtc(e.end)}{e.endStated ? '' : ` (${L.computed})`}</td>
                <td>{e.winner ?? L.notStated}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}

function Qualify({ r }: { r: SellReport }) {
  const q = r.qualify;
  return (
    <>
      <p className="m-0 max-w-prose text-small text-ink-muted">{L.statusNote}</p>
      <ol className="m-0 flex list-none flex-col p-0">
        {q.items.map((i) => (
          <li key={i.key} className="sr-item flex flex-col gap-1.5 border-t border-line py-3 first:border-t-0" data-sr-item={i.key}>
            <div className="flex flex-wrap items-center gap-3">
              <h3 className="m-0 min-w-0 flex-1 text-h4">{i.name}</h3>
              <StatusBadge s={i.status} />
            </div>
            <p className="m-0 text-small"><strong>{L.appliesTo}:</strong> {L.applies[i.applies]} · <strong>{L.costTime}:</strong> {i.cost || i.time ? [i.cost, i.time].filter(Boolean).join('; ') : L.noCostTime}</p>
            {i.quotes.map((x) => (
              <div key={x.ref + x.text.slice(0, 20)} className="flex flex-col gap-0.5 text-small" data-sr-quote>
                <blockquote className="m-0 break-words border-l-2 border-line pl-3">{excerpt(x.text)}</blockquote>
                <Src url={x.url}>{x.ref}</Src>
              </div>
            ))}
          </li>
        ))}
      </ol>
      {q.verdicts.length > 0 && (
        <>
          <h3 className="m-0 text-h4">{L.verdicts}</h3>
          <ul className="m-0 flex list-none flex-col gap-1 p-0 text-small" data-sr-verdicts>
            {q.verdicts.map((v) => (
              <li key={v.programme}><strong>{v.name}:</strong> {L.verdictWord[v.verdict]}{v.missing ? ` (${v.missing} ${v.missing === 1 ? 'answer' : 'answers'} not given)` : ''} · <Src url={v.sourceUrl}>legal basis</Src></li>
            ))}
          </ul>
          <p className="m-0 text-small text-ink-muted">Every rule, its reason and its source: <Link href="/readiness" prefetch={false}>the readiness check</Link> and <Link href="/requirements" prefetch={false}>the requirements</Link>.</p>
        </>
      )}
      {q.notSourced.length > 0 && (
        <div className="flex flex-col gap-1 text-small" data-sr-not-sourced>
          <p className="m-0 font-semibold">{L.notSourcedHead}</p>
          <ul className="m-0 flex list-disc flex-col gap-0.5 pl-5">{q.notSourced.map((n) => <li key={n.key}><strong>{n.name}.</strong> {n.why}</li>)}</ul>
        </div>
      )}
    </>
  );
}

export function SellReportView({ r }: { r: SellReport }) {
  const m = r.market;
  const brand = r.brand;
  const generated = formatDateUtc(r.generatedAt);
  return (
    <article className="sr flex flex-col gap-6 print:gap-0" data-sell-report data-sample={r.sample || undefined}>
      <style>{PRINT_CSS}</style>
      <header className="flex flex-col gap-3 print:mb-5" data-sr-cover>
        <div className="flex flex-wrap items-center justify-between gap-4">
          {brand ? (
            <span className="inline-flex items-center gap-3" data-sr-brand>
              {/* eslint-disable-next-line @next/next/no-img-element -- a data: URI of the account's own logo, no remote image */}
              {brand.logo && <img src={brand.logo} alt="" className="h-10 w-auto max-w-[160px] object-contain" />}
              {brand.name && <span className="text-h3 font-bold">{brand.name}</span>}
            </span>
          ) : <Logo />}
          <p className="m-0 font-mono text-mono text-ink-muted">{L.generated} {generated}</p>
        </div>
        <p className="m-0 text-small font-bold uppercase tracking-wide">{L.kicker} · {L.title}</p>
        <h1 className="m-0 text-h1-sm md:text-h1 print:text-[22pt] print:leading-tight">{r.profile.name ?? L.title}</h1>
        <p className="m-0 max-w-prose text-body">{L.question}</p>
        <p className="m-0 max-w-prose text-body font-semibold" data-disclaimer>{L.disclaimer}</p>
        {r.sample && <p className="m-0 rounded-md bg-surface-inset p-3 text-small" data-sr-sample>{L.sampleNote}</p>}
      </header>

      <Section id="sr-1" title={L.s1}><Profile r={r} /></Section>

      <Section id="sr-2" title={L.s2}>
        {!m.available ? <Unavailable r={r} /> : (
          <>
            <p className="m-0 max-w-prose text-body">{L.buyersLead(m.total!.procurements, formatDateUtc(m.since!), formatDateUtc(m.until!))}</p>
            {m.buyers!.length === 0 ? <p className="m-0 text-body" data-sr-empty>No defence-scope procurement under these codes in the countries we cover.</p>
              : m.buyers!.filter((b) => b.rows.length > 0).map((b) => <Buyers key={b.country} b={b} />)}
            {m.buyers!.some((b) => b.rows.length === 0) && (
              <p className="m-0 text-small" data-sr-other-countries>
                {L.otherCountries}{' '}
                {m.buyers!.filter((b) => b.rows.length === 0).map((b, i) => (
                  <span key={b.country}>{i > 0 && ' · '}<Link href={b.href} prefetch={false}>{countryName(b.country)}: {L.countryLine(b.procurements, b.buyers, b.coreBuyers)}</Link></span>
                ))}
              </p>
            )}
          </>
        )}
      </Section>

      <Section id="sr-3" title={L.s3}>
        {!m.available ? <Unavailable r={r} /> : m.winners!.total === 0
          ? <p className="m-0 text-body" data-sr-empty>No winner of these contracts is published in what we hold.</p>
          : <Winners r={r} />}
      </Section>

      <Section id="sr-4" title={L.s4}><OpenNow r={r} /></Section>

      {r.ending && <Section id="sr-5" title={L.s5}><Ending r={r} /></Section>}

      <Section id="sr-6" title={L.s6}>
        {r.qualify.available ? <Qualify r={r} /> : <p className="m-0 text-body" data-sr-empty>The requirement rules could not be read just now.</p>}
      </Section>

      <Section id="sr-7" title={L.s7}>
        <ol className="m-0 flex flex-col gap-2 pl-5" data-sr-steps>
          {r.steps.map((s) => <li key={s.key} className="sr-row text-body" data-step={s.key}><strong className="font-mono text-mono">{s.window}</strong> {s.text}</li>)}
        </ol>
      </Section>

      <Section id="sr-8" title={L.s8}>
        <p className="m-0 max-w-prose text-small"><strong>{L.coverageHead}:</strong> {r.sources.coverage}</p>
        {r.sources.winnersFrom && <p className="m-0 max-w-prose text-small">{r.sources.winnersFrom}</p>}
        <ul className="m-0 flex list-none flex-col gap-0.5 p-0 font-mono text-mono text-ink-muted">
          {r.sources.notes.map((n) => <li key={n.code}>{n.attribution}</li>)}
          {r.sources.projects && <li>{r.sources.projects}</li>}
          <li>{r.sources.rules}{r.qualify.rulesReviewed ? ` Rules last reviewed ${r.qualify.rulesReviewed}.` : ''}</li>
          <li>CPV codes and titles: CPV 2008 vocabulary, Publications Office of the EU (CC BY 4.0).</li>
        </ul>
        <p className="m-0 max-w-prose text-body font-semibold">{r.sources.disclaimer}</p>
      </Section>
    </article>
  );
}
