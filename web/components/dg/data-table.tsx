import { cn } from '@/lib/utils';
import { ScrollBox } from './scroll-box';

/**
 * A table that stays readable at 375 px: it keeps its own width (`minWidth`, default 480 px) and scrolls sideways inside a
 * labelled, keyboard-reachable box (with the "more to the right" line of ScrollBox) instead of squeezing its cells into
 * columns of 60 px. One density for every table: 14 px text, 10 px above and below a row, a hairline under each row,
 * a tinted header row, a row tinted under the pointer (brand book). Every body cell, a row header too, starts at the top of its row. Put `<thead>` and `<tbody>` inside; the caption is for screen readers.
 */
export function DataTable({ label, caption, minWidth = 480, className, children }: {
  /** The name of the scroll region. */
  label: string;
  /** The name of the table for a screen reader (default: the label). A table keeps the name its tests and readers know it by. */
  caption?: string; minWidth?: number; className?: string; children: React.ReactNode;
}) {
  return (
    <ScrollBox label={label}>
      <table style={{ minWidth }} className={cn(
        'w-full border-collapse text-left text-small',
        // WP-175 (D-1, F-2, F07): a row's header cell is top-aligned like its figures (bottom-aligned, a wrapped name sat beside the
        // next row's numbers); only the column headers sit on the bottom line. The corners are the header row's first and last cell
        // (`[&_thead_th]:first:` rounded every header cell: the variant read `:first-child` of the table)
        '[&_th]:px-3 [&_th]:py-2.5 [&_th]:font-semibold [&_thead_th]:align-bottom [&_tbody_th]:align-top [&_thead_th]:bg-surface-inset [&_thead_th:first-child]:rounded-tl-md [&_thead_th:last-child]:rounded-tr-md',
        '[&_td]:px-3 [&_td]:py-2.5 [&_td]:align-top [&_tbody_tr]:border-b [&_tbody_tr]:border-line [&_tbody_tr:last-child]:border-0 [&_tbody_tr]:transition-colors [&_tbody_tr:hover]:bg-surface-inset',
        className)}>
        <caption className="sr-only">{caption ?? label}</caption>
        {children}
      </table>
    </ScrollBox>
  );
}
