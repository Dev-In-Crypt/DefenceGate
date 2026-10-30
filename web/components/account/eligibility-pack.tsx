'use client';

import Link from 'next/link';
import { useMemo } from 'react';
import { CircleAlert, CircleCheck, Download, Printer } from 'lucide-react';
import { LINE_WORD, PACK_CSV_HEADER, buildPack, packCsvRows, type PackAnswer } from '@/lib/eligibility-pack';
import { toCsv } from '@/lib/csv';
import { formatDateTimeUtc, formatDateUtc, formatNumber, plural } from '@/lib/format';
import { cleanQuote } from '@/lib/quote';
import { safeHttpUrl } from '@/lib/safe-url';
import { useAssessment, useProfile } from '@/components/readiness/use-readiness';
import { NoProfile } from '@/components/readiness/results';
import { Button } from '@/components/dg/button';
import { Skeleton } from '@/components/dg/feedback';
import { Icon } from '@/components/dg/icon';

/**
 * Print: A4, without the account area's menu (the layout's header and sidebar, children of `.page`), each outside link followed by its
 * address, since paper has no links. Only on this page: the rules are inside its own markup (the pattern of components/readiness/report.tsx).
 */
const PRINT_CSS = `
@media print {
  @page { size: A4; margin: 16mm 14mm; }
  .page > header, .page > aside { display: none !important; }
  .pack { font-size: 10.5pt; }
  .pack-item { break-inside: avoid; }
  .pack a[href^="http"]::after { content: " (" attr(href) ")"; font-weight: 400; overflow-wrap: anywhere; }
}`;

const DISCLAIMER = 'Indicative, sources linked, not legal advice.';

/**
 * WP-156: the results pack of the eligibility check (Pro and up). Every open call the saved profile fits, with its verdict, each rule
 * read from the call's document with its sentence and the links, to print (or save as PDF) and as CSV. Built here, in the browser: the
 * profile and the verdicts never leave it (the calls and their facts came from the server, the same for every account).
 */
export function EligibilityPack({ answer, base }: { answer: PackAnswer; base: string }) {
  const { profile, ready } = useProfile();
  const assessment = useAssessment(profile && profile.country ? profile : null);
  const settled = assessment.state === 'done' || assessment.state === 'error' || assessment.state === 'idle';
  // the hook's answer is a new object at every render: the memo keys on its data, or it would build the pack at every render
  const data = assessment.state === 'done' ? assessment.data : null;
  const pack = useMemo(() => (profile && profile.country && settled ? buildPack(answer.items, profile, data) : null),
    [answer, profile, settled, data]);
  /** The file is made at the click, from the pack on the page. */
  const download = () => {
    if (!pack) return;
    const url = URL.createObjectURL(new Blob([toCsv(PACK_CSV_HEADER, packCsvRows(pack.rows, base))], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `defencegate-eligibility-${answer.asOf.slice(0, 10)}.csv`;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  };

  if (!ready || (profile?.country && !settled)) return <div className="flex flex-col gap-3" aria-busy="true"><Skeleton className="h-24" /><Skeleton className="h-40" /></div>;
  if (!profile || !profile.country || !pack) return <NoProfile />;
  const { rows, counts } = pack;
  return (
    <div className="pack flex flex-col gap-6" data-eligibility-pack>
      <style>{PRINT_CSS}</style>
      <header className="flex flex-col gap-3">
        <h2 className="m-0 text-h2 print:text-[18pt]">Open calls your profile fits{profile.name ? `: ${profile.name}` : ''}</h2>
        <p className="m-0 max-w-prose text-body text-ink" data-pack-summary>
          {rows.length === 0
            ? `None of the ${formatNumber(answer.items.length)} open ${plural(answer.items.length, 'call')} fits your saved profile on the rules read so far.`
            : `${formatNumber(rows.length)} of ${formatNumber(answer.items.length)} open ${plural(answer.items.length, 'call')} fit your saved profile: ${formatNumber(counts.yes)} eligible, ${formatNumber(counts.check)} with conditions to check.`}
          {' '}{formatNumber(counts.no)} {counts.no === 1 ? 'is' : 'are'} blocked by a rule and {formatNumber(counts.unknown)} {counts.unknown === 1 ? 'has' : 'have'} no rule read that can be compared; neither is listed.
          {answer.total > answer.items.length ? ` Only the first ${formatNumber(answer.items.length)} of ${formatNumber(answer.total)} open calls (by deadline) were compared.` : ''}
        </p>
        <p className="m-0 text-small text-ink-muted">Calls as of {formatDateTimeUtc(answer.asOf)}. {DISCLAIMER} Your answers stay in this browser.</p>
        <div className="flex flex-wrap gap-3 print:hidden">
          <Button icon={Printer} onClick={() => window.print()} data-pack-print>Print or save as PDF</Button>
          <Button icon={Download} variant="secondary" onClick={download} data-pack-csv>Download CSV</Button>
        </div>
        <p className="m-0 max-w-prose text-small text-ink-muted print:hidden">
          To keep a PDF, choose “Save as PDF” as the printer in your browser’s print dialog. Changed an answer? <Link href="/readiness" className="font-semibold">Edit your profile</Link> and come back.
        </p>
      </header>
      {rows.length > 0 && (
        <ol className="m-0 flex list-none flex-col gap-4 p-0">
          {rows.map(({ call, fit, word, lines }) => {
            const source = safeHttpUrl(call.sourceUrl);
            return (
              <li key={call.id} className="pack-item flex flex-col gap-3 rounded-lg border border-transparent bg-surface p-5 print:border-line print:p-3" data-pack-call={call.id}>
                <div className="flex flex-col gap-1">
                  <Link href={`/funding/${call.slug}`} className="text-h3 font-semibold [overflow-wrap:anywhere]">{call.title}</Link>
                  <span className="hidden text-small [overflow-wrap:anywhere] print:inline">{base}/funding/{call.slug}</span>
                  <span className="text-small text-ink-muted">
                    {call.programmeName ?? call.programme}{call.topicId ? ` · ${call.topicId}` : ''}
                    {call.deadline ? ` · ${call.rolling ? 'next cut-off' : 'deadline'} ${call.deadlineIsDate ? formatDateUtc(call.deadline) : `${formatDateTimeUtc(call.deadline)}`}` : ''}
                  </span>
                </div>
                <span className="inline-flex max-w-full items-start gap-1.5 self-start rounded-pill border border-line bg-surface-inset px-2.5 py-[5px] text-label font-bold" data-pack-verdict>
                  <Icon icon={fit === 'yes' ? CircleCheck : CircleAlert} size="inline" className="mt-0.5 shrink-0" />{word}
                </span>
                {lines.length > 0 && (
                  <ul className="m-0 flex list-none flex-col gap-2 p-0">
                    {lines.map((l) => (
                      <li key={l.key} className="flex flex-col gap-1 border-t border-line pt-2 text-small" data-pack-line>
                        <span><span className="font-semibold">{l.label}</span>: {LINE_WORD[l.verdict]}. {l.reason}</span>
                        {l.quote && <q className="text-ink-muted [overflow-wrap:anywhere]">{cleanQuote(l.quote)}</q>}
                      </li>
                    ))}
                  </ul>
                )}
                {source && <a href={source} className="self-start text-small font-semibold [overflow-wrap:anywhere]" rel="noopener noreferrer">The call at {call.sourceName ?? 'its source'}</a>}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
