import Link from 'next/link';
import { ExternalLink } from 'lucide-react';
import { safeHttpUrl } from '@/lib/safe-url';
import { requirementSlug } from '@/lib/readiness';
import { Icon } from '@/components/dg/icon';
import { Details } from '@/components/dg/details';
import type { RulesApply } from '@/lib/types';

/** Where the Ukraine flag was read from, in words. */
export const UKRAINE_BASIS: Record<string, string> = {
  call_document: 'From the call document',
  topic_text: 'From the topic’s own conditions',
  call_text: 'From the call’s conditions text',
  programme_rule: 'From the regulation of this regime',
  edf_association_unconfirmed: 'From the EDF call documents and the regulation',
  call_document_closed_list: 'From the call document’s list of eligible countries',
  topic_text_associated: 'From the topic’s own conditions and the general annexes',
};

/** One rule: a hairline above it, no box (the card around the block is the only box). */
const RULE = 'flex flex-col gap-1 border-t border-line py-4';

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
        <ul className="m-0 flex list-none flex-col p-0">
          {block.rules.map((r) => {
            const url = safeHttpUrl(r.source.url);
            return (
              <li key={r.rule} className={RULE}>
                <p className="m-0 text-body font-semibold">{r.title}</p>
                {r.caveat && <p className="m-0 text-small">{r.caveat}</p>}
                <Details summary="The sentence of the regulation">
                  <blockquote className="m-0 whitespace-pre-wrap break-words border-l-4 border-line pl-3 text-small text-ink">{r.source.text}</blockquote>
                </Details>
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
        <div className={RULE}>
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

export { ukraineSentence } from '@/lib/ukraine';
