import Link from 'next/link';
import { ChevronRight, CircleAlert, Clock, Inbox, Lock, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { breadcrumbJsonLd, type Crumb } from '@/lib/seo';
import { Icon } from './icon';
import { Button } from './button';

export function JsonLd({ data }: { data: object }) {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, '\\u003c') }} />;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb">
      <JsonLd data={breadcrumbJsonLd(items)} />
      <ol className="m-0 flex list-none flex-wrap items-center gap-1 p-0 text-small">
        {items.map((c, i) => {
          const last = i === items.length - 1;
          return (
            <li key={c.href} className="inline-flex min-w-0 items-center gap-1">
              {last ? (
                <span aria-current="page" className="max-w-[40ch] truncate text-ink-muted">{c.label}</span>
              ) : (
                <><Link href={c.href} className="inline-flex min-h-6 items-center font-semibold">{c.label}</Link><Icon icon={ChevronRight} size="inline" className="text-ink-muted" /></>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function StateShell({ icon, title, children, action, tone = 'default' }: { icon: React.ReactNode; title: string; children?: React.ReactNode; action?: React.ReactNode; tone?: 'default' | 'error' }) {
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className="flex flex-col items-start gap-4 rounded-lg bg-surface p-6">
      <span className={cn('flex size-11 items-center justify-center rounded-pill bg-surface-inset', tone === 'error' ? 'text-alert' : 'text-ink')}>{icon}</span>
      <div className="flex flex-col gap-1">
        <h2 className="m-0 text-h3">{title}</h2>
        {children && <div className="m-0 max-w-[60ch] text-body text-ink-muted">{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return <StateShell icon={<Icon icon={Inbox} />} title={title} action={action}>{children}</StateShell>;
}

/** `onRetry` works from client error boundaries; `retryHref` from server components. */
export function ErrorState({ title = 'We could not load this data', children, onRetry, retryHref }: { title?: string; children?: React.ReactNode; onRetry?: () => void; retryHref?: string }) {
  const action = onRetry ? <Button variant="secondary" icon={RotateCcw} onClick={onRetry}>Try again</Button>
    : retryHref ? <Button variant="secondary" icon={RotateCcw} href={retryHref}>Try again</Button> : undefined;
  return <StateShell tone="error" icon={<Icon icon={CircleAlert} />} title={title} action={action}>{children ?? 'The source may be temporarily unavailable. Your filters are kept in the address bar.'}</StateShell>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn('rounded-md bg-surface-inset motion-safe:animate-pulse', className)} />;
}

export function CallCardSkeleton() {
  return (
    <div className="flex flex-col gap-5 rounded-lg bg-surface p-6">
      <div className="flex gap-2"><Skeleton className="h-[26px] w-14 rounded-pill" /><Skeleton className="h-[26px] w-20 rounded-pill" /><Skeleton className="ml-auto h-7 w-16 rounded-pill" /></div>
      <Skeleton className="h-8 w-3/4" />
      <div className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3"><Skeleton className="h-[88px]" /><Skeleton className="h-[88px]" /><Skeleton className="h-[88px]" /></div>
      <Skeleton className="h-4 w-1/2" />
    </div>
  );
}

/** Plan gate. Content is never rendered behind the lock. Without `href` (no plans page yet) the action is plain text. */
export function LockedFeature({ feature, plan = 'Pro', href }: { feature: string; plan?: string; href?: string }) {
  return (
    <div className="flex flex-col items-start gap-4 rounded-lg border-strong border-dashed border-line bg-surface p-6">
      <span className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink"><Icon icon={Lock} /></span>
      <div className="flex flex-col gap-1">
        <h2 className="m-0 text-h3">{feature}</h2>
        <p className="m-0 text-body text-ink-muted">Available on the {plan} plan.</p>
      </div>
      {href ? <Button href={href}>See plans</Button> : <span className="font-mono text-mono text-ink-muted">Plans: coming soon</span>}
    </div>
  );
}

/** Small placeholder for planned features. Never a full design. */
export function ComingSoon({ feature, className }: { feature: string; className?: string }) {
  return (
    <div className={cn('flex items-center gap-3 rounded-md bg-surface-inset px-4 py-3', className)}>
      <Icon icon={Clock} className="shrink-0 text-ink-muted" />
      <span className="text-small"><span className="font-bold">{feature}</span> <span className="text-ink-muted">· Coming soon</span></span>
    </div>
  );
}
