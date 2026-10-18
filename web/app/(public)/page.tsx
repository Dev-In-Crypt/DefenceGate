import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, Building2, Clock, GitCompare, Layers, Link2, SearchCheck, ShieldCheck } from 'lucide-react';
import { getAccountStatus } from '@/lib/account';
import { getCalls, getChanges, getHealth, getSiteStats, getTenderScopeCounts, getTenders, lastDataUpdate } from '@/lib/api';
import { portalWords } from '@/lib/coverage-copy';
import { staleNote, valueMissingNote, valueMissingShares } from '@/lib/source-status';
import { toTenderQuery } from '@/lib/filters';
import { formatDateTimeUtc, formatNumber, repeatedCallBudgets } from '@/lib/format';
import { buildMetadata, faqJsonLd, organizationJsonLd } from '@/lib/seo';
import { BUYER_COUNTRIES, SCOPE_CHOICES, TENDER_SCOPES, cpvDivisionLabel } from '@/lib/taxonomy';
import { Button } from '@/components/dg/button';
import { Select, TextInput } from '@/components/dg/form';
import { AudienceGrid, BenefitGrid, Callout, Faq, Steps, type FaqItem } from '@/components/dg/blocks';
import { CallCard, TenderCard } from '@/components/dg/cards';
import { EmptyState, JsonLd } from '@/components/dg/feedback';
import { Icon } from '@/components/dg/icon';

export const revalidate = 60;
const SAMPLE_SIZE = 3;

export const metadata: Metadata = buildMetadata({
  title: 'Defence and dual-use tenders and funding calls',
  description: 'Tenders, buyers and funding calls from TED and national portals in one place. Every record links to its original source, and changes to dates, values and status are kept.',
  path: '/',
});

/**
 * Example searches for the finder under the headline. Each is a real filter of /tenders; the page counts the open
 * notices of each when it renders and shows the first three that have any, so an example is never an empty list.
 */
const EXAMPLES: { country: string; cpv: string }[] = [
  { country: 'PL', cpv: '35' }, { country: 'FR', cpv: '35' }, { country: 'DE', cpv: '34' },
  { country: 'ES', cpv: '18' }, { country: 'NL', cpv: '50' }, { country: 'SE', cpv: '35' },
];
const EXAMPLES_SHOWN = 3;

const benefits = (names: string) => [
  { icon: SearchCheck, title: 'Many portals, one list', body: `TED notices and the national portals of ${names}, in one list with one layout. Other countries appear through TED only.` },
  { icon: GitCompare, title: 'See what changed', body: 'Deadlines move and values are corrected. We keep a new version when a notice’s deadline, value, status or another main field changes, so you see what changed and when. Our archive began in September 2026.' },
  { icon: Link2, title: 'Straight to the source', body: 'Each record links to its original publication. Check it there before you act: the source is the authority, not us.' },
  { icon: ShieldCheck, title: 'Know what we cover', body: 'Every source, when it last ran and whether it met the minimum we expect are public, with the span of publication dates held. Known gaps are listed on the status page.' },
  { icon: Layers, title: 'Tenders and funding side by side', body: 'EU and national funding calls are in the same directory as the procurement notices and on one deadline calendar. They are searched separately.' },
  { icon: Building2, title: 'The buyer in context', body: 'Open a buyer to see its current and past notices in one place before you decide to bid.' },
];

const AUDIENCE = [
  { who: 'Suppliers and SMEs', body: 'Find the notices that fit what you make, and see deadlines before they pass.' },
  { who: 'Primes and business development', body: 'See buyers across countries and the amendments to their notices in one place, without re-reading each portal.' },
  { who: 'Bid and grant writers', body: 'Check dates, budgets and eligibility fields against the original, with the source one click away.' },
  { who: 'Consultants and advisers', body: 'Keep one current picture of the market to brief clients, with the source one click away.' },
];

const STEPS = [
  { title: 'We collect', body: 'Public notices and funding calls are collected from the sources listed on the status page, once a day.' },
  { title: 'You search and filter', body: 'By country, buyer, deadline, value or keyword. Every fact is shown with its source.' },
  { title: 'You verify and act', body: 'Open the original, confirm the details there, then bid or apply. We link; the decision is yours.' },
];

