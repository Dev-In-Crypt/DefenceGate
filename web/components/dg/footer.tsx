import Link from 'next/link';
import { Logo } from './logo';
import { getHealth } from '@/lib/api';
import { formatDateTimeUtc } from '@/lib/format';

/** A link without `href` is a page that does not exist yet: it renders as text marked "Coming soon". */
interface FooterLink { label: string; href?: string }

const COLUMNS: { title: string; links: FooterLink[] }[] = [
  { title: 'Directory', links: [{ label: 'Funding calls', href: '/funding' }, { label: 'Closing soon', href: '/funding?status=closing-soon' }, { label: 'Tenders' }, { label: 'Buyers' }] },
  { title: 'Data', links: [{ label: 'Source status' }, { label: 'Get alerts' }, { label: 'Opportunity pack' }, { label: 'Pricing' }] },
  { title: 'Legal', links: [{ label: 'Privacy' }, { label: 'Terms' }, { label: 'Imprint' }] },
];

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
              {col.links.map(({ label, href }) => href ? (
                <Link key={label} href={href} className="inline-flex min-h-11 items-center text-small font-semibold text-ink md:min-h-8">{label}</Link>
              ) : (
                <span key={label} className="inline-flex min-h-11 flex-wrap items-center gap-x-2 text-small font-semibold text-ink-muted md:min-h-8">
                  {label}<span className="font-mono text-mono font-normal">Coming soon</span>
                </span>
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
