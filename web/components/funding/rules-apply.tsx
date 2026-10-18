import Link from 'next/link';
import { ExternalLink } from 'lucide-react';
import { safeHttpUrl } from '@/lib/safe-url';
import { requirementSlug } from '@/lib/readiness';
import { Icon } from '@/components/dg/icon';
import type { RulesApply } from '@/lib/types';

/** Where the Ukraine flag was read from, in words. */
export const UKRAINE_BASIS: Record<string, string> = {
  call_document: 'From the call document',
  topic_text: 'From the topic’s own conditions',
  call_text: 'From the call’s conditions text',
  programme_rule: 'From the regulation of this regime',
  edf_association_unconfirmed: 'From the European Defence Fund regulation',
};

/**
 * The regime a call is under and the headline conditions of that regime, each with the sentence of the regulation it
 * rests on. No verdict: the readiness check gives that, from the company's own answers.
 */
export function RulesApplyBlock({ block }: { block: RulesApply }) {
  const reviewed = block.rules.map((r) => r.source.lastReviewed).sort().pop();
  return (
    <>
      <p className="m-0 text-body">
        This call falls under <strong>{block.regime.name}</strong>. <span className="text-ink-muted">{block.regime.why}</span>
      </p>
      {block.encoded ? (
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {block.rules.map((r) => {
            const url = safeHttpUrl(r.source.url);
            return (
              <li key={r.rule} className="flex flex-col gap-1 rounded-md bg-surface-inset p-4">
                <p className="m-0 text-body font-semibold">{r.title}</p>
                <details>
                  <summary className="min-h-11 cursor-pointer py-2 text-small font-semibold">The sentence of the regulation</summary>
                  <blockquote className="m-0 whitespace-pre-wrap break-words border-l-4 border-line pl-3 text-small">{r.source.text}</blockquote>
                </details>
                <p className="m-0 flex flex-wrap items-center gap-x-3 text-small text-ink-muted">
                  <span>{r.source.ref}</span>
                  {url && (
                    <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-1 font-semibold">
                      Official Journal<Icon icon={ExternalLink} size="inline" /><span className="sr-only">(opens in new tab)</span>
                    </a>
                  )}
                  {r.requirement && <Link href={`/requirements/${requirementSlug(r.requirement)}`} className="inline-flex min-h-11 items-center font-semibold">About this rule</Link>}
                </p>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="m-0 text-body text-ink-muted">
          No rules of this regime are encoded in our readiness check, so none are listed here. Its conditions are in the documents under “Can you apply?” and in the official call text.
        </p>
      )}
      {block.alsoRead && (
        <div className="flex flex-col gap-1 rounded-md bg-surface-inset p-4">
          <p className="m-0 text-body font-semibold">{block.alsoRead.label}</p>
          <blockquote className="m-0 break-words border-l-4 border-line pl-3 text-small">{block.alsoRead.text}</blockquote>
          <p className="m-0 flex flex-wrap items-center gap-x-3 text-small text-ink-muted">
            <span>{block.alsoRead.ref}</span>
            {safeHttpUrl(block.alsoRead.url) && (
              <a href={safeHttpUrl(block.alsoRead.url) ?? '#'} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-1 font-semibold">
                Official Journal<Icon icon={ExternalLink} size="inline" /><span className="sr-only">(opens in new tab)</span>
              </a>
            )}
          </p>
          <p className="m-0 text-small text-ink-muted">This rule is not part of the readiness check yet.</p>
        </div>
      )}
      <p className="m-0 text-small text-ink-muted">
        {block.notice}{reviewed ? ` Rules last reviewed ${reviewed}.` : ''}{' '}
        {block.encoded && <>Check your own company in the <Link href="/readiness" className="font-semibold">readiness check</Link>, or read <Link href="/requirements" className="font-semibold">all requirements</Link>.</>}
      </p>
    </>
  );
}

/** What the Ukraine flag says, in a sentence. Null: nothing to show. */
export function ukraineSentence(flag: boolean | null | undefined, reason: string | undefined): string | null {
  if (flag === true) return 'Ukrainian entities may take part in this call.';
  if (flag === false) {
    return reason === 'programme_rule'
      ? 'The regulation of this regime does not list Ukraine among the countries whose entities may take part. Ukrainian entities are served by the Ukraine Support Instrument instead.'
      : 'The source says Ukrainian entities may not take part in this call.';
  }
  if (reason === 'edf_association_unconfirmed') {
    return 'Unknown. Ukraine may take part in the European Defence Fund as an associated country, under the EU-Ukraine association agreement. We have found no official text that says that agreement is in force, so we do not mark this call.';
  }
  return null;
}
