import { cn } from '@/lib/utils';

/**
 * Label-above-value facts in a hairline grid (the layout of the EU Funding & Tenders "general information" block):
 * at most 3 columns, fewer when the box is narrow, a 1px `--line` rule above every row (not above the first row of a grid inside a card), no tinted cells. Replaces
 * hand-written `dl` grids of equal two-column cells, where a long value wrapped into four short lines.
 *
 *   <FactsGrid items={[{ label: 'Cost', value: 'Free' }, { label: 'Time', value: 'Up to 14 working days', wide: true }]} />
 *   <FactsGrid><Fact label="Deadline" mono>2026-11-04</Fact>...</FactsGrid>
 *
 * `wide` makes one fact span the whole row (a long sentence). `mono` sets ids, dates and amounts in DM Mono.
 */
export interface FactItem { label: React.ReactNode; value: React.ReactNode; mono?: boolean; wide?: boolean }

export function Fact({ label, children, mono = false, wide = false, className }: {
  label: React.ReactNode; children: React.ReactNode; mono?: boolean; wide?: boolean; className?: string;
}) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-1 border-t border-line py-3', wide && 'col-span-full', className)}>
      <dt className="text-label text-ink-muted">{label}</dt>
      <dd className={cn('m-0 break-words', mono ? 'font-mono text-mono-strong tabular-nums' : 'text-body')}>{children}</dd>
    </div>
  );
}

export function FactsGrid({ items, children, className }: { items?: FactItem[]; children?: React.ReactNode; className?: string }) {
  return (
    // `border-b-0` is how a page says "inside a card" (no closing rule): that grid also loses the top rule of its whole first row.
    <dl className={cn('facts-grid m-0 border-b border-line', className?.includes('border-b-0') && 'facts-grid--flush', className)}>
      {items?.map((f, i) => <Fact key={i} label={f.label} mono={f.mono} wide={f.wide}>{f.value}</Fact>)}
      {children}
    </dl>
  );
}
