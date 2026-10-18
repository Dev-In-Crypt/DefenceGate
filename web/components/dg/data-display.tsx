import { cn } from '@/lib/utils';
import { formatMoney, isPlaceholderAmount } from '@/lib/format';
import { countryName, languageName } from '@/lib/taxonomy';
import type { Money } from '@/lib/types';

/** "EUR 25,000,000" in DM Mono. A missing amount, or a placeholder (0, 0.01, 1), says so instead of showing it. */
export function AmountDisplay({ money, size = 'md', className }: { money: Money | null; size?: 'md' | 'lg'; className?: string }) {
  if (!money || isPlaceholderAmount(money.amount)) return <span className={cn('font-sans text-body text-ink-muted', className)}>Not available</span>;
  return (
    <data value={`${money.amount} ${money.currency}`} className={cn('font-mono tabular-nums', size === 'lg' ? 'text-figure' : 'text-mono-strong', className)}>
      {formatMoney(money)}
    </data>
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
 * A fact of a list card. Under sm: label at the left, value at the right, a hairline between rows. From sm: three columns, label above
 * value. From xl (the card has an aside column): rows again. Only the soon tone gets a tint, so a deadline that is close stands out.
 * Put them in a <dl className={LIST_FACTS}>.
 */
export const LIST_FACTS = 'm-0 grid min-w-0 content-start sm:grid-cols-3 sm:gap-x-4 sm:border-t sm:border-line sm:pt-3 xl:grid-cols-1 xl:gap-x-0 xl:border-l xl:border-t-0 xl:pl-6 xl:pt-0';
export function ListFact({ label, children, tone = 'default' }: { label: string; children: React.ReactNode; tone?: 'default' | 'soon' | 'closed' }) {
  return (
    <div className={cn(
      'grid min-w-0 grid-cols-[6rem_minmax(0,1fr)] items-baseline gap-x-3 border-t border-line py-2 first:border-t-0 sm:block sm:border-t-0 sm:py-0 xl:grid xl:border-t xl:py-2 xl:first:border-t-0',
      tone === 'soon' && 'rounded-md bg-soon-bg px-3 sm:py-2 xl:my-0.5 xl:border-t-0')}>
      <dt className={cn('text-label', tone === 'soon' ? 'text-soon-fg' : 'text-ink-muted')}>{label}</dt>
      <dd className={cn('m-0 break-words font-mono text-mono font-medium tabular-nums', tone === 'soon' ? 'text-soon-fg' : tone === 'closed' ? 'text-ink-muted' : 'text-ink')}>{children}</dd>
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
    <div className={cn('flex min-w-0 flex-col gap-1 py-3', tone === 'soon' ? 'rounded-md bg-soon-bg px-3' : 'border-t border-line', className)}>
      <dt className={cn('text-label', tone === 'soon' ? 'text-soon-fg' : 'text-ink-muted')}>{label}</dt>
      <dd className={cn('m-0 break-words font-mono text-mono-strong tabular-nums', tone === 'soon' ? 'text-soon-fg' : tone === 'closed' ? 'text-ink-muted' : 'text-ink')}>{children}</dd>
    </div>
  );
}
