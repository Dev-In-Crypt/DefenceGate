import Link from 'next/link';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Icon } from './icon';
import { LinkBusy } from './live-list';

const ITEM = 'inline-flex min-h-11 min-w-11 items-center justify-center gap-1 rounded-pill px-3 font-mono text-mono-strong no-underline hover:no-underline';

/** Link-based pagination so every page is crawlable and shareable. `hrefFor(page)` builds the URL. */
export function Pagination({ page, total, pageSize, hrefFor }: { page: number; total: number; pageSize: number; hrefFor: (page: number) => string }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages === 1) return null;
  const nums = Array.from({ length: pages }, (_, i) => i + 1).filter((n) => n === 1 || n === pages || Math.abs(n - page) <= 1);
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-center gap-1">
      {page > 1 ? <Link href={hrefFor(page - 1)} prefetch={false} rel="prev" className={cn(ITEM, 'font-sans text-small font-bold text-ink hover:bg-surface')}><Icon icon={ChevronLeft} size="inline" />Previous<LinkBusy /></Link> : null}
      {nums.map((n, i) => (
        <span key={n} className="contents">
          {i > 0 && n - nums[i - 1] > 1 && <span className="px-1 text-ink-muted" aria-hidden="true">…</span>}
          {n === page
            ? <span aria-current="page" className={cn(ITEM, 'bg-primary text-on-primary')}>{n}</span>
            : <Link href={hrefFor(n)} prefetch={false} aria-label={`Page ${n}`} className={cn(ITEM, 'text-ink hover:bg-surface')}>{n}<LinkBusy /></Link>}
        </span>
      ))}
      {page < pages ? <Link href={hrefFor(page + 1)} prefetch={false} rel="next" className={cn(ITEM, 'font-sans text-small font-bold text-ink hover:bg-surface')}>Next<Icon icon={ChevronRight} size="inline" /><LinkBusy /></Link> : null}
    </nav>
  );
}