const faqItems = (portals: { count: string; names: string }): FaqItem[] => [
  { q: 'What is DefenceGate?', a: 'An independent information service that collects publicly published defence and dual-use procurement notices and funding calls, shows them in one directory, and keeps a version history of the changes it observes.' },
  { q: 'Is it an official source?', a: 'No. We are not affiliated with the EU, TED or any government. Every record links to the original publication, which is the authoritative text.' },
  { q: 'Where does the data come from?', a: `From TED, the national tender portals and feeds of ${portals.names}, and public funding portals. The source status page lists each one with its licence, when it last ran and the known gaps.` },
  { q: 'How current is it?', a: 'Each source is collected once a day, not in real time. The status page shows the last run per source. Always confirm deadlines in the original notice.' },
  { q: 'Is it complete?', a: `No, and we do not claim it is. Sources can fail or publish late, national tender portals are collected for ${portals.count} countries only (the others through TED), and some history is still being loaded. A notice you need may be missing, so check the portals relevant to you.` },
  { q: 'How do you decide what counts as defence or dual-use?', a: 'Automatically, from several signals such as the legal basis, the product classification and the buyer. It can be wrong and is not a legal determination. See the methodology page.' },
  { q: 'What does the version history show?', a: 'What changed in a notice between two of our observations and when we saw it, for example a moved deadline or a corrected value. A new version is kept when the title, buyer, country, procedure, legal basis, value, currency, publication date, deadline, product codes, source link or status changes. History starts when we first saw a notice (our archive began in September 2026); earlier states are not reconstructed.' },
  { q: 'Do I need an account?', a: 'Not to browse. Alerts and a personal workspace are being prepared and are not open yet.' },
  { q: 'Is it free?', a: 'Browsing the catalogue is free today. Anything beyond that will be announced with its own terms before it is offered.' },
  { q: 'Do you give legal or bidding advice?', a: 'No. This is information only. For legal, export-control or eligibility questions, ask a qualified adviser.' },
  { q: 'How do I report an error?', a: 'Use the contact route in the imprint and tell us the record and what is wrong. We check it against the source.' },
];

/**
 * A figure of the home page. `value` null means the data service gave none and no earlier answer is held: the tile says
 * so in words. It is never a dash, which read as "zero" or as a broken page (UX walk-throughs of 16 October 2026).
 * `asOf`: the figure is the last good one, from that time.
 */
function Counter({ label, value, sub, asOf }: { label: string; value: string | null; sub?: string; asOf?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-md bg-surface-inset p-4">
      <dt className="text-label text-ink-muted">{label}</dt>
      {value === null
        ? <dd className="m-0 text-body text-ink-muted">Not available right now</dd>
        : <dd className="m-0 font-mono text-figure tabular-nums">{value}</dd>}
      {asOf && value !== null && <dd className="m-0 text-small text-ink-muted">as of {formatDateTimeUtc(asOf)}</dd>}
      {sub && <dd className="m-0 text-small text-ink-muted">{sub}</dd>}
    </div>
  );
}

const ACCOUNT_ANSWER_OPEN = 'Not to browse. An account, opened with a one-time link sent to your e-mail, lets you save searches, follow buyers and programmes and keep a shortlist.';

