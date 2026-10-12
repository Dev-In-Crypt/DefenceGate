import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, Database, Filter, Bell, Plus } from 'lucide-react';
import { getCalls, getSiteStats } from '@/lib/api';
import { formatDateTimeUtc } from '@/lib/format';
import { AUDIENCE_COUNTRIES } from '@/lib/taxonomy';
import { buildMetadata, faqJsonLd, organizationJsonLd } from '@/lib/seo';
import { Button } from '@/components/dg/button';
import { CallCard } from '@/components/dg/cards';
import { CountryLabel } from '@/components/dg/data-display';
import { EmptyState, JsonLd } from '@/components/dg/feedback';
import { Icon } from '@/components/dg/icon';
import { WaitlistForm } from '@/components/landing/waitlist-form';

export const revalidate = 3600;
const SAMPLE_SIZE = 3;

export const metadata: Metadata = buildMetadata({
  title: 'Defence funding and tenders for SMEs',
  description: 'EU and national defence and dual-use funding calls and tenders in one English feed. For manufacturers with 20 to 500 staff.',
  path: '/',
});

const STEPS = [
  { icon: Database, title: 'We collect', body: 'Funding calls and tenders from EU and national portals, every day, normalised into English.' },
  { icon: Filter, title: 'You filter', body: 'By programme, country, deadline and budget. Every fact links to its source.' },
  { icon: Bell, title: 'You act', body: 'Get alerts before deadlines, or order an opportunity pack for a specific call.' },
];

const FAQ = [
  { q: 'Who is DefenceGate for?', a: 'Owners, managing directors and bid managers at manufacturers with 20 to 500 staff who want to supply European defence and dual-use programmes.' },
  { q: 'Where does the data come from?', a: 'From public EU and national portals such as the EU Funding & Tenders Portal and TED. Each call shows its source, licence and the time we retrieved it.' },
  { q: 'Do I need defence experience?', a: 'No. Many calls are dual-use and open to civil manufacturers. Eligibility is listed as structured fields on every call.' },
  { q: 'How often is it updated?', a: 'Every source is collected daily. The Data page shows the status of the last run for each source.' },
  { q: 'Is it free?', a: 'The directory is free. Alerts, opportunity packs and the Pro archive are paid.' },
  { q: 'Why are all times in UTC?', a: 'Calls come from many time zones. UTC gives one unambiguous reference. Always check the original notice before you submit.' },
];

function Counter({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-1 rounded-md bg-surface-inset p-4">
      <dt className="text-label text-ink-muted">{label}</dt>
      <dd className={mono ? 'm-0 font-mono text-figure tabular-nums' : 'm-0 font-mono text-mono-strong tabular-nums'}>{value}</dd>
    </div>
  );
}

export default async function LandingPage() {
  const [stats, closing] = await Promise.all([getSiteStats(), getCalls({ status: 'closing-soon', pageSize: SAMPLE_SIZE }, { cacheable: true })]);
  return (
    <>
      <JsonLd data={organizationJsonLd()} />
      <JsonLd data={faqJsonLd(FAQ)} />

      <section aria-labelledby="hero" className="grid items-end gap-6 rounded-lg bg-surface p-6 md:p-10 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-5">
          <h1 id="hero" className="m-0 text-[40px] font-extrabold leading-[44px] tracking-[-1.5px] md:text-display">Your way into European defence supply chains.</h1>
          <p className="m-0 max-w-[52ch] text-body text-ink-muted md:text-h3 md:font-normal">
            Funding calls and tenders from EU and national portals, in one English feed. See what is open, when it closes and whether it fits your company.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button href="/funding" iconRight={ArrowRight}>Browse open calls</Button>
            <Button href="#waitlist" variant="secondary">Join the waitlist</Button>
          </div>
        </div>
        <dl aria-label="Live data" className="m-0 grid grid-cols-2 gap-3">
          <Counter label="Open calls" value={String(stats.openCalls)} />
          <Counter label="Sources" value={String(stats.sources)} />
          <div className="col-span-2"><Counter label="Last update" value={formatDateTimeUtc(stats.lastUpdate)} mono={false} /></div>
        </dl>
      </section>

      <section aria-labelledby="audience" className="flex flex-col gap-4">
        <h2 id="audience" className="m-0 text-h2">For manufacturers with 20 to 500 staff</h2>
        <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
          {AUDIENCE_COUNTRIES.map((c) => <li key={c} className="rounded-pill bg-surface px-4 py-2 text-small font-semibold"><CountryLabel code={c} /></li>)}
        </ul>
      </section>

      <section aria-labelledby="how" className="flex flex-col gap-4">
        <h2 id="how" className="m-0 text-h2">How it works</h2>
        <ol className="m-0 grid list-none gap-4 p-0 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex flex-col gap-3 rounded-lg bg-surface p-6">
              <div className="flex items-center gap-3">
                <span className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink"><Icon icon={s.icon} /></span>
                <span className="font-mono text-mono text-ink-muted">Step {i + 1}</span>
              </div>
              <h3 className="m-0 text-h3">{s.title}</h3>
              <p className="m-0 text-body text-ink-muted">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="closing" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="closing" className="m-0 text-h2">Closing soon</h2>
          <Link href="/funding?status=closing-soon" className="inline-flex min-h-11 items-center text-small font-bold">All calls closing within 30 days</Link>
        </div>
        {closing.items.length === 0 ? (
          <EmptyState title="No calls close in the next 30 days" action={<Button variant="secondary" href="/funding">Browse all open calls</Button>} />
        ) : (
          <ul className="m-0 grid list-none gap-4 p-0 lg:grid-cols-3">
            {closing.items.map((c) => <li key={c.id} className="min-w-0"><CallCard call={c} headingLevel="h3" /></li>)}
          </ul>
        )}
      </section>

      <section id="waitlist" aria-labelledby="waitlist-h" className="grid scroll-mt-4 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="flex flex-col gap-3">
          <h2 id="waitlist-h" className="m-0 text-h2">Join the waitlist</h2>
          <p className="m-0 text-body text-ink-muted">Sign-ups are not open yet. The form checks your answers, but nothing is stored or sent.</p>
        </div>
        <WaitlistForm />
      </section>

      <section aria-labelledby="faq" className="flex flex-col gap-4">
        <h2 id="faq" className="m-0 text-h2">Questions</h2>
        <div className="flex flex-col gap-2">
          {FAQ.map((f) => (
            <details key={f.q} className="group rounded-lg bg-surface px-6">
              <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 py-4 text-body font-semibold [&::-webkit-details-marker]:hidden">
                {f.q}
                <Icon icon={Plus} className="shrink-0 text-ink-muted transition-transform duration-dg group-open:rotate-45" />
              </summary>
              <p className="m-0 pb-5 text-body text-ink-muted">{f.a}</p>
            </details>
          ))}
        </div>
      </section>
    </>
  );
}
