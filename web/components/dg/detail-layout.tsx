import { cn } from '@/lib/utils';

export interface NavItem { id: string; label: string }

/**
 * The body of a record page (a call, a tender): the text in one column, and the record's own facts and actions in a
 * side column, as the EU Funding & Tenders portal and CORDIS lay them out. Slots, in the order they read on a phone:
 *
 *   top    the deadline, first on a phone (hidden from lg, where it sits at the head of `side`)
 *   nav    "On this page": a card of links on a phone, a sticky list from lg (in the side column; at the left from xl)
 *   facts  the key facts of the record (a card)
 *   main   the panels
 *   side   deadline, actions
 *
 * The placement is in globals.css (`.detail`); the DOM order is the phone order.
 */
export function DetailLayout({ top, nav, facts, side, sideLabel = 'Deadline and actions', children }: {
  top?: React.ReactNode; nav?: React.ReactNode; facts?: React.ReactNode; side: React.ReactNode; sideLabel?: string; children: React.ReactNode;
}) {
  return (
    <div className={cn('detail', nav && 'detail--nav')}>
      {top && <div className="d-top rounded-lg border border-edge bg-surface p-3 sm:p-4">{top}</div>}
      {nav && <div className="d-nav">{nav}</div>}
      {facts && <div className="d-facts">{facts}</div>}
      <div className="d-main flex min-w-0 flex-col gap-6">{children}</div>
      <aside aria-label={sideLabel} className="d-side">{side}</aside>
    </div>
  );
}

/**
 * "On this page": links to the parts of a long page. A card of wrapped links on a phone; from lg a plain vertical list with a
 * rule at its left (the placement and the stickiness are the layout's).
 */
export function SectionNav({ items }: { items: NavItem[] }) {
  return (
    <nav aria-label="On this page" className="flex flex-col gap-1 rounded-lg border border-edge bg-surface px-5 py-3 sm:px-6 lg:rounded-none lg:border-0 lg:bg-transparent lg:p-0">
      <p className="m-0 text-label text-ink">On this page</p>
      <ul className="m-0 flex list-none flex-wrap gap-x-5 p-0 lg:flex-col lg:gap-0 lg:border-l lg:border-line">
        {items.map((t) => (
          <li key={t.id}>
            <a href={`#${t.id}`} className="inline-flex min-h-12 items-center text-small font-semibold lg:-ml-px lg:min-h-9 lg:w-full lg:border-l-2 lg:border-transparent lg:pl-3 lg:hover:border-ink">{t.label}</a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
