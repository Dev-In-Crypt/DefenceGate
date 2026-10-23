import Link from 'next/link';
import { apartLines, sumLines, suspectLine, totalLine, VALUE_RULES, withoutValueLine, type ValueTotals } from '@/lib/value-totals';
import { formatDateUtc, formatMoney } from '@/lib/format';
import { Details } from './details';

/**
 * WP-81: the sum of one supplier's contract values, collapsed by default (a native disclosure: keyboard and print work without
 * script). `noun` is what the list counts ("contract", "notice"); `scope` says which period and sources the sum covers.
 * WP-89: the summary line carries the total ("Contract values: EUR 1,200,000 over 3 contracts"), so the closed block is not read as
 * empty; `rules={false}` leaves out the scope and the rules, for a list that states them once (the supplier report's winners).
 * WP-95: framework ceilings and estimates are listed apart (never added), and the largest contracts are named with their notices.
 */
export function ValueTotalsBlock({ values, noun, scope, className, rules = true }: {
  values: ValueTotals; noun: string; scope: string; className?: string; rules?: boolean;
}) {
  const lines = sumLines(values, noun);
  const apart = apartLines(values);
  const without = withoutValueLine(values, noun);
  const suspect = suspectLine(values, noun);
  const largest = values.largest ?? [];
  return (
    <Details summary={<span data-value-summary>Contract values: {totalLine(values, noun)}</span>} className={className}>
      <div data-value-totals className="flex flex-col gap-2">
        {lines.length > 0 ? (
          <ul className="m-0 flex list-none flex-col gap-0.5 p-0 text-ink">
            {lines.map((l) => <li key={l} className="tabular-nums" data-value-sum>{l}</li>)}
          </ul>
        ) : (
          <p className="m-0 text-ink">No value to sum.</p>
        )}
        {apart.map((l) => <p key={l} className="m-0 tabular-nums" data-value-apart>{l}.</p>)}
        {without && <p className="m-0" data-value-without>{without}</p>}
        {suspect && <p className="m-0" data-value-suspect>{suspect}</p>}
        {largest.length > 0 && (
          <div className="flex flex-col gap-1" data-largest>
            <p className="m-0 font-semibold text-ink">Largest contracts</p>
            <ol className="m-0 flex flex-col gap-1 pl-5">
              {largest.map((c) => (
                <li key={c.id} className="text-small">
                  <span className="font-mono tabular-nums">{formatMoney({ currency: c.currency, amount: Math.round(c.amount) })}</span>{' '}
                  <Link href={`/tenders/${c.slug}`}>{c.title}</Link>
                  <span className="text-ink-muted">{c.buyerName ? `, ${c.buyerName}` : ''}{c.publishedAt ? `, ${formatDateUtc(c.publishedAt)}` : ''}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
        {rules && <p className="m-0">{scope} {VALUE_RULES}</p>}
      </div>
    </Details>
  );
}
