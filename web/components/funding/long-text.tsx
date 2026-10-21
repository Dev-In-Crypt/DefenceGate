import { Details } from '@/components/dg/details';
import { fullTextLabel, textHead } from '@/lib/long-text';
import { cn } from '@/lib/utils';

/**
 * A source text that may be long. Short: shown whole. Long: the first ~600 characters, then a disclosure ("Show full text,
 * N characters") that holds all of it. `pre`: keep the source's line breaks.
 */
export function LongText({ text, pre = false, className }: { text: string; pre?: boolean; className?: string }) {
  const head = textHead(text);
  const body = cn('m-0 max-w-prose break-words text-body text-ink', pre && 'whitespace-pre-wrap', className);
  if (head === null) return <p className={body}>{text}</p>;
  return (
    <>
      {/* in print the disclosure is open (the whole text), so the head is not printed twice */}
      <p className={cn(body, 'print:hidden')}>{head}</p>
      <Details summary={fullTextLabel(text)}>
        <p className={body}>{text}</p>
      </Details>
    </>
  );
}
