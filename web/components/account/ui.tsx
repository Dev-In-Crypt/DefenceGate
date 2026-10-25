import Link from 'next/link';
import { CircleAlert, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getCallDeadline, getTenderDeadline } from '@/lib/deadline';
import { formatDateUtc } from '@/lib/format';
import { itemHref } from '@/lib/account-format';
import { PROGRAMMES } from '@/lib/taxonomy';
import type { Call, ShortlistKind, Tender } from '@/lib/types';
import { Icon } from '../dg/icon';
import { Button } from '../dg/button';
import { Card } from '../dg/card';
import { PageHeader } from '../dg/page-header';

/** Page title of a signed-in page. No breadcrumbs: the sidebar is the navigation. */
export function AppHeader({ title, lead }: { title: string; lead?: string }) {
  return <PageHeader title={title} lead={lead} />;
}

/** A framed section with an h2. */
export function Block({ id, title, aside, children, className }: {
  id: string; title: string; aside?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return <Card title={title} id={id} action={aside} className={className}>{children}</Card>;
}

/** What to do next, with links. Never a bare empty box. */
export function NextStep({ children, links }: { children: React.ReactNode; links: { label: string; href: string }[] }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-md bg-surface-inset p-4">
      <p className="m-0 text-body text-ink-muted">{children}</p>
      <div className="flex flex-wrap gap-x-4">
        {links.map((l) => <Link key={l.href} href={l.href} className="inline-flex min-h-11 items-center text-small font-bold">{l.label}</Link>)}
      </div>
    </div>
  );
}

const NOTICES: Record<string, { text: string; error?: true }> = {
  saved: { text: 'Saved.' },
  removed: { text: 'Removed.' },
  revoked: { text: 'Session ended.' },
  error: { text: 'That did not work. Try again.', error: true },
  confirm: { text: 'That did not match your e-mail address. Nothing was deleted.', error: true },
  countries: { text: 'Choose at most 20 countries.', error: true },
  invalid: { text: 'One of the values was not accepted. Check the form and try again.', error: true },
  password: { text: 'Your password is changed. Every other browser was signed out.' },
  wrong_password: { text: 'The current password is wrong. Nothing was changed.', error: true },
  weak: { text: 'Choose another new password: at least 12 characters, and not a common or easily guessed one.', error: true },
  rate_limited: { text: 'Too many attempts. Wait a little and try again.', error: true },
  totp_off: { text: 'Two-step sign-in is off.' },
};

/** Result of the last action, from `?n=`. Only codes in the table above are ever shown. */
export function Notice({ code }: { code?: string | string[] }) {
  const n = NOTICES[Array.isArray(code) ? (code[0] ?? '') : (code ?? '')];
  if (!n) return null;
  return (
    <p role={n.error ? 'alert' : 'status'} className={cn('m-0 flex items-center gap-2 rounded-md bg-surface p-4 text-small font-semibold', n.error ? 'text-alert' : 'text-ink')}>
      <Icon icon={n.error ? CircleAlert : Info} size="inline" />{n.text}
    </p>
  );
}

export function LoadFailed({ href }: { href: string }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-4 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
      <span className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-alert"><Icon icon={CircleAlert} /></span>
      <div className="flex flex-col gap-1">
        <h2 className="m-0 text-h3">We could not load this</h2>
        <p className="m-0 max-w-prose text-body text-ink-muted">Your account is fine. The service did not answer. Try again in a moment.</p>
      </div>
      <Button href={href} variant="secondary">Try again</Button>
    </div>
  );
}

/**
 * One notice or call as a compact row: title (a link to the public page), who it is from and the deadline.
 * `item` null is a notice that is no longer published; the row says so and stays removable elsewhere.
 */
export function ItemRow({ kind, item, refId, badge }: {
  kind: ShortlistKind; item: Tender | Call | null; refId?: string; badge?: React.ReactNode;
}) {
  if (!item) {
    return (
      <li className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-surface-inset p-4">
        <span className="text-body text-ink-muted">This {kind === 'tender' ? 'notice' : 'call'} is no longer published.</span>
        {badge}
      </li>
    );
  }
  const tender = kind === 'tender';
  const d = tender ? getTenderDeadline(item as Tender) : getCallDeadline(item as Call);
  const who = tender
    ? [(item as Tender).buyerName, (item as Tender).country].filter(Boolean).join(' · ')
    : [PROGRAMMES[(item as Call).programme]?.label, (item as Call).funderCountry].filter(Boolean).join(' · ');
  const href = itemHref(kind, refId ?? item.id, item.slug);
  const hot = d.state === 'soon' || d.state === 'urgent';
  return (
    <li className="flex flex-col gap-2 rounded-md bg-surface-inset p-4 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <div className="flex min-w-0 flex-col gap-1">
        {href
          ? <Link href={href} className="break-words text-body font-semibold text-ink">{item.title}</Link>
          : <span className="break-words text-body font-semibold">{item.title}</span>}
        {who && <span className="text-small text-ink-muted">{who}</span>}
        {badge && <span className="pt-1">{badge}</span>}
      </div>
      <div className="flex shrink-0 flex-col sm:items-end">
        <span className="text-label text-ink-muted">Deadline</span>
        {d.iso ? <time dateTime={d.iso} className="font-mono text-mono-strong tabular-nums">{formatDateUtc(d.iso)} UTC</time> : <span className="text-small">None stated</span>}
        {d.countdown && <span className={cn('text-small font-bold', hot ? 'text-accent-text' : 'text-ink-muted')}>{d.countdown}</span>}
      </div>
    </li>
  );
}
