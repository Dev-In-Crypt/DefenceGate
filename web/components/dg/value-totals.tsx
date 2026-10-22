import { sumLines, VALUE_RULES, withoutValueLine, type ValueTotals } from '@/lib/value-totals';
import { Details } from './details';

/**
 * WP-81: the sum of one supplier's contract values, collapsed by default (a native disclosure: keyboard and print work without
 * script). `noun` is what the list counts ("contract", "notice"); `scope` says which period and sources the sum covers.
 */
export function ValueTotalsBlock({ values, noun, scope, className }: { values: ValueTotals; noun: string; scope: string; className?: string }) {
  const lines = sumLines(values, noun);
  const without = withoutValueLine(values, noun);
  return (
    <Details summary="Contract values" className={className}>
      <div data-value-totals className="flex flex-col gap-2">
        {lines.length > 0 ? (
          <ul className="m-0 flex list-none flex-col gap-0.5 p-0 text-ink">
            {lines.map((l) => <li key={l} className="tabular-nums" data-value-sum>{l}</li>)}
          </ul>
        ) : (
          <p className="m-0 text-ink">No value to sum.</p>
        )}
        {without && <p className="m-0" data-value-without>{without}</p>}
        <p className="m-0">{scope} {VALUE_RULES}</p>
      </div>
    </Details>
  );
}
