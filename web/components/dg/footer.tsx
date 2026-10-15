import Link from 'next/link';
import { Logo } from './logo';
import { getHealth, lastDataUpdate } from '@/lib/api';
import { formatDateTimeUtc } from '@/lib/format';

const COLUMNS: { title: string; links: { label: string; href: string }[] }[] = [
  { title: 'Directory', links: [
    { label: 'Funding calls', href: '/funding' }, { label: 'Closing soon', href: '/funding?status=closing-soon' },
    { label: 'Tenders', href: '/tenders' }, { label: 'Buyers', href: '/buyers' },
    { label: 'Deadline calendar', href: '/calendar' }, { label: 'What changed', href: '/changes' },
  ] },
  { title: 'Data', links: [
    { label: 'Source status', href: '/data' }, { label: 'Methodology', href: '/methodology' },
    { label: 'Market overview', href: '/market' }, { label: 'CPV finder', href: '/cpv' }, { label: 'Glossary', href: '/glossary' },
    { label: 'Alerts (not open yet)', href: '/alerts' }, { label: 'Opportunity pack', href: '/pack' },
    { label: 'Pricing', href: '/pricing' },
  ] },
  { title: 'About and legal', links: [
    { label: 'About', href: '/about' }, { label: 'Privacy', href: '/privacy' },
    { label: 'Terms', href: '/terms' }, { label: 'Imprint', href: '/imprint' },
  ] },
];

export async function Footer() {
  const health = await getHealth();
  return (
    <footer className="page pb-8 print:hidden">
      <div className="flex flex-col gap-8 rounded-lg bg-surface p-6">
        <div className="grid gap-8 md:grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(0,1fr))]">
          <div className="flex flex-col gap-3">
            <Logo href="/" />
            <p className="m-0 max-w-[36ch] text-small text-ink-muted">Defence and dual-use tenders and funding calls, in one place.</p>
            <div className="mt-2 flex max-w-[34ch] flex-col gap-2 rounded-md bg-surface-inset p-4">
              <p className="m-0 text-small text-ink-muted">Which sources are healthy, and when each was last collected.</p>
              <Link href="/data" className="text-small font-semibold text-ink">Source status →</Link>
            </div>
            <nav aria-label="Follow" className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <span className="text-label text-ink-muted">Follow</span>
              <a href="/changes.atom" className="inline-flex min-h-8 items-center text-small font-semibold text-ink">Atom feed</a>
              <a href="/calendar.ics" className="inline-flex min-h-8 items-center text-small font-semibold text-ink">Calendar (.ics)</a>
              <a href="/tenders/export.csv" className="inline-flex min-h-8 items-center text-small font-semibold text-ink">CSV</a>
            </nav>
          </div>
          {COLUMNS.map((col) => (
            <nav key={col.title} aria-label={col.title} className="flex flex-col">
              <p className="m-0 text-label text-ink-muted">{col.title}</p>
              {col.links.map(({ label, href }) => (
                <Link key={label} href={href} className="inline-flex min-h-11 items-center text-small font-semibold text-ink md:min-h-7">{label}</Link>
              ))}
            </nav>
          ))}
        </div>
        <p className="m-0 max-w-[90ch] border-t border-line pt-4 text-small text-ink-muted">
          DefenceGate is an information service. It is not an official source and is not affiliated with the European Union, TED or any government. The original publication is authoritative: check it before you act. Nothing here is legal or professional advice.
        </p>
        <div className="flex flex-wrap justify-between gap-2 font-mono text-mono text-ink-muted">
          <span>{health.sources.length} sources · Last collection run {formatDateTimeUtc(lastDataUpdate(health))}</span>
          <span>All dates in UTC</span>
        </div>
      </div>
    </footer>
  );
}
