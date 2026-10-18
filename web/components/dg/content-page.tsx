import { Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Crumb } from '@/lib/seo';
import { Icon } from './icon';
import { Card, TextCard, slugId } from './card';
import { PageHeader } from './page-header';

/** Visible on every page whose text is not written yet. Removing the `draft` prop is the whole switch. */
export function DraftNotice({ className }: { className?: string }) {
  return (
    <div role="note" className={cn('flex items-start gap-3 rounded-lg border-strong border-dashed border-line bg-surface p-5', className)}>
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

/**
 * A titled card (56 px header row with the h2, then the body). The id is derived from the title so the section is labelled.
 * On a ContentPage that is not `wide` the title moves to its own column from lg (see `.reading` in globals.css).
 */
export function ContentSection({ title, children, className, aside }: {
  title: string; children: React.ReactNode; className?: string; aside?: React.ReactNode;
}) {
  return <Card title={title} id={`s-${slugId(title)}`} action={aside} className={className}>{children}</Card>;
}

/**
 * A section with no box: an h2 (24/32) and, 16 px under it, whatever it holds (a grid of cards, a list). The page puts
 * 32 px between sections, so the heading is twice as close to its own content as to the section above.
 */
export function PageSection({ title, id, intro, children, className }: {
  title: string; id?: string; intro?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  const hid = id ?? `s-${slugId(title)}`;
  return (
    <section aria-labelledby={hid} className={cn('flex min-w-0 flex-col gap-4', className)}>
      <div className="flex flex-col gap-2">
        <h2 id={hid} className="m-0 scroll-mt-4 text-h2">{title}</h2>
        {intro && <div className="max-w-prose text-body text-ink-muted">{intro}</div>}
      </div>
      {children}
    </section>
  );
}

/**
 * Shared shell of the text-style pages: PageHeader (breadcrumbs, h1, lead), optional draft notice, then sections.
 * Two kinds, one prop:
 *  - reading (default): one centred column, 220 + 40 + 680 + 48 = 988 px; every titled card has its title in a left column and
 *    its text at the right (`.reading`), so the page is a composition and not a strip of text hugging the left of a wide card.
 *  - `wide` (data pages: tables, grids, figures): the full content box; titled cards keep the title on top.
 * Either way running text (`p`, `blockquote`, `dd`, bulleted lists) never runs wider than the reading measure, and sections are 32 px apart.
 */
export function ContentPage({ crumbs, title, lead, draft = false, wide = false, children }: {
  crumbs: Crumb[]; title: string; lead?: string; draft?: boolean; wide?: boolean; children?: React.ReactNode;
}) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-8 md:gap-12', wide ? 'w-full' : 'reading mx-auto w-full max-w-reading')}>
      <PageHeader crumbs={crumbs} title={title} lead={lead} />
      {draft && <DraftNotice />}
      {children && (
        <div className="flex flex-col gap-8 [&_blockquote]:max-w-prose [&_dd]:max-w-prose [&_p]:max-w-prose [&_.list-decimal]:max-w-prose [&_.list-disc]:max-w-prose">
          {children}
        </div>
      )}
    </div>
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
