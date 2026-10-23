import Link from 'next/link';
import { isNonEnglish } from '@/lib/taxonomy';
import { displayName } from '@/lib/display-name';
import { formatDateTimeUtc, formatDateUtc } from '@/lib/format';
import type { Change } from '@/lib/types';
import { Card } from '../dg/card';
import { StatusPill, Tag } from '../dg/tag';
import { describeChange } from '../dg/version-timeline';

/** The sentence a "new" entry carries. The list says it once, in the legend; each entry keeps it for a screen reader. */
export const FIRST_COLLECTED = 'First collected by DefenceGate on this day.';
/** WP-95: the same for a new award notice (a result, not a call). */
export const FIRST_COLLECTED_AWARD = 'An award notice, first collected by DefenceGate on this day.';

/**
 * One change: a notice that is new, or that was amended, on one day. The lines under the title say what moved
 * ("Deadline changed from ... to ..."), in the words of the notice's own version history.
 */
export function ChangeEntry({ change }: { change: Change }) {
  const t = change.tender;
  const isNew = change.kind === 'new' || change.kind === 'award';
  const isAward = change.kind === 'award';
  const more = (change.repeats ?? 1) - 1;
  return (
    <Card as="article" className="h-full gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {isNew ? <Tag kind="programme">{isAward ? 'New award' : 'New'}</Tag> : <StatusPill status="amended" />}
        {t.country && <Tag>{t.country}</Tag>}
        <time dateTime={change.detectedAt} className="ml-auto font-mono text-mono text-ink-muted">Seen {formatDateTimeUtc(change.detectedAt)}</time>
      </div>
      <h3 className="m-0 break-words text-h3">
        <Link href={`/tenders/${t.slug}`} lang={isNonEnglish(t.titleLanguage) ? (t.titleLanguage ?? undefined) : undefined}>{displayName(t.title)}</Link>
      </h3>
      <p className="m-0 text-small font-semibold">
        {t.buyerSlug ? <Link href={`/buyers/${t.buyerSlug}`} className="inline-flex min-h-8 items-center">{displayName(t.buyerName, 'title')}</Link> : displayName(t.buyerName, 'title')}
      </p>
      {/* WP-95: when the notice was published, and how many look-alike notices (lots, a second source) this row stands for */}
      {t.publishedAt && <p className="m-0 text-small text-ink-muted" data-published>Published {formatDateUtc(t.publishedAt)}</p>}
      {more > 0 && <p className="m-0 text-small text-ink-muted" data-repeats>{`And ${more} more ${more === 1 ? 'notice' : 'notices'} of the same buyer with the same title (lots, or another source), listed once`}</p>}
      {isNew ? (
        <p className="sr-only">{isAward ? FIRST_COLLECTED_AWARD : FIRST_COLLECTED}</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {change.changes.map((c, i) => <li key={`${c.field}-${i}`} className="min-w-0 text-body">{describeChange(c)}</li>)}
        </ul>
      )}
    </Card>
  );
}
