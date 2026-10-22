import { cn } from '@/lib/utils';

/**
 * Running text: the reading measure (`--measure`, the full width of the block since WP-83), 16/24, 16 px between blocks,
 * real list markers (the reset removes them), ink colour. Put it around paragraphs and lists that belong together;
 * `muted` is for secondary text. It sets the width of the text, not of the box: the box can be as wide as it likes.
 */
export function Prose({ as = 'div', muted = false, className, children }: {
  as?: 'div' | 'section' | 'article'; muted?: boolean; className?: string; children: React.ReactNode;
}) {
  const As = as;
  return (
    <As className={cn(
      'justify-text max-w-prose text-body [&>*+*]:mt-4 [&_p]:m-0 [&_ul]:m-0 [&_ol]:m-0 [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-6 [&_ol]:pl-6 [&_li+li]:mt-1',
      muted ? 'text-ink-muted' : 'text-ink', className)}>
      {children}
    </As>
  );
}
