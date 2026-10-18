import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Icon } from './icon';

/**
 * A native disclosure for what is long and rarely needed: a source line, a citation, a full URL. Works without
 * script, the summary is a 44 px target, the panel breaks long strings (`overflow-wrap: anywhere`) and never runs
 * wider than one reading measure, so a 150-character citation does not stretch a card.
 */
export function Details({ summary, children, defaultOpen = false, className }: {
  summary: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean; className?: string;
}) {
  return (
    <details open={defaultOpen || undefined} className={cn('group min-w-0', className)}>
      <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-1.5 text-small font-semibold text-link [&::-webkit-details-marker]:hidden">
        {summary}
        <Icon icon={ChevronDown} size="inline" className="transition-transform duration-dg group-open:rotate-180" />
      </summary>
      <div className="flex max-w-prose flex-col gap-2 pb-2 pt-1 text-small text-ink-muted [overflow-wrap:anywhere]">{children}</div>
    </details>
  );
}
