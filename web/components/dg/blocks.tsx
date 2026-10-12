import { Info, Plus, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Icon } from './icon';

/** A short, framed note. Used for the "in short" summary of long texts and for plain-language caveats. */
export function Callout({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <aside className={cn('flex max-w-[860px] items-start gap-3 rounded-lg border-strong border-line bg-surface p-5 sm:p-6', className)}>
      <span className="flex size-11 shrink-0 items-center justify-center rounded-pill bg-surface-inset text-ink"><Icon icon={Info} /></span>
      <div className="flex min-w-0 flex-col gap-2">
        <p className="m-0 text-body font-bold">{title}</p>
        <div className="flex flex-col gap-2 text-body text-ink-muted">{children}</div>
      </div>
    </aside>
  );
}

export interface Benefit { icon: LucideIcon; title: string; body: string }

/** Titled blocks of one sentence each: the unit of a benefit list on a page that sells. */
export function BenefitGrid({ items, columns = 3 }: { items: Benefit[]; columns?: 2 | 3 }) {
  return (
    <ul className={cn('m-0 grid list-none gap-4 p-0', columns === 3 ? 'md:grid-cols-2 lg:grid-cols-3' : 'md:grid-cols-2')}>
      {items.map((b) => (
        <li key={b.title} className="flex min-w-0 flex-col gap-3 rounded-lg bg-surface p-6">
          <span className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink"><Icon icon={b.icon} /></span>
          <h3 className="m-0 text-h3">{b.title}</h3>
          <p className="m-0 text-body text-ink-muted">{b.body}</p>
        </li>
      ))}
    </ul>
  );
}

/** Numbered steps. */
export function Steps({ items }: { items: { title: string; body: string }[] }) {
  return (
    <ol className="m-0 grid list-none gap-4 p-0 md:grid-cols-3">
      {items.map((s, i) => (
        <li key={s.title} className="flex flex-col gap-2 rounded-lg bg-surface p-6">
          <span className="font-mono text-mono text-ink-muted">Step {i + 1}</span>
          <h3 className="m-0 text-h3">{s.title}</h3>
          <p className="m-0 text-body text-ink-muted">{s.body}</p>
        </li>
      ))}
    </ol>
  );
}

/** Who it is for: a name and one line of what they get. */
export function AudienceGrid({ items }: { items: { who: string; body: string }[] }) {
  return (
    <ul className="m-0 grid list-none gap-4 p-0 md:grid-cols-2">
      {items.map((a) => (
        <li key={a.who} className="flex min-w-0 flex-col gap-1 rounded-lg bg-surface p-6">
          <h3 className="m-0 text-h3">{a.who}</h3>
          <p className="m-0 text-body text-ink-muted">{a.body}</p>
        </li>
      ))}
    </ul>
  );
}

export interface FaqItem { q: string; a: string }

/** Native disclosure: works without script and is keyboard-reachable. */
export function Faq({ items }: { items: FaqItem[] }) {
  return (
    <div className="flex flex-col gap-2">
      {items.map((f) => (
        <details key={f.q} className="group rounded-lg bg-surface px-6">
          <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 py-4 text-body font-semibold [&::-webkit-details-marker]:hidden">
            {f.q}
            <Icon icon={Plus} className="shrink-0 text-ink-muted transition-transform duration-dg group-open:rotate-45" />
          </summary>
          <p className="m-0 pb-5 text-body text-ink-muted">{f.a}</p>
        </details>
      ))}
    </div>
  );
}

/**
 * One numbered clause of a legal text. `id` is the anchor, so a clause can be linked.
 * Paragraphs are separate strings: a clause is never one block of prose.
 */
export function Clause({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  const id = `c${n}`;
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="flex scroll-mt-4 flex-col gap-3 rounded-lg bg-surface p-5 sm:p-6">
      <h2 id={`${id}-h`} className="m-0 text-h3"><span className="mr-2 font-mono text-mono text-ink-muted">{n}.</span>{title}</h2>
      <div className="flex flex-col gap-3 text-body text-ink-muted">{children}</div>
    </section>
  );
}

/** Lettered or plain list inside a clause. */
export function ClauseList({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="m-0 flex list-disc flex-col gap-1 pl-6">
      {items.map((it, i) => <li key={i}>{it}</li>)}
    </ul>
  );
}
