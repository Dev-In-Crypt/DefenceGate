import { ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatDateTimeUtc } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { TENDER_CHECKED_LABEL } from '@/lib/tender-status';
import type { SourceAttribution } from '@/lib/types';
import { Icon } from './icon';

/**
 * Provenance for every fact. `inline` = one mono line for cards; `full` = detail pages.
 * "View original" sits above stretched card links (relative z-10).
 * The link is rendered only for an http(s) URL; otherwise the source name stays as text.
 */
export function SourceBadge({ source, variant = 'full', version, retrievedLabel = 'Retrieved', className }: {
  source: SourceAttribution; variant?: 'inline' | 'full'; version?: string; className?: string;
  /** What `retrievedAt` means for this record: "Retrieved" for a call (last seen at the source), the last change seen at the source for a tender. */
  retrievedLabel?: string;
}) {
  const retrieved = formatDateTimeUtc(source.retrievedAt);
  const url = safeHttpUrl(source.url);
  if (variant === 'inline') {
    return (
      // Provenance of a list card: one hairline above it, 13/18 sans (not a monospace sentence), the link at the right end.
      <div className={cn('flex flex-wrap items-center gap-x-4 gap-y-0 border-t border-line pt-1 font-sans text-[13px] leading-[18px] text-ink-muted', className)}>
        <span className="min-w-0 flex-1 basis-64 [overflow-wrap:anywhere]">{source.sourceName} · {retrievedLabel} {retrieved} · {source.licence} · {source.attribution}</span>
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer" className="relative z-10 inline-flex min-h-8 items-center text-small font-bold text-link">
            View original<span className="sr-only"> at {source.sourceName} (opens in new tab)</span>
          </a>
        ) : (
          <span className="text-small">The source gives no link to this record</span>
        )}
      </div>
    );
  }
  return (
    <div className={cn('flex flex-col gap-3', className)}>
      <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 font-mono text-[12px] leading-[18px] tabular-nums">
        <dt className="text-ink-muted">Source</dt><dd className="m-0 font-medium text-ink">{source.sourceName}</dd>
        <dt className="text-ink-muted">{retrievedLabel}</dt><dd className="m-0 text-ink"><time dateTime={source.retrievedAt}>{retrieved}</time></dd>
        {source.checkedAt && (<><dt className="text-ink-muted">{TENDER_CHECKED_LABEL}</dt><dd className="m-0 text-ink"><time dateTime={source.checkedAt}>{formatDateTimeUtc(source.checkedAt)}</time></dd></>)}
        <dt className="text-ink-muted">Licence</dt><dd className="m-0 text-ink">{source.licence}</dd>
        <dt className="text-ink-muted">Attribution</dt><dd className="m-0 text-ink">{source.attribution}</dd>
        {version && (<><dt className="text-ink-muted">Version</dt><dd className="m-0 text-ink">{version}</dd></>)}
      </dl>
      {url ? (
        <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-2 self-start font-sans text-small font-bold text-link">
          View original <Icon icon={ExternalLink} size="inline" /><span className="sr-only">(opens in new tab)</span>
        </a>
      ) : (
        <p className="m-0 font-sans text-small">The source gives no link to this record. Search for it by its identifier at {source.sourceName}.</p>
      )}
    </div>
  );
}
