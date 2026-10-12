import { Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Crumb } from '@/lib/seo';
import { Breadcrumbs } from './feedback';
import { Icon } from './icon';

/** Visible on every page whose text is not written yet. Removing the `draft` prop is the whole switch. */
export function DraftNotice({ className }: { className?: string }) {
  return (
    <div role="note" className={cn('flex max-w-[860px] items-start gap-3 rounded-lg border-strong border-dashed border-line bg-surface p-5', className)}>
      <span className="flex size-11 shrink-0 items-center justify-center rounded-pill bg-surface-inset text-ink"><Icon icon={Info} /></span>
      <div className="flex flex-col gap-1">
        <p className="m-0 text-body font-bold">Draft — text pending</p>
        <p className="m-0 text-small text-ink-muted">This page is a skeleton. The final text has not been written yet, so nothing here should be relied on.</p>
      </div>
    </div>
  );
}

/** A value that has to come from the owner. Never filled in by us. */
export function Placeholder({ children = 'to be provided' }: { children?: string }) {
  return <span className="rounded-md bg-surface-inset px-2 py-0.5 font-mono text-mono">[{children}]</span>;
}

/** A surface card with an h2. The id is derived from the title so the section is labelled. */
export function ContentSection({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  const id = `s-${title.toLowerCase().replace(/\W+/g, '-')}`;
  return (
    <section aria-labelledby={id} className={cn('flex flex-col gap-3 rounded-lg bg-surface p-5 sm:p-6', className)}>
      <h2 id={id} className="m-0 text-h3">{title}</h2>
      {children}
    </section>
  );
}

/** Shared shell of the text-style pages: breadcrumbs, h1, lead, optional draft notice, then sections. */
export function ContentPage({ crumbs, title, lead, draft = false, wide = false, children }: {
  crumbs: Crumb[]; title: string; lead?: string; draft?: boolean; wide?: boolean; children?: React.ReactNode;
}) {
  return (
    <>
      <Breadcrumbs items={crumbs} />
      <header className="flex flex-col gap-3">
        <h1 className="m-0 text-[32px] font-extrabold leading-10 tracking-[-1px] md:text-h1">{title}</h1>
        {lead && <p className="m-0 max-w-[62ch] text-body text-ink-muted">{lead}</p>}
      </header>
      {draft && <DraftNotice />}
      {children && <div className={cn('flex flex-col gap-4', !wide && 'max-w-[860px]')}>{children}</div>}
    </>
  );
}

/** Headings of a page whose text is not written: each section shows a visible placeholder, never invented text. */
export function PendingSections({ items }: { items: { title: string; text?: React.ReactNode }[] }) {
  return (
    <>
      {items.map((i) => (
        <ContentSection key={i.title} title={i.title}>
          <p className="m-0 text-body text-ink-muted">{i.text ?? <Placeholder>text pending</Placeholder>}</p>
        </ContentSection>
      ))}
    </>
  );
}
