import type { Metadata } from 'next';
import Link from 'next/link';
import { dataOrNull, getCurrentUser, getDashboard } from '@/lib/account';
import { STATUS_LABEL, STATUS_ORDER, followHref, itemHref } from '@/lib/account-format';
import { formatDateUtc, formatNumber, formatPercent } from '@/lib/format';
import type { Dashboard } from '@/lib/types';
import { Callout } from '@/components/dg/blocks';
import { FactCell } from '@/components/dg/data-display';
import { Tag } from '@/components/dg/tag';
import { describeChange } from '@/components/dg/version-timeline';
import { AppHeader, Block, ItemRow, LoadFailed, NextStep } from '@/components/account/ui';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Dashboard', robots: { index: false, follow: false } };

const LIST = 'm-0 flex list-none flex-col gap-3 p-0';
const BROWSE = [{ label: 'Open tenders', href: '/tenders' }, { label: 'Open funding calls', href: '/funding' }];

function NewForSearches({ d }: { d: Dashboard }) {
  return (
    <Block id="new" title="New for your searches" aside={<Link href="/app/searches" className="text-small font-bold">All saved searches</Link>}>
      {d.matches.length === 0 ? (
        <NextStep links={BROWSE}>
          You have no saved searches. Set filters on the tenders or funding list and choose Save this search. New matches show up here.
        </NextStep>
      ) : (
        <ul className={LIST}>
          {d.matches.map((m) => (
            <li key={m.search.id} className="flex flex-col gap-3">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                <h3 className="m-0 break-words text-body font-bold">{m.search.name}</h3>
                <span className="font-mono text-mono text-ink-muted">{formatNumber(m.newCount)} new · {formatNumber(m.totalCount)} matches</span>
              </div>
              {m.items.length > 0 ? (
                <ul className={LIST}>{m.items.map((i) => <ItemRow key={i.id} kind={m.search.kind} item={i} />)}</ul>
              ) : (
                <p className="m-0 text-small text-ink-muted">No new matches since your last visit.</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </Block>
  );
}

function ClosingSoon({ d }: { d: Dashboard }) {
  return (
    <Block id="closing" title="Closing in the next 14 days">
      {d.closingSoon.length === 0 ? (
        <NextStep links={[{ label: 'Open shortlist', href: '/app/shortlist' }, ...BROWSE.slice(0, 1)]}>
          Nothing on your shortlist or in your searches closes in the next 14 days. Shortlist a notice to see its deadline here.
        </NextStep>
      ) : (
        <ul className={LIST}>
          {d.closingSoon.map((c) => (
            <ItemRow key={`${c.kind}/${c.item.id}`} kind={c.kind} item={c.item}
              badge={<Tag>{c.source === 'shortlist' ? 'On your shortlist' : 'From a saved search'}</Tag>} />
          ))}
        </ul>
      )}
    </Block>
  );
}

function Changes({ d }: { d: Dashboard }) {
  return (
    <Block id="changes" title="Changes on what you follow">
      {d.changes.length === 0 ? (
        <NextStep links={[{ label: 'Browse buyers', href: '/buyers' }, { label: 'Open shortlist', href: '/app/shortlist' }]}>
          No changes since your last visit. Follow a buyer or shortlist a notice and every amendment shows up here.
        </NextStep>
      ) : (
        <ul className={LIST}>
          {d.changes.map((c) => {
            const href = itemHref(c.kind, c.item.id, c.item.slug);
            return (
              <li key={`${c.kind}/${c.item.id}/${c.observedAt}`} className="flex flex-col gap-2 rounded-md bg-surface-inset p-4">
                {href ? <Link href={href} className="break-words text-body font-semibold text-ink">{c.item.title}</Link> : <span className="text-body font-semibold">{c.item.title}</span>}
                <span className="font-mono text-mono text-ink-muted">Detected <time dateTime={c.observedAt}>{formatDateUtc(c.observedAt)}</time></span>
                <ul className="m-0 flex list-none flex-col gap-1 p-0">
                  {c.changes.map((ch, i) => <li key={`${ch.field}-${i}`} className="min-w-0 text-body">{describeChange(ch)}</li>)}
                </ul>
              </li>
            );
          })}
        </ul>
      )}
    </Block>
  );
}

function Following({ d }: { d: Dashboard }) {
  return (
    <Block id="following" title="Following" aside={<Link href="/app/following" className="text-small font-bold">Manage</Link>}>
      {d.following.length === 0 ? (
        <NextStep links={[{ label: 'Browse buyers', href: '/buyers' }, { label: 'Open funding calls', href: '/funding' }]}>
          You follow no buyers or programmes yet. Open one and choose Follow to keep an eye on its notices.
        </NextStep>
      ) : (
        <ul className={LIST}>
          {d.following.map((f) => {
            const href = followHref(f.kind, f.ref);
            return (
              <li key={`${f.kind}/${f.ref}`} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-md bg-surface-inset p-4">
                <span className="flex min-w-0 flex-col">
                  {href ? <Link href={href} className="break-words text-body font-semibold text-ink">{f.name}</Link> : <span className="text-body font-semibold">{f.name}</span>}
                  <span className="text-small text-ink-muted">{f.kind === 'buyer' ? 'Buyer' : 'Programme'}{f.latestAt ? ` · latest ${formatDateUtc(f.latestAt)}` : ''}</span>
                </span>
                <span className="font-mono text-mono-strong tabular-nums">{formatNumber(f.openCount)} open</span>
              </li>
            );
          })}
        </ul>
      )}
    </Block>
  );
}

function Shortlist({ d }: { d: Dashboard }) {
  const counted = STATUS_ORDER.filter((s) => (d.shortlist.counts[s] ?? 0) > 0);
  return (
    <Block id="shortlist" title="Your shortlist" aside={<Link href="/app/shortlist" className="text-small font-bold">Open shortlist</Link>}>
      {counted.length === 0 && d.shortlist.items.length === 0 ? (
        <NextStep links={BROWSE}>
          Your shortlist is empty. Open a tender or a funding call and choose Shortlist to track it here.
        </NextStep>
      ) : (
        <>
          {counted.length > 0 && (
            <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
              {counted.map((s) => <li key={s}><Tag>{STATUS_LABEL[s]} · {d.shortlist.counts[s]}</Tag></li>)}
            </ul>
          )}
          <ul className={LIST}>
            {d.shortlist.items.map((s) => (
              <ItemRow key={`${s.kind}/${s.ref}`} kind={s.kind} item={s.item} refId={s.ref} badge={<Tag>{STATUS_LABEL[s.status] ?? s.status}</Tag>} />
            ))}
          </ul>
        </>
      )}
    </Block>
  );
}

function Pulse({ d }: { d: Dashboard }) {
  const p = d.pulse;
  return (
    <Block id="pulse" title="Market pulse">
      {!p ? (
        <p className="m-0 text-body text-ink-muted">Market figures are not available right now. They return on the next refresh.</p>
      ) : (
        <>
          <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
            <FactCell label="Published, last 30 days">
              {formatNumber(p.tendersPublished30d)}
              <div className="font-sans text-small font-normal text-ink-muted">Previous 30 days: {formatNumber(p.tendersPublishedPrev30d)}</div>
            </FactCell>
            <FactCell label="Open now">{formatNumber(p.openTenders)}</FactCell>
            <FactCell label="Closing within 14 days">{formatNumber(p.closingWithin14d)}</FactCell>
            <FactCell label="Amended, last 30 days">
              {formatPercent(p.amendedShare30d)}
              <div className="font-sans text-small font-normal text-ink-muted">of notices published</div>
            </FactCell>
            <FactCell label="Median time to deadline">
              {p.medianWindowDays === null ? <span className="font-sans">Not enough data</span> : `${Math.round(p.medianWindowDays * 10) / 10} days`}
              <div className="font-sans text-small font-normal text-ink-muted">notices published in the last 90 days</div>
            </FactCell>
          </dl>
          <p className="m-0 text-small text-ink-muted">
            Counts of notices published, not spend. As of <time dateTime={p.asOf}>{formatDateUtc(p.asOf)} UTC</time>.
          </p>
        </>
      )}
    </Block>
  );
}

export default async function DashboardPage() {
  const [result, me] = await Promise.all([getDashboard(), getCurrentUser()]);
  const d = dataOrNull(result);
  return (
    <>
      <AppHeader
        title={d?.lastVisitAt ? 'Welcome back' : 'Welcome'}
        lead={d?.lastVisitAt ? `Here is what is new since your last visit on ${formatDateUtc(d.lastVisitAt)}.` : 'Start by saving a search or shortlisting a notice.'}
      />
      {me && !me.onboarded && (
        <Callout title="Finish your profile">
          <p className="m-0">Tell us your role and what you follow, so your dashboard starts in the right place.</p>
          <Link href="/app/welcome" className="inline-flex min-h-11 items-center font-bold">Set up your profile</Link>
        </Callout>
      )}
      {d === null ? <LoadFailed href="/app" /> : (
        <>
          <NewForSearches d={d} />
          <div className="grid items-start gap-6 lg:grid-cols-2">
            <ClosingSoon d={d} />
            <Changes d={d} />
            <Following d={d} />
            <Shortlist d={d} />
          </div>
          <Pulse d={d} />
        </>
      )}
    </>
  );
}
