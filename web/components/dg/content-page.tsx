import { Children, Fragment, isValidElement } from 'react';
import { Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Crumb } from '@/lib/seo';
import { Icon } from './icon';
import { Card, TextCard, slugId } from './card';
import { PageHeader } from './page-header';
import { Clause, ClauseGroup } from './blocks';

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
export function ContentSection({ title, children, className, aside, split = false }: {
  title: string; children: React.ReactNode; className?: string; aside?: React.ReactNode;
  /** Title in its own 220 px column from lg (a text card on a `wide` page, where the reading layout does not apply). */
  split?: boolean;
}) {
  return <Card title={title} id={`s-${slugId(title)}`} action={aside} className={cn(split && 'split', className)}>{children}</Card>;
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

export interface TocItem { id: string; label: string }

/**
 * The contents of a page, read from its children: a ContentSection or PageSection by its title, a Clause by its number and title.
 * Fragments are walked; anything else (a Callout, a paragraph) is not a section and is skipped.
 */
export function tocOf(children: React.ReactNode): TocItem[] {
  const out: TocItem[] = [];
  const walk = (nodes: React.ReactNode) => {
    Children.forEach(nodes, (c) => {
      if (!isValidElement(c)) return;
      const p = c.props as { title?: unknown; id?: string; n?: number; children?: React.ReactNode };
      if (c.type === Fragment || c.type === ClauseGroup) walk(p.children);
      else if (c.type === ContentSection && typeof p.title === 'string') out.push({ id: `s-${slugId(p.title)}`, label: p.title });
      else if (c.type === PageSection && typeof p.title === 'string') out.push({ id: p.id ?? `s-${slugId(p.title)}`, label: p.title });
      else if (c.type === Clause && typeof p.title === 'string') out.push({ id: `c${p.n}`, label: `${p.n}. ${p.title}` });
    });
  };
  walk(children);
  return out;
}

/**
 * The contents list of a long page: from lg a sticky column at the left (220 px) that scrolls on its own when it is longer than the
 * screen. Below lg it is not shown: the page is one column and the headings are the structure. Each link is a 32 px target.
 */
function PageToc({ items }: { items: TocItem[] }) {
  return (
    <nav aria-label="Contents" className="hidden lg:sticky lg:top-4 lg:col-start-1 lg:row-start-1 lg:block lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto print:hidden">
      <p className="m-0 pb-1 text-label text-ink-muted">On this page</p>
      <ol className="m-0 flex list-none flex-col border-l border-line p-0">
        {items.map((i) => (
          <li key={i.id}>
            <a href={`#${i.id}`} className="-ml-px flex min-h-8 items-center border-l border-transparent py-1 pl-3 text-small text-ink-muted hover:border-ink hover:text-ink">{i.label}</a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

/**
 * Shared shell of the text-style pages: PageHeader (breadcrumbs, h1, lead), optional draft notice, then sections.
 * Two kinds, one prop:
 *  - reading (default): every titled card has its title in a left column (220 px) and its text at the right (`.reading`).
 *  - `wide` (data pages: tables, grids, figures): titled cards keep the title on top.
 * Both span the whole content box, exactly the width of the header pill (WP-45: the 988 px column left the page narrower than the header).
 * Running text (`p`, `blockquote`, `dd`, bulleted lists) never runs wider than the reading measure, paragraphs are justified from md
 * (`.justify-text`), and sections are 32 px apart.
 *
 * `toc` (WP-45) puts a sticky list of the sections at the left from lg (`true` = read it from the children, or pass the items). The
 * sections then use the column beside it (what is left of the content box) and keep their titles on top. The list comes after the
 * content in the document, so the text reads first.
 */
export function ContentPage({ crumbs, title, lead, draft = false, wide = false, toc, children }: {
  crumbs: Crumb[]; title: string; lead?: string; draft?: boolean; wide?: boolean; toc?: boolean | TocItem[]; children?: React.ReactNode;
}) {
  const items = toc === true ? tocOf(children) : toc || [];
  const hasToc = items.length > 1;
  const body = children && (
    <div className={cn(
      'justify-text flex min-w-0 flex-col gap-8 [&_blockquote]:max-w-prose [&_dd]:max-w-prose [&_p]:max-w-prose [&_.list-decimal]:max-w-prose [&_.list-disc]:max-w-prose',
      hasToc && 'lg:col-start-2 lg:row-start-1')}>
      {children}
    </div>
  );
  return (
    <div className={cn('flex min-w-0 flex-col gap-8 md:gap-12', 'w-full', !wide && !hasToc && 'reading')}>
      <PageHeader crumbs={crumbs} title={title} lead={lead} />
      {draft && <DraftNotice />}
      {hasToc ? (
        <div className="toc-page grid min-w-0 items-start gap-8 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-10">
          {body}
          <PageToc items={items} />
        </div>
      ) : body}
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
