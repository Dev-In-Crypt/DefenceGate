import { cn } from '@/lib/utils';

/**
 * A grid of cards that fills its row: `repeat(auto-fit, minmax(min(100%, <min>px), 1fr))`. A lone card takes the whole
 * row (it never sits in the left half of a two-column grid), two cards share it, and the number of columns follows the
 * width, not a breakpoint. Gap 16 px, 24 px from lg.
 *
 *   <AutoGrid as="ul" min={320}>{items.map((i) => <Card as="li" key=...>)}</AutoGrid>
 *
 * `min` is the narrowest a card may get (default 320; a card that holds a paragraph should not go below it).
 */
export function AutoGrid({ as = 'div', min = 320, className, children }: {
  as?: 'div' | 'ul' | 'ol'; min?: number; className?: string; children: React.ReactNode;
}) {
  const As = as;
  return (
    <As className={cn('auto-grid m-0 list-none p-0', className)} style={{ '--auto-min': `${min}px` } as React.CSSProperties}>
      {children}
    </As>
  );
}