export default async function LandingPage() {
  const today = new Date().toISOString().slice(0, 10);
  // Cached for a minute; any failure reads as "not open", which keeps the earlier wording.
  const { open: accountsOpen } = await getAccountStatus();
  const health = await getHealth().catch(() => null);
  const portals = portalWords(health?.sources ?? []);
  const faq = faqItems(portals).map((f) => (accountsOpen && f.q === 'Do I need an account?' ? { ...f, a: ACCOUNT_ANSWER_OPEN } : f));
  const [stats, current, dated, closingCalls, counts, goodsOpen, changes, exampleCounts] = await Promise.all([
    getSiteStats().catch(() => null),
    // Current: not past its deadline, and with no deadline only if published within the last year.
    getTenders({ pageSize: 1 }, { cacheable: true }).catch(() => null),
    // With a stated deadline that has not passed: the ones a reader can still act on by date.
    getTenders({ deadlineFrom: today, pageSize: SAMPLE_SIZE }, { cacheable: true }).catch(() => null),
    getCalls({ status: 'closing-soon', pageSize: SAMPLE_SIZE }, { cacheable: true }).catch(() => null),
    // What is in here: open notices by scope, as the list's own filter counts them (one request, three counts).
    getTenderScopeCounts({}),
    // The "Defence goods only" switch narrows whichever scope is chosen; on the default scope it is a part of core.
    getTenders({ goods: 'defence', pageSize: 1 }, { cacheable: true }).catch(() => null),
    getChanges({ pageSize: 1 }).catch(() => null),
    Promise.all(EXAMPLES.map((e) => getTenders({ country: [e.country], cpv: [e.cpv], pageSize: 1 }, { cacheable: true }).then((r) => r.total).catch(() => 0))),
  ]);
  const examples = EXAMPLES.map((e, i) => ({ ...e, open: exampleCounts[i] })).filter((e) => e.open > 0).slice(0, EXAMPLES_SHOWN);
  const closingTenders = dated;
  const closingCallItems = closingCalls?.items ?? [];
  const budgetRepeats = repeatedCallBudgets(closingCallItems);
  const missing = valueMissingShares(health?.sources ?? []);
  const stale = [current, dated].map((r) => r?.staleAsOf).find(Boolean);
  // The goods tile earns its place only when its number differs from core's (it was 300 = 300 on 16 October 2026).
  const showGoods = goodsOpen !== null && counts !== null && goodsOpen.total !== counts.core;
  return (
    <>
      <JsonLd data={organizationJsonLd()} />
      <JsonLd data={faqJsonLd(faq)} />

      <section aria-labelledby="hero" className="grid items-end gap-6 rounded-lg bg-surface p-6 md:p-10 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-5">
          <h1 id="hero" className="m-0 text-[40px] font-extrabold leading-[44px] tracking-[-1.5px] md:text-display">Defence and dual-use tenders and funding, in one place.</h1>
          <p className="m-0 max-w-[52ch] text-body text-ink-muted md:text-h3 md:font-normal">
            Notices from TED and national portals, each linked to its original source, with changes to dates, values and status kept.
          </p>
          {/* The three layers, in the hero (U15: they started 1,849 px down, after the whole tender form). */}
          <ol aria-label="The three parts of DefenceGate" className="m-0 grid list-none gap-2 p-0 md:grid-cols-3">
            <li className="flex flex-col rounded-md bg-surface-inset p-3">
              <span className="text-label text-ink">1. What is open to me?</span>
              <span className="flex flex-wrap gap-x-4 text-small font-bold">
                <Link href="/tenders" className="inline-flex min-h-8 items-center">Tenders</Link>
                <Link href="/funding" className="inline-flex min-h-8 items-center">Funding calls</Link>
              </span>
            </li>
            <li className="flex flex-col rounded-md bg-surface-inset p-3">
              <span className="text-label text-ink">2. Who is already inside?</span>
              <Link href="/organisations" className="inline-flex min-h-8 items-center text-small font-bold">Organisations in funded projects</Link>
            </li>
            <li className="flex flex-col rounded-md bg-surface-inset p-3">
              <span className="text-label text-ink">3. What do I need to qualify?</span>
              <Link href="/readiness" className="inline-flex min-h-8 items-center text-small font-bold">Readiness check</Link>
            </li>
          </ol>
          <form method="get" action="/tenders" role="search" aria-label="Find tenders by country and product code" className="flex flex-col gap-3 rounded-lg bg-surface-inset p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Select name="country" label="Country of the buyer" placeholder="Any country"
                options={Object.entries(BUYER_COUNTRIES).map(([code, name]) => ({ value: code, label: `${name} (${code})` }))} />
              <TextInput name="cpv" label="Product code (CPV)" placeholder="For example 35 or 35120000" maxLength={200} inputMode="numeric" />
            </div>
            <TextInput search name="q" label="Or a word in the title or the name of the buyer" placeholder="For example uniforms" maxLength={100} />
            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" iconRight={ArrowRight}>Find tenders</Button>
              <Link href="/cpv" className="inline-flex min-h-11 items-center text-small font-bold">Not sure of the code? CPV finder</Link>
            </div>
          </form>
          {examples.length > 0 && (
            <div className="flex flex-col gap-1">
              <p className="m-0 text-small text-ink-muted">Open now, for example:</p>
              <ul className="m-0 flex list-none flex-wrap gap-x-5 p-0">
                {examples.map((e) => (
                  <li key={`${e.country}-${e.cpv}`}>
                    <Link href={`/tenders${toTenderQuery({ country: [e.country], cpv: [e.cpv] })}`} className="inline-flex min-h-11 items-center text-small font-bold">
                      {BUYER_COUNTRIES[e.country] ?? e.country}, {cpvDivisionLabel(e.cpv)?.toLowerCase() ?? `CPV ${e.cpv}`}: {formatNumber(e.open)}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-x-5">
            <Link href="/tenders" className="inline-flex min-h-11 items-center text-small font-bold">All current tenders</Link>
            <Link href="/funding" className="inline-flex min-h-11 items-center text-small font-bold">Funding calls</Link>
            <Link href="/changes" className="inline-flex min-h-11 items-center text-small font-bold">What changed</Link>
          </div>
          <p className="m-0 text-small text-ink-muted">Free to browse. No account needed.</p>
        </div>
        <dl aria-label="Live data" className="m-0 grid grid-cols-2 gap-3">
          <Counter label="Tenders with a deadline ahead" value={dated ? formatNumber(dated.total) : null} asOf={dated?.staleAsOf} />
          <Counter label="Current notices" value={current ? formatNumber(current.total) : null} asOf={current?.staleAsOf} sub="including some without a stated deadline" />
          <Counter label="Open funding calls" value={stats ? String(stats.openCalls) : null} />
          <Counter label="Sources" value={stats ? String(stats.sources) : null} />
          <div className="col-span-2"><Counter label="Last collection run" value={stats ? formatDateTimeUtc(stats.lastUpdate) : health ? formatDateTimeUtc(lastDataUpdate(health)) : null} /></div>
        </dl>
      </section>

      <section aria-labelledby="inside" className="flex flex-col gap-4 rounded-lg bg-surface p-6 md:p-8">
        <h2 id="inside" className="m-0 text-h2">What is in here</h2>
        {stale && <p role="status" className="m-0 text-small text-ink-muted">{staleNote(stale, formatDateTimeUtc)}</p>}
        <p className="m-0 max-w-[70ch] text-body text-ink-muted">
          Open tenders, by the scope names of the tender filter. The first is the default list: the other two together.
        </p>
        <dl className="m-0 grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          <Counter label={SCOPE_CHOICES.relevant.short} value={counts ? formatNumber(counts.relevant) : null} sub={`Open tenders. ${SCOPE_CHOICES.relevant.hint}`} />
          <Counter label={SCOPE_CHOICES.core.short} value={counts ? formatNumber(counts.core) : null}
            sub={`${SCOPE_CHOICES.core.hint}${showGoods || goodsOpen === null ? '' : ' The “Defence goods only” switch gives the same list.'}`} />
          {showGoods && goodsOpen && (
            <Counter label="Core, defence goods only" value={formatNumber(goodsOpen.total)} sub="Of the core notices, those that state the directive or a military product code themselves: the “Defence goods only” switch." />
          )}
          <Counter label={SCOPE_CHOICES.supply.short} value={counts ? formatNumber(counts.supply) : null} sub={SCOPE_CHOICES.supply.hint} />
          <Counter label="Open funding calls" value={stats ? String(stats.openCalls) : null} sub="EU and national programmes, searched separately from tenders." />
        </dl>
        <p className="m-0 max-w-[70ch] text-small text-ink-muted">{TENDER_SCOPES.supply.also}</p>
        <p className="m-0 max-w-[70ch] text-small text-ink-muted">
          Not in these counts: notices that are only dual-use (reachable with the scope &ldquo;All&rdquo;) and closed notices. We read the national portals and feeds of {portals.names}; every
          other country appears through TED only. The{' '}
          <Link href="/data" className="font-semibold">status page</Link> lists every source, its span of dates and the known gaps; the{' '}
          <Link href="/methodology" className="font-semibold">methodology</Link> says how a notice is judged.
        </p>
      </section>

      <section aria-labelledby="layers" className="flex flex-col gap-4 rounded-lg bg-surface p-6 md:p-8">
        <h2 id="layers" className="m-0 text-h2">Three questions, three parts</h2>
        <p className="m-0 max-w-[70ch] text-body text-ink-muted">
          A supplier asks the same three things in turn. Each part below answers one of them from public sources, and says where the answer comes from.
        </p>
        <ol className="m-0 grid list-none gap-3 p-0 md:grid-cols-3">
          <li className="flex flex-col gap-2 rounded-md bg-surface-inset p-5">
            <h3 className="m-0 text-h4">1. What is open to me?</h3>
            <p className="m-0 text-body">
              Procurement notices from TED and the national portals, and EU and national funding calls, with their deadlines. A funding call whose rules we have read
              shows what its document says about who may apply.
            </p>
            <p className="m-0 flex flex-wrap gap-x-4 text-small font-bold">
              <Link href="/tenders" className="inline-flex min-h-11 items-center">Tenders</Link>
              <Link href="/funding" className="inline-flex min-h-11 items-center">Funding calls</Link>
            </p>
          </li>
          <li className="flex flex-col gap-2 rounded-md bg-surface-inset p-5">
            <h3 className="m-0 text-h4">2. Who is already inside?</h3>
            <p className="m-0 text-body">
              Who took part in funded projects, in which role and with whom: Horizon Europe, Horizon 2020 and FP7 projects from CORDIS, and European Defence Fund projects
              from the Commission’s factsheets, which a language model reads. A funding call page lists organisations from earlier projects of the same area.
            </p>
            <p className="m-0 flex flex-wrap gap-x-4 text-small font-bold">
              <Link href="/organisations" className="inline-flex min-h-11 items-center">Organisations in funded projects</Link>
            </p>
          </li>
          <li className="flex flex-col gap-2 rounded-md bg-surface-inset p-5">
            <h3 className="m-0 text-h4">3. What do I need to qualify?</h3>
            <p className="m-0 text-body">
              Five short questions about your company, kept in your browser, give a verdict for the European Defence Fund, EDIP and SAFE, the steps you would still need,
              and, on a call page, whether you can get them before the deadline. Each rule shows the text it rests on.
            </p>
            <p className="m-0 flex flex-wrap gap-x-4 text-small font-bold">
              <Link href="/readiness" className="inline-flex min-h-11 items-center">Readiness check</Link>
              <Link href="/requirements" className="inline-flex min-h-11 items-center">Requirements</Link>
            </p>
          </li>
        </ol>
        <p className="m-0 max-w-[70ch] text-small text-ink-muted">
          None of this is legal advice or a promise of eligibility: the call text and the contracting authority decide.
        </p>
      </section>

      {changes && (
        <section aria-labelledby="changed" className="flex flex-col items-start gap-3 rounded-lg bg-surface p-6 md:p-8">
          <h2 id="changed" className="m-0 text-h2">What changed in the last {changes.windowDays} days</h2>
          <p className="m-0 max-w-[70ch] text-body text-ink-muted">
            <span className="font-mono tabular-nums text-ink">{formatNumber(changes.counts.new)}</span> new notices and{' '}
            <span className="font-mono tabular-nums text-ink">{formatNumber(changes.counts.amended)}</span> amendments to a deadline, value, status or procedure,
            from our archive. There is an Atom feed of the same list: no account needed.
          </p>
          <div className="flex flex-wrap items-center gap-x-5">
            <Button href="/changes" variant="secondary">See what changed</Button>
            <a href="/changes.atom" className="inline-flex min-h-11 items-center text-small font-bold">Atom feed</a>
          </div>
        </section>
      )}

      <section aria-labelledby="why" className="flex flex-col gap-4">
        <h2 id="why" className="m-0 text-h2">Why DefenceGate</h2>
        <BenefitGrid items={benefits(portals.names)} />
      </section>

      <section aria-labelledby="who" className="flex flex-col gap-4">
        <h2 id="who" className="m-0 text-h2">Built for the people who bid, advise and write</h2>
        <AudienceGrid items={AUDIENCE} />
      </section>

      <section aria-labelledby="how" className="flex flex-col gap-4">
        <h2 id="how" className="m-0 text-h2">How it works</h2>
        <Steps items={STEPS} />
      </section>

      <section aria-labelledby="closing-tenders" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="closing-tenders" className="m-0 text-h2">Tenders closing next</h2>
          <Link href="/tenders" className="inline-flex min-h-11 items-center text-small font-bold">All current tenders</Link>
        </div>
        {!closingTenders ? (
          // The data service did not answer and no earlier answer is held: say that, not "no tenders".
          <EmptyState title="The list could not be loaded just now" action={<Button variant="secondary" href="/tenders">Open the tender list</Button>}>
            The data service is slow at the moment. This is not an empty market: reload in a minute, or open the full list.
          </EmptyState>
        ) : closingTenders.items.length === 0 ? (
          <EmptyState title="No tenders to show right now" action={<Button variant="secondary" href="/tenders">Browse all tenders</Button>} />
        ) : (
          <ul className="m-0 grid list-none gap-4 p-0 lg:grid-cols-3">
            {closingTenders.items.map((t) => <li key={t.id} className="min-w-0"><TenderCard tender={t} headingLevel="h3" valueNote={valueMissingNote(missing, t.source.sourceId)} /></li>)}
          </ul>
        )}
      </section>

      <section aria-labelledby="closing" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="closing" className="m-0 text-h2">Funding calls closing soon</h2>
          <Link href="/funding?status=closing-soon" className="inline-flex min-h-11 items-center text-small font-bold">All calls closing within 30 days</Link>
        </div>
        {closingCalls === null ? (
          <EmptyState title="The list could not be loaded just now" action={<Button variant="secondary" href="/funding">Open the funding list</Button>}>
            The data service is slow at the moment. This is not an empty list: reload in a minute.
          </EmptyState>
        ) : closingCallItems.length === 0 ? (
          <EmptyState title="No calls close in the next 30 days" action={<Button variant="secondary" href="/funding">Browse all open calls</Button>} />
        ) : (
          <ul className="m-0 grid list-none gap-4 p-0 lg:grid-cols-3">
            {closingCallItems.map((c) => <li key={c.id} className="min-w-0"><CallCard call={c} headingLevel="h3" budgetRepeated={budgetRepeats.has(c.id)} /></li>)}
          </ul>
        )}
      </section>

      <section aria-labelledby="next" className="flex flex-col items-start gap-4 rounded-lg bg-surface p-6 md:p-8">
        <span className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink"><Icon icon={Clock} /></span>
        <h2 id="next" className="m-0 text-h2">{accountsOpen ? 'Save searches and keep a shortlist' : 'Alerts and a personal workspace are being prepared'}</h2>
        <p className="m-0 max-w-[62ch] text-body text-ink-muted">
          {accountsOpen
            ? 'Sign in with your e-mail to save a search, follow buyers and programmes, and keep a shortlist for your own bids. Browsing stays free.'
            : 'Saved searches with alerts for new matches, followed buyers and programmes, and a shortlist for your own bids. They are not open yet. Browsing stays free.'}
        </p>
        <div className="flex flex-wrap items-center gap-x-5">
          <Button href={accountsOpen ? '/signin' : '/alerts'} variant="secondary">{accountsOpen ? 'Sign in' : 'What is planned and what works today'}</Button>
          {!accountsOpen && <Link href="/changes" className="inline-flex min-h-11 items-center text-small font-bold">What changed (works today)</Link>}
        </div>
      </section>

      <Callout title="Please note">
        <p className="m-0">DefenceGate is an information service, not an official source and not advice. The original publication is authoritative; check it before you act. See the <Link href="/terms" className="font-semibold">terms</Link>.</p>
      </Callout>

      <section aria-labelledby="faq" className="flex flex-col gap-4">
        <h2 id="faq" className="m-0 text-h2">Questions</h2>
        <Faq items={faq} />
      </section>
    </>
  );
}
