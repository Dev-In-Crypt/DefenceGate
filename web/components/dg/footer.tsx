import Link from 'next/link';
import { cn } from '@/lib/utils';
import { Logo } from './logo';
import { CARD_SURFACE } from './card';
import { FOOTER_GROUPS, LEGAL_LINKS as LEGAL } from '@/lib/nav';
import { getHealth, lastDataUpdate } from '@/lib/api';
import { formatDateTimeUtc } from '@/lib/format';

/** A footer link: 44 px high on a phone (a tap target), 32 px from lg, where the links stand in columns, on one line each. */
const LINK = 'inline-flex min-h-11 items-center text-small font-semibold text-ink lg:min-h-8 lg:whitespace-nowrap';

/**
 * One card: the brand (a row of its own below xl, a column from xl), six link groups side by side from lg (two columns on a
 * phone), then the legal line and the disclaimer at the left and the source line (with the Atom feed) at the right.
 */
export async function Footer() {
  const health = await getHealth();
  return (
    <footer className="page pb-4 print:hidden">
      <div className={cn(CARD_SURFACE, 'flex flex-col gap-4 p-5 sm:px-6')}>
        {/* From lg every group is as wide as its longest label: nothing wraps and nothing overlaps (re-audit NEW-9). */}
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-3 lg:grid-cols-[repeat(6,auto)] lg:justify-between lg:gap-x-6 xl:grid-cols-[minmax(0,1fr)_repeat(6,auto)]">
          <div className="col-span-full flex flex-col items-start gap-2 xl:col-span-1">
            <Logo href="/" />
            <p className="m-0 max-w-[30ch] text-small text-ink-muted">Defence and dual-use tenders and funding calls, in one place.</p>
          </div>
          {FOOTER_GROUPS.map((col) => (
            <nav key={col.title} aria-label={col.title} className="flex min-w-0 flex-col">
              <p className="m-0 mb-1 text-label text-ink-muted">{col.title}</p>
              {col.links.map(({ label, href }) => (
                <Link key={href} href={href} className={cn(LINK, 'flex')}>{label}</Link>
              ))}
            </nav>
          ))}
        </div>
        <div className="grid gap-3 border-t border-line pt-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end lg:gap-8">
          <div className="flex flex-col gap-1">
            <nav aria-label="Legal" className="flex flex-wrap gap-x-5">
              {LEGAL.map(({ label, href }) => <Link key={href} href={href} className={LINK}>{label}</Link>)}
            </nav>
            <p className="m-0 text-small text-ink-muted">
              DefenceGate is an information service. It is not an official source and is not affiliated with the European Union, TED or any government. The original publication is authoritative: check it before you act. Nothing here is legal or professional advice.
            </p>
          </div>
          <div className="flex flex-col gap-0.5 font-sans text-small text-ink-muted lg:text-right">
            {/* WP-87: the newest run of any source; each list names the run of its own sources, so this one says it is "any".
                WP-131: a run that brought data (lib/api.ts lastDataUpdate), the same time as the home page's "Last update" */}
            {/* WP-130: a link in running text is underlined (`run-text`): its colour was 1.03:1 from the text around it */}
            <span className="run-text">{health.sources.length} sources · <Link href="/data">Last run that brought data (any source)</Link> {formatDateTimeUtc(lastDataUpdate(health))}</span>
            <span>All dates in UTC · <a href="/changes.atom" className="inline-flex min-h-11 items-center font-semibold text-ink lg:min-h-8">Atom feed of changes</a></span>
          </div>
        </div>
      </div>
    </footer>
  );
}
