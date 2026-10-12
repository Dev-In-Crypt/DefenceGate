import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, Building2, Clock, GitCompare, Layers, Link2, SearchCheck, ShieldCheck } from 'lucide-react';
import { getCalls, getSiteStats, getTenders } from '@/lib/api';
import { formatDateTimeUtc, formatNumber } from '@/lib/format';
import { buildMetadata, faqJsonLd, organizationJsonLd } from '@/lib/seo';
import { Button } from '@/components/dg/button';
import { AudienceGrid, BenefitGrid, Callout, Faq, Steps, type FaqItem } from '@/components/dg/blocks';
import { CallCard, TenderCard } from '@/components/dg/cards';
import { EmptyState, JsonLd } from '@/components/dg/feedback';
import { Icon } from '@/components/dg/icon';

export const revalidate = 3600;
const SAMPLE_SIZE = 3;

export const metadata: Metadata = buildMetadata({
  title: 'Defence and dual-use tenders and funding calls',
  description: 'Tenders, buyers and funding calls from TED and national portals in one place. Every record links to its original source, and every change is kept.',
  path: '/',
});

const BENEFITS = [
  { icon: SearchCheck, title: 'One search, many portals', body: 'Stop visiting a dozen portals in a dozen formats. Search notices from TED and national portals together, in English.' },
  { icon: GitCompare, title: 'See what changed', body: 'Deadlines move and values are corrected. Every version of a notice is kept, so you see what changed and when.' },
  { icon: Link2, title: 'Straight to the source', body: 'Each record links to its original publication. Check it there before you act: the source is the authority, not us.' },
  { icon: ShieldCheck, title: 'Know what we cover', body: 'Every source, its last run and its coverage are public. Gaps are shown, not hidden.' },
  { icon: Layers, title: 'Tenders and funding together', body: 'EU and national funding calls sit next to the procurement notices, so one search covers both ways in.' },
  { icon: Building2, title: 'The buyer in context', body: 'Open a buyer to see its current and past notices in one place before you decide to bid.' },
];

const AUDIENCE = [
  { who: 'Suppliers and SMEs', body: 'Find the notices that fit what you make, and see deadlines before they pass.' },
  { who: 'Primes and business development', body: 'Follow buyers across countries and notice amendments without re-reading every portal.' },
  { who: 'Bid and grant writers', body: 'Check dates, budgets and eligibility fields against the original in a fraction of the time.' },
  { who: 'Consultants and advisers', body: 'Keep one current picture of the market to brief clients, with the source one click away.' },
];

const STEPS = [
  { title: 'We collect', body: 'Public notices and funding calls are collected from the sources listed on the status page, on a schedule.' },
  { title: 'You search and filter', body: 'By country, buyer, deadline, value or keyword. Every fact is shown with its source.' },
  { title: 'You verify and act', body: 'Open the original, confirm the details there, then bid or apply. We link; the decision is yours.' },
];

const FAQ: FaqItem[] = [
  { q: 'What is DefenceGate?', a: 'An independent information service that collects publicly published defence and dual-use procurement notices and funding calls, shows them in one searchable place, and keeps every version of each notice.' },
  { q: 'Is it an official source?', a: 'No. We are not affiliated with the EU, TED or any government. Every record links to the original publication, which is the authoritative text.' },
  { q: 'Where does the data come from?', a: 'From TED, national procurement portals and public funding portals. The source status page lists each one with its licence and when it last ran.' },
  { q: 'How current is it?', a: 'Each source is collected on a schedule, not in real time. The status page shows the last run per source. Always confirm deadlines in the original notice.' },
  { q: 'Is it complete?', a: 'No, and we do not claim it is. Sources can fail or publish late, and not every portal is covered. A notice you need may be missing, so check the portals relevant to you.' },
  { q: 'How do you decide what counts as defence or dual-use?', a: 'Automatically, from several signals such as the legal basis, the product classification and the buyer. It can be wrong and is not a legal determination. See the methodology page.' },
  { q: 'What does the version history show?', a: 'What changed in a notice between two observations and when we saw it, for example a moved deadline or a corrected value.' },
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

export default async function LandingPage() {
  const [stats, tenders, closingCalls, closingTenders] = await Promise.all([
    getSiteStats(),
    getTenders({}, { cacheable: true }).catch(() => null),
    getCalls({ status: 'closing-soon', pageSize: SAMPLE_SIZE }, { cacheable: true }),
    getTenders({ pageSize: SAMPLE_SIZE }, { cacheable: true }).catch(() => null),
  ]);
  return (
    <>
      <JsonLd data={organizationJsonLd()} />
      <JsonLd data={faqJsonLd(FAQ)} />

      <section aria-labelledby="hero" className="grid items-end gap-6 rounded-lg bg-surface p-6 md:p-10 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-5">
          <h1 id="hero" className="m-0 text-[40px] font-extrabold leading-[44px] tracking-[-1.5px] md:text-display">Defence and dual-use tenders and funding, in one place.</h1>
          <p className="m-0 max-w-[52ch] text-body text-ink-muted md:text-h3 md:font-normal">
            Notices from TED and national portals, each linked to its original source, with every change kept.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button href="/tenders" iconRight={ArrowRight}>Browse open tenders</Button>
            <Button href="/funding" variant="secondary">Browse funding calls</Button>
          </div>
          <p className="m-0 text-small text-ink-muted">Free to browse. No account needed.</p>
        </div>
        <dl aria-label="Live data" className="m-0 grid grid-cols-2 gap-3">
          <Counter label="Open tenders" value={tenders ? formatNumber(tenders.total) : '–'} />
          <Counter label="Open funding calls" value={String(stats.openCalls)} />
          <Counter label="Sources" value={String(stats.sources)} />
          <Counter label="Last update" value={formatDateTimeUtc(stats.lastUpdate)} />
        </dl>
      </section>

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
          <Link href="/tenders" className="inline-flex min-h-11 items-center text-small font-bold">All open tenders</Link>
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
            {closingCalls.items.map((c) => <li key={c.id} className="min-w-0"><CallCard call={c} headingLevel="h3" /></li>)}
          </ul>
        )}
      </section>

      <section aria-labelledby="next" className="flex flex-col items-start gap-4 rounded-lg bg-surface p-6 md:p-8">
        <span className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink"><Icon icon={Clock} /></span>
        <h2 id="next" className="m-0 text-h2">Alerts and a personal workspace are being prepared</h2>
        <p className="m-0 max-w-[62ch] text-body text-ink-muted">
          Saved searches, alerts when a notice you follow changes, and a shortlist for your own bids. They are not open yet. Browsing stays free.
        </p>
        <Button href="/alerts" variant="secondary">What is planned</Button>
      </section>

      <Callout title="Please note">
        <p className="m-0">DefenceGate is an information service, not an official source and not advice. The original publication is authoritative; check it before you act. See the <Link href="/terms" className="font-semibold">terms</Link>.</p>
      </Callout>

      <section aria-labelledby="faq" className="flex flex-col gap-4">
        <h2 id="faq" className="m-0 text-h2">Questions</h2>
        <Faq items={FAQ} />
      </section>
    </>
  );
}
