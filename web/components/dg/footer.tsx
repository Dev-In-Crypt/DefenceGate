import Link from 'next/link';
import { cn } from '@/lib/utils';
import { Logo } from './logo';
import { CARD_SURFACE } from './card';
import { getHealth, lastDataUpdate } from '@/lib/api';
import { formatDateTimeUtc } from '@/lib/format';

/** `long`: eight links, set in two columns except from lg to xl (see LONG); the short groups are one column. */
const COLUMNS: { title: string; long?: boolean; links: { label: string; href: string }[] }[] = [
  // The groups are the header's (components/dg/header-bar.tsx): a destination the header lists is under the same name here.
  // "Directory" holds the header's top-level pages and the lists only the footer carries.
  { title: 'Directory', long: true, links: [
    { label: 'Funding calls', href: '/funding' }, { label: 'Closing soon', href: '/funding?status=closing-soon' },
    { label: 'Tenders', href: '/tenders' }, { label: 'Buyers', href: '/buyers' },
    { label: 'Deadline calendar', href: '/calendar' }, { label: 'What changed', href: '/changes' },
    { label: 'Market', href: '/market' }, { label: 'Pricing', href: '/pricing' },
  ] },
  { title: 'Network', links: [
    { label: 'Organisations', href: '/organisations' }, { label: 'Suppliers', href: '/suppliers' },
    { label: 'Ukraine partners', href: '/networks/ukraine-partners' }, { label: 'Consortium gaps', href: '/networks/consortium-gaps' },
  ] },
  { title: 'Readiness', links: [
    { label: 'Readiness check', href: '/readiness' }, { label: 'Supplier profile', href: '/readiness/supplier' }, { label: 'Spain automotive', href: '/readiness/spain-automotive' },
    { label: 'Requirements', href: '/requirements' },
    { label: 'Regulatory tracker', href: '/regulation' },
  ] },
  { title: 'Data', long: true, links: [
    { label: 'Source status', href: '/data' }, { label: 'Methodology', href: '/methodology' },
    { label: 'Weekly digest', href: '/digest' }, { label: 'Where the data runs', href: '/data/sovereignty' },
    { label: 'CPV finder', href: '/cpv' }, { label: 'Glossary', href: '/glossary' },
    { label: 'Opportunity pack', href: '/pack' }, { label: 'Alerts (not open yet)', href: '/alerts' },
  ] },
  { title: 'About and legal', links: [
    { label: 'About', href: '/about' }, { label: 'Privacy', href: '/privacy' },
    { label: 'Terms', href: '/terms' }, { label: 'Imprint', href: '/imprint' },
  ] },
];

/** A footer link: 36 px high on a phone, 32 px from lg (where the links stand in columns, on one line each). Secondary targets: at least 32. */
const LINK = 'inline-flex min-h-9 items-center text-small font-semibold text-ink lg:min-h-8 lg:whitespace-nowrap';
/**
 * The inner columns of a long group: two, as wide as their longest label, on a phone and from xl; one from lg to xl, where two
 * would not fit beside the other groups (re-audit NEW-9: at 1024 to 1279 px the labels wrapped and the brand ran into them).
 */
const LONG = 'grid grid-flow-col grid-rows-4 grid-cols-[auto_auto] justify-start gap-x-4 lg:grid-flow-row lg:grid-rows-none lg:grid-cols-1 xl:grid-flow-col xl:grid-rows-4 xl:grid-cols-[auto_auto] xl:gap-x-6';

/**
 * One compact card (about 300 px from xl, taller from lg to xl): the brand, five link groups side by side (the two long ones in two
 * columns), then the legal line at the left and the source line (with the Atom feed) at the right. The same links as before; the "source status"
 * box said what the Data column's first link says.
 */
export async function Footer() {
  const health = await getHealth();
  return (
    <footer className="page pb-4 print:hidden">
      <div className={cn(CARD_SURFACE, 'flex flex-col gap-4 p-5 sm:px-6')}>
        {/* From lg every group is as wide as its longest label and the brand takes the rest: nothing wraps and nothing overlaps. */}
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 lg:grid-cols-[minmax(0,1fr)_repeat(5,auto)] lg:gap-x-6">
          <div className="col-span-2 flex flex-col items-start gap-2 sm:col-span-1">
            <Logo href="/" />
            <p className="m-0 max-w-[30ch] text-small text-ink-muted">Defence and dual-use tenders and funding calls, in one place.</p>
          </div>
          {COLUMNS.map((col) => (
            <nav key={col.title} aria-label={col.title} className={cn('flex min-w-0 flex-col', col.long ? 'col-span-2 sm:col-span-1' : 'max-lg:order-3', col.title === 'Directory' && 'max-lg:order-1', col.title === 'Data' && 'max-lg:order-2')}>
              <p className="m-0 mb-1 text-label text-ink-muted">{col.title}</p>
              <div className={cn(col.long && LONG)}>
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
