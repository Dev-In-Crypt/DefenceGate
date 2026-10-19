import Link from 'next/link';
import { cn } from '@/lib/utils';
import { Logo } from './logo';
import { CARD_SURFACE } from './card';
import { getHealth, lastDataUpdate } from '@/lib/api';
import { formatDateTimeUtc } from '@/lib/format';

/** `long`: nine links, set in two columns at every width; the short groups are one column. */
const COLUMNS: { title: string; long?: boolean; links: { label: string; href: string }[] }[] = [
  { title: 'Directory', long: true, links: [
    { label: 'Funding calls', href: '/funding' }, { label: 'Closing soon', href: '/funding?status=closing-soon' },
    { label: 'Tenders', href: '/tenders' }, { label: 'Buyers', href: '/buyers' },
    { label: 'Organisations', href: '/organisations' }, { label: 'Suppliers', href: '/suppliers' },
    { label: 'Deadline calendar', href: '/calendar' }, { label: 'What changed', href: '/changes' },
    { label: 'Weekly digest', href: '/digest' },
  ] },
  { title: 'Readiness', links: [
    { label: 'Readiness check', href: '/readiness' }, { label: 'Requirements', href: '/requirements' },
    { label: 'Regulatory tracker', href: '/regulation' }, { label: 'Ukraine partners', href: '/networks/ukraine-partners' },
  ] },
  { title: 'Data', long: true, links: [
    { label: 'Source status', href: '/data' }, { label: 'Methodology', href: '/methodology' }, { label: 'Data sovereignty', href: '/data/sovereignty' },
    { label: 'Market overview', href: '/market' }, { label: 'CPV finder', href: '/cpv' }, { label: 'Glossary', href: '/glossary' },
    { label: 'Alerts (not open yet)', href: '/alerts' }, { label: 'Opportunity pack', href: '/pack' },
    { label: 'Pricing', href: '/pricing' },
  ] },
  { title: 'About and legal', links: [
    { label: 'About', href: '/about' }, { label: 'Privacy', href: '/privacy' },
    { label: 'Terms', href: '/terms' }, { label: 'Imprint', href: '/imprint' },
  ] },
];

/** A footer link: 36 px high on a phone, 32 px from lg (where the links stand in columns). Secondary targets: at least 32. */
const LINK = 'inline-flex min-h-9 items-center text-small font-semibold text-ink lg:min-h-8';

/**
 * One compact card (about 300 px from lg): the brand, four link groups side by side (the two long ones in two
 * columns), then the legal line at the left and the source line (with the Atom feed) at the right. The same links as before; the "source status"
 * box said what the Data column's first link says.
 */
export async function Footer() {
  const health = await getHealth();
  return (
    <footer className="page pb-4 print:hidden">
      <div className={cn(CARD_SURFACE, 'flex flex-col gap-4 p-5 sm:px-6')}>
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,2fr)_minmax(0,1fr)_minmax(0,2fr)_minmax(0,1fr)]">
          <div className="col-span-2 flex flex-col items-start gap-2 sm:col-span-1">
            <Logo href="/" />
            <p className="m-0 max-w-[30ch] text-small text-ink-muted">Defence and dual-use tenders and funding calls, in one place.</p>
          </div>
          {COLUMNS.map((col) => (
            <nav key={col.title} aria-label={col.title} className={cn('flex min-w-0 flex-col', col.long ? 'col-span-2 sm:col-span-1' : 'max-lg:order-3', col.title === 'Directory' && 'max-lg:order-1', col.title === 'Data' && 'max-lg:order-2')}>
              <p className="m-0 mb-1 text-label text-ink-muted">{col.title}</p>
              <div className={cn('gap-x-6 [&>a]:break-inside-avoid', col.long && '[column-count:2]')}>
                {col.links.map(({ label, href }) => (
                  <Link key={label} href={href} className={cn(LINK, 'flex')}>{label}</Link>
                ))}
              </div>
            </nav>
          ))}
        </div>
        <div className="grid gap-3 border-t border-line pt-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end lg:gap-8">
          <p className="m-0 max-w-3xl text-small text-ink-muted">
            DefenceGate is an information service. It is not an official source and is not affiliated with the European Union, TED or any government. The original publication is authoritative: check it before you act. Nothing here is legal or professional advice.
          </p>
          <div className="flex flex-col gap-0.5 font-sans text-small text-ink-muted lg:text-right">
            <span>{health.sources.length} sources · Last collection run {formatDateTimeUtc(lastDataUpdate(health))}</span>
            <span>All dates in UTC · <a href="/changes.atom" className="inline-flex min-h-9 items-center font-semibold text-ink lg:min-h-8">Atom feed of changes</a></span>
          </div>
        </div>
      </div>
    </footer>
  );
}
