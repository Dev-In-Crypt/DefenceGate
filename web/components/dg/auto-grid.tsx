import { cn } from '@/lib/utils';

/**
 * A grid of cards that fills its row: `repeat(auto-fit, minmax(min(100%, <min>px), 1fr))`. A lone card takes the whole
 * row (it never sits in the left half of a two-column grid), two cards share it, and the number of columns follows the
 * width, not a breakpoint. Gap 16 px, 24 px from lg.
 *
 *   <AutoGrid as="ul" min={320}>{items.map((i) => <Card as="li" key=...>)}</AutoGrid>
 *
 * `min` is the narrowest a card may get (default 320; a card that holds a paragraph should not go below it).
 * `fill`: a row that is not full spreads its cards over the row (5 cards at 3 columns are 3 + 2, the two share the row)
 * instead of leaving the empty cells of a grid. Cards of one row have one height; rows may differ in column width.
 */
export function AutoGrid({ as = 'div', min = 320, fill = false, className, children, 'aria-label': label }: {
  as?: 'div' | 'ul' | 'ol' | 'dl'; min?: number; fill?: boolean; className?: string; children: React.ReactNode; 'aria-label'?: string;
}) {
  const As = as;
  return (
    <As aria-label={label} className={cn(fill ? 'auto-fill' : 'auto-grid', 'm-0 list-none p-0', className)} style={{ '--auto-min': `${min}px` } as React.CSSProperties}>
      {children}
    </As>
  );
}
