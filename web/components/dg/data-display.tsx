import { cn } from '@/lib/utils';
import { formatMoney, isPlaceholderAmount } from '@/lib/format';
import { countryName, languageName } from '@/lib/taxonomy';
import type { BudgetNote, Money } from '@/lib/types';

/** "EUR 25,000,000" in DM Mono. A missing amount, or a placeholder (0, 0.01, 1), says so instead of showing it. */
export function AmountDisplay({ money, size = 'md', className }: { money: Money | null; size?: 'md' | 'lg'; className?: string }) {
  if (!money || isPlaceholderAmount(money.amount)) return <span className={cn('font-sans text-body text-ink-muted', className)}>Not available</span>;
  return (
    <data value={`${money.amount} ${money.currency}`} className={cn('font-mono tabular-nums', size === 'lg' ? 'text-figure' : 'text-mono-strong', className)}>
      {formatMoney(money)}
    </data>
  );
}

/**
 * A call's budget. With no figure it says why, from the data we hold (`budgetNote`): the short line on a card, the full
 * sentence on the call page (`long`). A per-project ceiling the source states is shown as that, never as the budget.
 */
export function BudgetDisplay({ money, note, size = 'md', long = false, className }: {
  money: Money | null; note?: BudgetNote | null; size?: 'md' | 'lg'; long?: boolean; className?: string;
}) {
  if (money && !isPlaceholderAmount(money.amount)) return <AmountDisplay money={money} size={size} className={className} />;
  if (!note) return <AmountDisplay money={null} className={className} />;
  return (
    <>
      <span className={cn('font-sans text-body text-ink-muted', className)}>{note.short}</span>
      {note.perProject && !isPlaceholderAmount(note.perProject.amount) && (
        <div className="mt-1 font-sans text-small font-normal text-ink-muted">
          Ceiling per project: <AmountDisplay money={note.perProject} className="text-mono" />
        </div>
      )}
      {long && <div className="mt-1 font-sans text-small font-normal text-ink-muted">{note.text}</div>}
    </>
  );
}

/** Two-letter code + name: "PL Poland". Never a flag alone. Any code we have a name for (funder or audience country). */
export function CountryLabel({ code, className }: { code: string; className?: string }) {
  const name = countryName(code);
  return (
    <span className={cn('inline-flex items-baseline gap-2', className)}>
      <abbr title={name} className="font-mono text-mono-strong no-underline">{code}</abbr>
      <span>{name}</span>
    </span>
  );
}

/** Small mono label for a title's language: "Original language, Polish" or "Original title, Swedish". */
export function LangLabel({ kind, code, className }: { kind: 'language' | 'title'; code: string | null | undefined; className?: string }) {
  const name = code ? languageName(code) : null;
  return (
    <span className={cn('font-mono text-mono text-ink-muted', className)}>
      {kind === 'language' ? 'Original language' : 'Original title'}{name ? `, ${name}` : ''}
    </span>
  );
}

/**
 * A fact of a list card (the brand book's FactCell): an inset cell, padding 16, label above a mono value, in a grid of as many 160 px
 * columns as fit, 12 px apart. The soon tone is tinted, so a deadline that is close stands out.
 * Put them in a <dl className={LIST_FACTS}>.
 */
export const LIST_FACTS = 'm-0 grid min-w-0 grid-cols-[repeat(auto-fit,minmax(min(100%,160px),1fr))] gap-3';
export function ListFact({ label, children, tone = 'default' }: { label: string; children: React.ReactNode; tone?: 'default' | 'soon' | 'closed' }) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-1 rounded-md p-4', tone === 'soon' ? 'bg-soon-bg' : 'bg-surface-inset')}>
      <dt className={cn('text-label', tone === 'soon' ? 'text-soon-fg' : 'text-ink-muted')}>{label}</dt>
      <dd className={cn('m-0 break-words font-mono text-mono-strong tabular-nums', tone === 'soon' ? 'text-soon-fg' : tone === 'closed' ? 'text-ink-muted' : 'text-ink')}>{children}</dd>
    </div>
  );
}

/**
 * One fact of a detail page or a small card: label above value, a hairline above (the FactsGrid look; put cells in a
 * <dl className="facts-grid m-0 border-b border-line">). The value is mono by default; wrap text in <span className="font-sans">.
 * Only the soon tone is tinted, so a close deadline stands out and nothing else looks like a box.
 */
export function FactCell({ label, children, tone = 'default', className }: { label: string; children: React.ReactNode; tone?: 'default' | 'soon' | 'closed'; className?: string }) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-1 py-3', tone === 'soon' ? 'mb-4 mt-4 rounded-md bg-soon-bg px-3 first:mt-0' : 'border-t border-line', className)}>
      <dt className={cn('text-label', tone === 'soon' ? 'text-soon-fg' : 'text-ink-muted')}>{label}</dt>
      <dd className={cn('m-0 break-words font-mono text-mono-strong tabular-nums', tone === 'soon' ? 'text-soon-fg' : tone === 'closed' ? 'text-ink-muted' : 'text-ink')}>{children}</dd>
    </div>
  );
}
