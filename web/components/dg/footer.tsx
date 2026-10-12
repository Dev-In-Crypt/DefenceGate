import Link from 'next/link';
import { Logo } from './logo';
import { getHealth } from '@/lib/api';
import { formatDateTimeUtc } from '@/lib/format';

const COLUMNS = [
  { title: 'Directory', links: [['Funding calls', '/funding'], ['Closing soon', '/funding/closing-soon'], ['Tenders', '/tenders'], ['Buyers', '/buyers']] },
  { title: 'Data', links: [['Source status', '/data'], ['Get alerts', '/alerts/subscribe'], ['Opportunity pack', '/pack'], ['Pricing', '/pricing']] },
  { title: 'Legal', links: [['Privacy', '/privacy'], ['Terms', '/terms'], ['Imprint', '/imprint']] },
] as const;

export async function Footer() {
  const health = await getHealth();
  return (
    <footer className="page pb-8">
      <div className="flex flex-col gap-8 rounded-lg bg-surface p-6">
        <div className="grid gap-8 md:grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(0,1fr))]">
          <div className="flex flex-col gap-3">
            <Logo href="/" />
            <p className="m-0 max-w-[36ch] text-small text-ink-muted">Defence and dual-use funding calls and tenders, in one English feed.</p>
          </div>
          {COLUMNS.map((col) => (
            <nav key={col.title} aria-label={col.title} className="flex flex-col gap-1">
              <h2 className="m-0 text-label text-ink-muted">{col.title}</h2>
              {col.links.map(([label, href]) => (
                <Link key={href} href={href} className="inline-flex min-h-11 items-center text-small font-semibold text-ink md:min-h-8">{label}</Link>
              ))}
            </nav>
          ))}
        </div>
        <div className="flex flex-wrap justify-between gap-2 border-t border-line pt-4 font-mono text-mono text-ink-muted">
          <span>{health.sources.length} sources · Last update {formatDateTimeUtc(health.generatedAt)}</span>
          <span>All dates in UTC</span>
        </div>
      </div>
    </footer>
  );
}
