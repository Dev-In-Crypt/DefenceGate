import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, Building2, Clock, GitCompare, Layers, Link2, SearchCheck, ShieldCheck } from 'lucide-react';
import { getAccountStatus } from '@/lib/account';
import { getCalls, getChanges, getSiteStats, getTenders } from '@/lib/api';
import { toTenderQuery } from '@/lib/filters';
import { formatDateTimeUtc, formatNumber, repeatedCallBudgets } from '@/lib/format';
import { buildMetadata, faqJsonLd, organizationJsonLd } from '@/lib/seo';
import { BUYER_COUNTRIES, TENDER_SCOPES, cpvDivisionLabel } from '@/lib/taxonomy';
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

const BENEFITS = [
  { icon: SearchCheck, title: 'Many portals, one list', body: 'TED notices and the national portals of France, the Netherlands, Poland and Spain, in one list with one layout. Other countries appear through TED only.' },
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

const FAQ: FaqItem[] = [
  { q: 'What is DefenceGate?', a: 'An independent information service that collects publicly published defence and dual-use procurement notices and funding calls, shows them in one directory, and keeps a version history of the changes it observes.' },
  { q: 'Is it an official source?', a: 'No. We are not affiliated with the EU, TED or any government. Every record links to the original publication, which is the authoritative text.' },
  { q: 'Where does the data come from?', a: 'From TED, the national tender portals of France, the Netherlands, Poland and Spain, and public funding portals. The source status page lists each one with its licence, when it last ran and the known gaps.' },
  { q: 'How current is it?', a: 'Each source is collected once a day, not in real time. The status page shows the last run per source. Always confirm deadlines in the original notice.' },
  { q: 'Is it complete?', a: 'No, and we do not claim it is. Sources can fail or publish late, national tender portals are collected for four countries only, and some history is still being loaded. A notice you need may be missing, so check the portals relevant to you.' },
  { q: 'How do you decide what counts as defence or dual-use?', a: 'Automatically, from several signals such as the legal basis, the product classification and the buyer. It can be wrong and is not a legal determination. See the methodology page.' },
  { q: 'What does the version history show?', a: 'What changed in a notice between two of our observations and when we saw it, for example a moved deadline or a corrected value. A new version is kept when the title, buyer, country, procedure, legal basis, value, currency, publication date, deadline, product codes, source link or status changes. History starts when we first saw a notice (our archive began in September 2026); earlier states are not reconstructed.' },
  { q: 'Do I need an account?', a: 'Not to browse. Alerts and a personal workspace are being prepared and are not open yet.' },
  { q: 'Is it free?', a: 'Browsing the catalogue is free today. Anything beyond that will be announced with its own terms before it is offered.' },
  { q: 'Do you give legal or bidding advice?', a: 'No. This is information only. For legal, export-control or eligibility questions, ask a qualified adviser.' },
  { q: 'How do I report an error?', a: 'Use the contact route in the imprint and tell us the record and what is wrong. We check it against the source.' },
];

function Counter({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-md bg-surface-inset p-4">
      <dt className="text-label text-ink-muted">{label}</dt>
      <dd className="m-0 font-mono text-figure tabular-nums">{value}</dd>
      {sub && <dd className="m-0 text-small text-ink-muted">{sub}</dd>}
    </div>
  );
}

const ACCOUNT_ANSWER_OPEN = 'Not to browse. An account, opened with a one-time link sent to your e-mail, lets you save searches, follow buyers and programmes and keep a shortlist.';

export default async function LandingPage() {
  const today = new Date().toISOString().slice(0, 10);
  // Cached for a minute; any failure reads as "not open", which keeps the earlier wording.
  const { open: accountsOpen } = await getAccountStatus();
  const faq = FAQ.map((f) => (accountsOpen && f.q === 'Do I need an account?' ? { ...f, a: ACCOUNT_ANSWER_OPEN } : f));
  const [stats, current, dated, closingCalls, coreOpen, supplyOpen, changes, exampleCounts] = await Promise.all([
    getSiteStats(),
    // Current: not past its deadline, and with no deadline only if published within the last year.
    getTenders({ pageSize: 1 }, { cacheable: true }).catch(() => null),
    // With a stated deadline that has not passed: the ones a reader can still act on by date.
    getTenders({ deadlineFrom: today, pageSize: SAMPLE_SIZE }, { cacheable: true }).catch(() => null),
    getCalls({ status: 'closing-soon', pageSize: SAMPLE_SIZE }, { cacheable: true }),
    // What is in here: open notices by scope, as the list's own filter counts them.
    getTenders({ scope: 'core', pageSize: 1 }, { cacheable: true }).catch(() => null),
    getTenders({ scope: 'supply', pageSize: 1 }, { cacheable: true }).catch(() => null),
    getChanges({ pageSize: 1 }).catch(() => null),
    Promise.all(EXAMPLES.map((e) => getTenders({ country: [e.country], cpv: [e.cpv], pageSize: 1 }, { cacheable: true }).then((r) => r.total).catch(() => 0))),
  ]);
  const examples = EXAMPLES.map((e, i) => ({ ...e, open: exampleCounts[i] })).filter((e) => e.open > 0).slice(0, EXAMPLES_SHOWN);
  const closingTenders = dated;
  const budgetRepeats = repeatedCallBudgets(closingCalls.items);
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
          <Counter label="Tenders with a deadline ahead" value={dated ? formatNumber(dated.total) : '–'} />
          <Counter label="Current notices" value={current ? formatNumber(current.total) : '–'} sub="including some without a stated deadline" />
          <Counter label="Open funding calls" value={String(stats.openCalls)} />
          <Counter label="Sources" value={String(stats.sources)} />
          <div className="col-span-2"><Counter label="Last collection run" value={formatDateTimeUtc(stats.lastUpdate)} /></div>
        </dl>
      </section>

      <section aria-labelledby="inside" className="flex flex-col gap-4 rounded-lg bg-surface p-6 md:p-8">
        <h2 id="inside" className="m-0 text-h2">What is in here</h2>
        <p className="m-0 max-w-[70ch] text-body text-ink-muted">
          Open tenders, split by how the notice itself qualifies. The tender search above shows the first by default; the second is the &ldquo;Supplies to defence buyers&rdquo; choice of the scope filter.
        </p>
        <dl className="m-0 grid gap-3 md:grid-cols-3">
          <Counter label="Defence notices" value={coreOpen ? formatNumber(coreOpen.total) : '–'} sub={`Open tenders. ${TENDER_SCOPES.core.hint} The tender list shows these by default.`} />
          <Counter label="Supplies to defence buyers" value={supplyOpen ? formatNumber(supplyOpen.total) : '–'} sub={`Open tenders. ${TENDER_SCOPES.supply.hint}`} />
          <Counter label="Open funding calls" value={String(stats.openCalls)} sub="EU and national programmes, searched separately from tenders." />
        </dl>
        <p className="m-0 max-w-[70ch] text-small text-ink-muted">{TENDER_SCOPES.supply.also}</p>
        <p className="m-0 max-w-[70ch] text-small text-ink-muted">
          Not in these counts: notices that are only dual-use (reachable with the scope &ldquo;All&rdquo;) and closed notices. We read the national portals of France, the
          Netherlands, Poland and Spain; every other country appears through TED only. The{' '}
          <Link href="/data" className="font-semibold">status page</Link> lists every source, its span of dates and the known gaps; the{' '}
          <Link href="/methodology" className="font-semibold">methodology</Link> says how a notice is judged.
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
        <BenefitGrid items={BENEFITS} />
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
        {!closingTenders || closingTenders.items.length === 0 ? (
          <EmptyState title="No tenders to show right now" action={<Button variant="secondary" href="/tenders">Browse all tenders</Button>} />
        ) : (
          <ul className="m-0 grid list-none gap-4 p-0 lg:grid-cols-3">
            {closingTenders.items.map((t) => <li key={t.id} className="min-w-0"><TenderCard tender={t} headingLevel="h3" /></li>)}
          </ul>
        )}
      </section>

      <section aria-labelledby="closing" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="closing" className="m-0 text-h2">Funding calls closing soon</h2>
          <Link href="/funding?status=closing-soon" className="inline-flex min-h-11 items-center text-small font-bold">All calls closing within 30 days</Link>
        </div>
        {closingCalls.items.length === 0 ? (
          <EmptyState title="No calls close in the next 30 days" action={<Button variant="secondary" href="/funding">Browse all open calls</Button>} />
        ) : (
          <ul className="m-0 grid list-none gap-4 p-0 lg:grid-cols-3">
            {closingCalls.items.map((c) => <li key={c.id} className="min-w-0"><CallCard call={c} headingLevel="h3" budgetRepeated={budgetRepeats.has(c.id)} /></li>)}
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
