import { cn } from '@/lib/utils';
import { ScrollBox } from './scroll-box';

/**
 * A table that stays readable at 375 px: it keeps its own width (`minWidth`, default 480 px) and scrolls sideways inside a
 * labelled, keyboard-reachable box (with the "more to the right" line of ScrollBox) instead of squeezing its cells into
 * columns of 60 px. One density for every table: 14 px text, 10 px above and below a row, a hairline under each row,
 * a tinted header row. Put `<thead>` and `<tbody>` inside; the caption is for screen readers.
 */
export function DataTable({ label, minWidth = 480, className, children }: {
  label: string; minWidth?: number; className?: string; children: React.ReactNode;
}) {
  return (
    <ScrollBox label={label}>
      <table style={{ minWidth }} className={cn(
        'w-full border-collapse text-left text-small',
        '[&_th]:px-3 [&_th]:py-2.5 [&_th]:align-bottom [&_th]:font-semibold [&_thead_th]:bg-surface-inset [&_thead_th]:first:rounded-tl-md [&_thead_th]:last:rounded-tr-md',
        '[&_td]:px-3 [&_td]:py-2.5 [&_td]:align-top [&_tbody_tr]:border-b [&_tbody_tr]:border-line [&_tbody_tr:last-child]:border-0',
        className)}>
        <caption className="sr-only">{label}</caption>
        {children}
      </table>
    </ScrollBox>
  );
}
