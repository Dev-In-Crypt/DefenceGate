import { cn } from '@/lib/utils';

/**
 * The card (brand book): one surface, one radius (20 px), no outline (a transparent 1px border, which forced-colours mode draws), one
 * padding (20 px, 28 px from sm: the book's --space-6 is Tailwind's 7). Every white box on the site is this component or the same classes.
 *
 *   <Card>                      plain padded box; children are spaced 16 px apart
 *   <Card title="Terms">        titled: a 56 px header row (h2, optional `action` at the right end), a hairline, then the body
 *   <TextCard title="Privacy">  two columns from lg: the title at the left (220 px), the text at the right (the rest of the card)
 *
 * `as` picks the element (`li` for a card in a list, `article` for a record). A titled card is a `section`
 * labelled by its heading; the heading id is `id`, or a slug of the title.
 */
export const CARD_SURFACE = 'rounded-lg border border-transparent bg-surface';
export const CARD_PADDING = 'p-5 sm:p-7';
const CARD_BODY = 'flex min-w-0 flex-col gap-4 [&_p]:max-w-prose';

export const slugId = (title: string) => title.toLowerCase().replace(/\W+/g, '-');

type Tag = 'div' | 'section' | 'article' | 'aside' | 'li';

export interface CardProps {
  title?: React.ReactNode;
  /** id of the heading (the label of the card). Default: a slug of the title, when it is a string. */
  id?: string;
  /** id of the card element itself (the target of a `#anchor` link). */
  anchor?: string;
  headingLevel?: 'h2' | 'h3';
  /** Right end of the header row of a titled card: a link, a count. */
  action?: React.ReactNode;
  as?: Tag;
  className?: string;
  /** Classes of the body of a titled card (the part under the header row). */
  bodyClassName?: string;
  children?: React.ReactNode;
}

export function Card({ title, id, anchor, headingLevel = 'h2', action, as, className, bodyClassName, children }: CardProps) {
  if (!title) {
    const As = as ?? 'div';
    return <As id={anchor} className={cn(CARD_SURFACE, CARD_PADDING, CARD_BODY, className)}>{children}</As>;
  }
  const As = as ?? 'section';
  const H = headingLevel;
  const hid = id ?? (typeof title === 'string' ? slugId(title) : undefined);
  return (
    <As id={anchor} aria-labelledby={hid} className={cn('card-titled', CARD_SURFACE, 'min-w-0', className)}>
      <div className="card-head flex min-h-14 flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-line px-5 py-3 sm:px-7">
        <H id={hid} className="m-0 scroll-mt-4 text-h3">{title}</H>
        {action}
      </div>
      <div className={cn('card-body', CARD_PADDING, CARD_BODY, bodyClassName)}>{children}</div>
    </As>
  );
}

/**
 * A card of text with the title in its own column: from lg the title (and `aside`: a date, a count) is at the left, 220 px and
 * sticky, and the text at the right in one reading measure (see `.split` in globals.css). Below lg it is a titled card.
 * Every titled card inside a ContentPage that is not `wide` does this on its own (`.reading`); use TextCard anywhere else.
 */
export function TextCard({ aside, className, ...rest }: Omit<CardProps, 'action'> & { aside?: React.ReactNode }) {
  return <Card {...rest} action={aside} className={cn('split', className)} />;
}
