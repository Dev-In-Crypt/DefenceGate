import Link from 'next/link';
import { displayName } from '@/lib/display-name';
import { formatDateTimeUtc, funderLine } from '@/lib/format';
import { PROGRAMMES, isNonEnglish } from '@/lib/taxonomy';
import type { FundingChange } from '@/lib/types';
import { Card } from '../dg/card';
import { Tag } from '../dg/tag';
import { FitBadge } from '../funding/fit-badge';
import { describeChange } from '../dg/version-timeline';
import { FIRST_COLLECTED } from './change-entry';

/** One funding call that is new in the window, or whose closing or opening date the source moved. */
export function FundingChangeEntry({ change }: { change: FundingChange }) {
  const c = change.call;
  const isNew = change.kind === 'call-new';
  return (
    <Card as="article" className="h-full gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Tag kind="programme">{isNew ? 'New call' : 'Date moved'}</Tag>
        <Tag>{PROGRAMMES[c.programme].label}</Tag>
        <FitBadge id={c.id} />
        <time dateTime={change.detectedAt} className="ml-auto font-mono text-mono text-ink-muted">Seen {formatDateTimeUtc(change.detectedAt)}</time>
      </div>
      <h3 className="m-0 break-words text-h3">
        <Link href={`/funding/${c.slug}`} lang={isNonEnglish(c.titleLanguage) ? c.titleLanguage : undefined}>{displayName(c.title)}</Link>
      </h3>
      <p className="m-0 text-small font-semibold">{funderLine(c)}</p>
      {isNew ? (
        <p className="sr-only">{FIRST_COLLECTED}</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {change.changes.map((l, i) => <li key={`${l.field}-${i}`} className="min-w-0 text-body">{describeChange(l)}</li>)}
        </ul>
      )}
    </Card>
  );
}
