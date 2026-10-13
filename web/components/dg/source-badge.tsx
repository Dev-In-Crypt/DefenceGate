import { ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatDateTimeUtc } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import type { SourceAttribution } from '@/lib/types';
import { Icon } from './icon';

/**
 * Provenance for every fact. `inline` = one mono line for cards; `full` = detail pages.
 * "View original" sits above stretched card links (relative z-10).
 * The link is rendered only for an http(s) URL; otherwise the source name stays as text.
 */
export function SourceBadge({ source, variant = 'full', version, retrievedLabel = 'Retrieved', className }: {
  source: SourceAttribution; variant?: 'inline' | 'full'; version?: string; className?: string;
  /** What `retrievedAt` means for this record: "Retrieved" for a call (last seen at the source), the archive's own change time for a tender. */
  retrievedLabel?: string;
}) {
  const retrieved = formatDateTimeUtc(source.retrievedAt);
  const url = safeHttpUrl(source.url);
  if (variant === 'inline') {
    return (
      <div className={cn('flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-mono text-ink-muted', className)}>
        <span>{source.sourceName} · {retrievedLabel} {retrieved} · {source.licence} · {source.attribution}</span>
        {url && (
          <a href={url} target="_blank" rel="noopener noreferrer" className="relative z-10 ml-auto font-sans text-small font-bold text-link">
            View original<span className="sr-only"> at {source.sourceName} (opens in new tab)</span>
          </a>
        )}
      </div>
    );
  }
  return (
    <div className={cn('flex flex-col gap-3 rounded-md bg-surface-inset p-4', className)}>
      <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 font-mono text-[12px] leading-[18px] tabular-nums">
        <dt className="text-ink-muted">Source</dt><dd className="m-0 font-medium text-ink">{source.sourceName}</dd>
        <dt className="text-ink-muted">{retrievedLabel}</dt><dd className="m-0 text-ink"><time dateTime={source.retrievedAt}>{retrieved}</time></dd>
        <dt className="text-ink-muted">Licence</dt><dd className="m-0 text-ink">{source.licence}</dd>
        <dt className="text-ink-muted">Attribution</dt><dd className="m-0 text-ink">{source.attribution}</dd>
        {version && (<><dt className="text-ink-muted">Version</dt><dd className="m-0 text-ink">{version}</dd></>)}
      </dl>
      {url && (
        <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-2 self-start font-sans text-small font-bold text-link">
          View original <Icon icon={ExternalLink} size="inline" /><span className="sr-only">(opens in new tab)</span>
        </a>
      )}
    </div>
  );
}
