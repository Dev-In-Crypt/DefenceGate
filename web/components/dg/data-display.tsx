import { cn } from '@/lib/utils';
import { formatMoney } from '@/lib/format';
import { countryName, languageName } from '@/lib/taxonomy';
import type { Money } from '@/lib/types';

/** "EUR 25,000,000" in DM Mono. Missing amounts say so instead of showing 0. */
export function AmountDisplay({ money, size = 'md', className }: { money: Money | null; size?: 'md' | 'lg'; className?: string }) {
  if (!money) return <span className={cn('font-sans text-body text-ink-muted', className)}>Not available</span>;
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

/** Inset cell holding one fact. Used inside cards and detail pages. */
export function FactCell({ label, children, tone = 'default', className }: { label: string; children: React.ReactNode; tone?: 'default' | 'soon' | 'closed'; className?: string }) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-1 rounded-md p-4', tone === 'soon' ? 'bg-soon-bg' : 'bg-surface-inset', className)}>
      <dt className={cn('text-label', tone === 'soon' ? 'text-soon-fg' : 'text-ink-muted')}>{label}</dt>
      <dd className={cn('m-0 break-words font-mono text-mono-strong tabular-nums', tone === 'soon' ? 'text-soon-fg' : tone === 'closed' ? 'text-ink-muted' : 'text-ink')}>{children}</dd>
    </div>
  );
}
