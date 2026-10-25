import Link from 'next/link';
import { callStatusKind, getCallDeadline } from '@/lib/deadline';
import { displayName } from '@/lib/display-name';
import { dayParts, formatMonthUtc, openingPhrase } from '@/lib/format';
import { PROGRAMMES, isNonEnglish } from '@/lib/taxonomy';
import { cn } from '@/lib/utils';
import type { Call } from '@/lib/types';
import { StatusPill, Tag } from '../dg/tag';
import { BudgetDisplay, LangLabel } from '../dg/data-display';
import { ROW_HOVER } from '../dg/card';

const DATE_TONE = {
  normal: 'bg-surface-inset text-ink', soon: 'bg-soon-bg text-soon-fg', urgent: 'bg-urgent text-on-urgent',
  closed: 'bg-closed-bg text-closed-fg', none: 'bg-surface-inset text-ink-muted',
} as const;

type DatedCall = Call & { deadline: string };
interface Group { key: string; heading: string; items: Call[] }

function Row({ c }: { c: Call }) {
  const d = getCallDeadline(c);
  const upcoming = c.status === 'forthcoming';
  const nonEnglish = isNonEnglish(c.titleLanguage);
  // A call that has not opened yet is not under time pressure: neutral date block and no countdown.
  const tone = upcoming ? 'normal' : d.state;
  const p = d.iso ? dayParts(d.iso) : null;
  return (
    <li className={`group relative grid grid-cols-[56px_minmax(0,1fr)] items-center gap-4 border-t border-line py-3 first:border-t-0 sm:grid-cols-[56px_minmax(0,1fr)_auto] ${ROW_HOVER}`}>
      {p && d.iso ? (
        <time dateTime={d.iso} className={cn('flex flex-col items-center rounded-md py-2 font-mono tabular-nums', DATE_TONE[tone])}>
          <span className="text-[20px] font-medium leading-6">{p.day}</span>
          <span className="text-[12px] leading-4">{p.weekday}</span>
        </time>
      ) : (
        <span aria-hidden="true" className={cn('flex flex-col items-center rounded-md py-2 font-mono tabular-nums', DATE_TONE.none)}>
          <span className="text-[20px] font-medium leading-6">–</span>
          <span className="text-[12px] leading-4">&nbsp;</span>
        </span>
      )}
      <div className="flex min-w-0 flex-col gap-1">
        <Link href={`/funding/${c.slug}`} prefetch={false} lang={nonEnglish ? c.titleLanguage : undefined}
          className="text-body font-semibold text-ink [overflow-wrap:anywhere] no-underline decoration-2 underline-offset-4 after:absolute after:inset-0 after:content-['']">{displayName(c.title)}</Link>
        <div className="flex flex-wrap items-center gap-2">
          <Tag kind="programme">{PROGRAMMES[c.programme].label}</Tag>
          <span className="font-mono text-mono text-ink-muted">{d.rolling ? `Rolling submission, last cut-off ${d.utc}` : d.utc || 'No fixed deadline'}</span>
          {nonEnglish && <LangLabel kind="language" code={c.titleLanguage} />}
        </div>
      </div>
      <div className="col-start-2 flex flex-wrap items-center gap-3 sm:col-start-auto sm:flex-col sm:items-end sm:gap-1">
        {upcoming && c.openingDate ? (
          <span className="text-small font-bold text-ink">{openingPhrase(c.openingDate).lead} {openingPhrase(c.openingDate).date}</span>
        ) : d.countdown ? (
          <span className={cn('text-small font-bold', d.state === 'closed' ? 'text-ink-muted' : d.state === 'normal' ? 'text-accent-text' : 'text-soon-fg')}>{d.countdown}</span>
        ) : null}
        <BudgetDisplay money={c.budget} note={c.budgetNote} className="text-mono text-ink-muted" />
        {(d.state === 'closed' || upcoming) && <StatusPill status={callStatusKind(c.status, d.state, c.openingDate)} />}
      </div>
    </li>
  );
}

/**
 * Agenda-style calendar: calls with a deadline grouped by deadline month, then the calls
 * without a deadline in their own group at the end.
 */
export function CallCalendar({ calls }: { calls: Call[] }) {
  const dated = calls.filter((c): c is DatedCall => c.deadline !== null).sort((a, b) => a.deadline.localeCompare(b.deadline));
  const undated = calls.filter((c) => c.deadline === null);

  const groups: Group[] = [];
  for (const c of dated) {
    const key = c.deadline.slice(0, 7);
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.items.push(c);
    else groups.push({ key, heading: formatMonthUtc(c.deadline), items: [c] });
  }
  if (undated.length > 0) groups.push({ key: 'none', heading: 'No fixed deadline', items: undated });

  return (
    <div className="flex flex-col gap-6">
      {groups.map((g) => (
        <section key={g.key} aria-labelledby={`m-${g.key}`} className="flex flex-col gap-2 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
          <h2 id={`m-${g.key}`} className="m-0 text-h3">{g.heading}</h2>
          <ul className="m-0 flex list-none flex-col p-0">
            {g.items.map((c) => <Row key={c.id} c={c} />)}
          </ul>
        </section>
      ))}
    </div>
  );
}
