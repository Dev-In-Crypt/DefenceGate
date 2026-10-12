import { formatDateUtc } from '@/lib/format';
import type { FieldChange, OpportunityVersion } from '@/lib/types';
import { cn } from '@/lib/utils';

function describe(c: FieldChange): React.ReactNode {
  const v = (s: string) => <span className="font-mono text-mono-strong tabular-nums">{s}</span>;
  if (c.before && c.after) return <>{c.label} changed from {v(c.before)} to {v(c.after)}</>;
  if (c.after) return <>{c.label} added: {v(c.after)}</>;
  return <>{c.label} removed{c.before ? <>: {v(c.before)}</> : null}</>;
}

/** Newest first. Each version lists field-level changes; first entry is filled. */
export function VersionTimeline({ versions }: { versions: OpportunityVersion[] }) {
  return (
    <ol className="m-0 flex list-none flex-col p-0">
      {versions.map((ver, i) => {
        const last = i === versions.length - 1;
        return (
          <li key={ver.version} className="grid grid-cols-[16px_1fr] gap-x-4">
            <div className="relative flex justify-center">
              <span className={cn('relative z-10 mt-1.5 size-2.5 rounded-pill border-2', i === 0 ? 'border-ink bg-ink' : 'border-line bg-surface')} />
              {!last && <span className="absolute -bottom-1.5 top-4 w-0.5 bg-line" />}
            </div>
            <div className={cn('flex flex-col gap-0.5', !last && 'pb-5')}>
              <span className="font-mono text-mono text-ink-muted">
                Detected <time dateTime={ver.detectedAt}>{formatDateUtc(ver.detectedAt)}</time> · v{ver.version}
              </span>
              {ver.changes.length === 0 ? (
                <span className="text-body">First published</span>
              ) : (
                <ul className="m-0 flex list-none flex-col gap-1 p-0">
                  {ver.changes.map((c) => <li key={c.field} className="text-body">{describe(c)}</li>)}
                </ul>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
