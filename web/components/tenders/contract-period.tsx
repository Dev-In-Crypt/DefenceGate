import Link from 'next/link';
import type { ContractPeriod } from '@/lib/types';
import type { EndingItem } from '@/lib/contract-period';
import { basisText, durationText, renewalText, spanText } from '@/lib/contract-period';
import { CountryLabel } from '@/components/dg/data-display';
import { displayName } from '@/lib/display-name';
import { cn } from '@/lib/utils';

/**
 * WP-160: a contract period as the notice states it, always with where its end comes from (stated, computed from start + duration,
 * estimated) and the renewal said apart. `data-end-basis` carries the basis for the tests.
 */
export function ContractPeriodText({ p, className }: { p: ContractPeriod; className?: string }) {
  const span = spanText(p);
  const duration = durationText(p);
  const renewal = renewalText(p);
  return (
    <span className={cn('flex flex-col gap-0.5 font-sans', className)} data-contract-period data-end-basis={p.end ? p.endBasis ?? '' : 'none'}>
      {span && <span className="text-ink">{span}{duration ? ` (${duration})` : ''}</span>}
      {!span && duration && <span className="text-ink">{duration}</span>}
      <span className={cn('text-small', p.endBasis === 'estimated' ? 'font-bold text-accent-text' : 'text-ink-muted')} data-basis>{sentence(basisText(p))}</span>
      {renewal && <span className="text-small text-ink-muted" data-renewal>{sentence(renewal)}; not added to the end date</span>}
    </span>
  );
}

const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

const ROW = 'flex min-w-0 flex-col gap-2 rounded-lg border border-transparent bg-surface p-4';

/** One contract of the list or of a buyer's block: the notice, its buyer, the period, the winners where known. */
export function EndingRow({ t, showBuyer = true }: { t: EndingItem; showBuyer?: boolean }) {
  const won = t.awardedTo ?? [];
  return (
    <li className={ROW} data-ending-row>
      <Link href={`/tenders/${t.slug}`} className="min-w-0 break-words text-h3 font-semibold">{displayName(t.title, 'title')}</Link>
      <span className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-small text-ink-muted">
        {showBuyer && <span className="text-ink">{t.buyerSlug ? <Link href={`/buyers/${t.buyerSlug}`}>{t.buyerName}</Link> : t.buyerName}</span>}
        {t.country && <CountryLabel code={t.country} />}
        {t.cpv && <span className="font-mono">CPV {t.cpv}</span>}
        <span className="font-mono">{t.noticeId}</span>
      </span>
      <ContractPeriodText p={t.contractPeriod} />
      <span className="text-small text-ink-muted" data-winners>
        {won.length > 0
          ? <>Awarded to {won.map((w, i) => <span key={`${w.name}-${i}`}>{i > 0 ? ', ' : ''}{w.slug ? <Link href={`/suppliers/${w.slug}`}>{w.name}</Link> : w.name}</span>)}{t.awardedPersons ? ` and ${t.awardedPersons} natural ${t.awardedPersons === 1 ? 'person' : 'persons'} (not named)` : ''}</>
          : 'Winner not known from the notices we hold'}
      </span>
    </li>
  );
}
