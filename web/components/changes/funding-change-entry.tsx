import Link from 'next/link';
import { displayName } from '@/lib/display-name';
import { formatDateTimeUtc, funderLine } from '@/lib/format';
import { PROGRAMMES } from '@/lib/taxonomy';
import type { FundingChange } from '@/lib/types';
import { Tag } from '../dg/tag';
import { describeChange } from '../dg/version-timeline';

/** One funding call that is new in the window, or whose closing or opening date the source moved. */
export function FundingChangeEntry({ change }: { change: FundingChange }) {
  const c = change.call;
  const isNew = change.kind === 'call-new';
  return (
    <article className="flex flex-col gap-3 rounded-lg bg-surface p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Tag kind="programme">{isNew ? 'New call' : 'Date moved'}</Tag>
        <Tag>{PROGRAMMES[c.programme].label}</Tag>
        <time dateTime={change.detectedAt} className="ml-auto font-mono text-mono text-ink-muted">Seen {formatDateTimeUtc(change.detectedAt)}</time>
      </div>
      <h3 className="m-0 break-words text-[20px] font-bold leading-[28px] tracking-[-0.4px]">
        <Link href={`/funding/${c.slug}`}>{displayName(c.title)}</Link>
      </h3>
      <p className="m-0 text-small font-semibold">{funderLine(c)}</p>
      {isNew ? (
        <p className="m-0 text-body text-ink-muted">First collected by DefenceGate on this day.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {change.changes.map((l, i) => <li key={`${l.field}-${i}`} className="min-w-0 text-body">{describeChange(l)}</li>)}
        </ul>
      )}
    </article>
  );
}
