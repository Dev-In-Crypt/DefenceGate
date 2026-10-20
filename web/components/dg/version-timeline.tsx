import { formatChangeValue } from '@/lib/change-format';
import { formatDateUtc } from '@/lib/format';
import type { FieldChange, TenderVersion } from '@/lib/types';
import { cn } from '@/lib/utils';

/** One field-level change as a sentence. Also used by the account dashboard. Values are said for a person. */
export function describeChange(c: FieldChange): React.ReactNode {
  const v = (s: string) => <span className="break-words font-mono text-mono-strong tabular-nums">{s}</span>;
  const before = formatChangeValue(c.field, c.before);
  const after = formatChangeValue(c.field, c.after);
  if (before && after) return <>{c.label} changed from {v(before)} to {v(after)}</>;
  if (after) return <>{c.label} added: {v(after)}</>;
  return <>{c.label} removed{before ? <>: {v(before)}</> : null}</>;
}

/**
 * The number a reader counts by: the API's `sequence` (1 = first seen), or, from a build that does not send it,
 * the place in the list. The archive's own row number (`version`) has gaps and is not shown.
 */
export function sequenceOf(versions: TenderVersion[], index: number): number {
  return versions[index].sequence ?? versions.length - index;
}

/** Newest first. Each version lists field-level changes; first entry is filled. */
export function VersionTimeline({ versions }: { versions: TenderVersion[] }) {
  return (
    <ol className="m-0 flex list-none flex-col p-0">
      {versions.map((ver, i) => {
        const last = i === versions.length - 1;
        const seq = sequenceOf(versions, i);
        return (
          <li key={ver.version} className="grid grid-cols-[16px_1fr] gap-x-4">
            <div className="relative flex justify-center">
              <span className={cn('relative z-10 mt-1.5 size-2.5 rounded-pill border-2', i === 0 ? 'border-ink bg-ink' : 'border-line bg-surface')} />
              {!last && <span className="absolute -bottom-1.5 top-4 w-0.5 bg-line" />}
            </div>
            <div className={cn('flex min-w-0 flex-col gap-0.5', !last && 'pb-5')}>
              <span className="font-mono text-mono text-ink-muted">
                Version {seq} · {ver.historic ? 'Read by DefenceGate on' : ver.correction ? 'Corrected by DefenceGate on' : 'Detected'} <time dateTime={ver.detectedAt}>{formatDateUtc(ver.detectedAt)}</time>
              </span>
              {ver.historic && (
                <span className="text-small text-ink-muted">
                  We read this from the source&rsquo;s older notices when we loaded its history: the change itself was published before this date, and it is not counted as a new change.
                </span>
              )}
              {ver.correction && (
                <span className="text-small text-ink-muted">
                  We read the notice we already held again with a corrected reading: the publisher did not change it on this date, and it is not counted as a change.
                </span>
              )}
              {ver.changes.length === 0 ? (
                <span className="text-body">First observed by DefenceGate</span>
              ) : (
                <ul className="m-0 flex list-none flex-col gap-1 p-0">
                  {ver.changes.map((c, n) => <li key={`${c.field}-${n}`} className="min-w-0 text-body">{describeChange(c)}</li>)}
                </ul>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
